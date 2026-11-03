-- Run the entire file in a fresh SSMS tab.
-- Rebuild the verified candidate preview and save it with a fixed customer split.
USE [InstacartAnalytics];
GO

IF @@TRANCOUNT <> 0
BEGIN
    RAISERROR('Open a new query tab before running this file.', 16, 1);
    RETURN;
END;

SET NOCOUNT ON;
SET XACT_ABORT ON;

DROP TABLE IF EXISTS #mlv1_examples;
DROP TABLE IF EXISTS #mlv1_splits;
DROP TABLE IF EXISTS #mlv1_history;
DROP TABLE IF EXISTS #mlv1_targets;
DROP TABLE IF EXISTS #mlv1_cohort;
DROP TABLE IF EXISTS #mlv1_labels;

DECLARE @publication_action VARCHAR(10);
DECLARE @saved_rows BIGINT;
DECLARE @lock_result INT;

SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
BEGIN TRY
    BEGIN TRANSACTION;

    EXEC @lock_result = sys.sp_getapplock
        @Resource = N'instacart_reorder_candidates_v1',
        @LockMode = 'Exclusive',
        @LockOwner = 'Transaction',
        @LockTimeout = 15000;

    IF @lock_result < 0
        THROW 51100, 'Could not acquire the candidate build lock.', 1;

    -- Reuse the saved labels and recover the same target orders.
    SELECT user_id, order_id, product_id, source_reordered
    INTO #mlv1_labels
    FROM pipeline_ml.train_labels_5000_users_v1;

    IF (SELECT COUNT_BIG(*) FROM #mlv1_labels) <> 33782
        OR (SELECT COUNT_BIG(DISTINCT product_id) FROM #mlv1_labels) <> 9850
        OR (SELECT COUNT_BIG(*) FROM #mlv1_labels WHERE source_reordered = 1) <> 20229
        OR EXISTS (
            SELECT 1
            FROM #mlv1_labels
            WHERE user_id IS NULL OR user_id <= 0
                OR order_id IS NULL OR order_id <= 0
                OR product_id IS NULL OR product_id <= 0
                OR source_reordered IS NULL OR source_reordered NOT IN (0, 1)
        )
        THROW 51101, 'Saved labels do not match the verified input.', 1;

    CREATE UNIQUE CLUSTERED INDEX IX_mlv1_labels
        ON #mlv1_labels(order_id, product_id);

    SELECT TOP (5000) user_id
    INTO #mlv1_cohort
    FROM pipeline_staging.orders
    GROUP BY user_id
    ORDER BY user_id;

    IF (SELECT COUNT_BIG(*) FROM #mlv1_cohort) <> 5000
        THROW 51102, 'Expected the verified cohort of 5,000 customers.', 1;

    SELECT
        o.user_id,
        o.order_id AS target_order_id,
        o.order_number AS target_order_number
    INTO #mlv1_targets
    FROM pipeline_staging.orders AS o
    INNER JOIN #mlv1_cohort AS u ON u.user_id = o.user_id
    WHERE o.eval_set = 'train';

    CREATE UNIQUE CLUSTERED INDEX IX_mlv1_targets_user
        ON #mlv1_targets(user_id);

    CREATE UNIQUE INDEX IX_mlv1_targets_order
        ON #mlv1_targets(target_order_id);

    IF (SELECT COUNT_BIG(*) FROM #mlv1_targets) <> 3200
        OR EXISTS (
            SELECT 1
            FROM #mlv1_targets
            WHERE target_order_number IS NULL OR target_order_number <= 1
        )
        OR EXISTS (
            SELECT user_id, order_id FROM #mlv1_labels
            EXCEPT
            SELECT user_id, target_order_id FROM #mlv1_targets
        )
        OR EXISTS (
            SELECT user_id, target_order_id FROM #mlv1_targets
            EXCEPT
            SELECT user_id, order_id FROM #mlv1_labels
        )
        THROW 51103, 'Target orders do not match the verified labeled customers.', 1;

    -- Build each product's history using orders strictly before the target.
    SELECT
        t.user_id,
        t.target_order_id,
        t.target_order_number,
        op.product_id,
        COUNT_BIG(*) AS prior_purchase_count,
        MAX(o.order_number) AS last_prior_order_number
    INTO #mlv1_history
    FROM #mlv1_targets AS t
    INNER JOIN pipeline_staging.orders AS o
        ON o.user_id = t.user_id
        AND o.eval_set = 'prior'
        AND o.order_number < t.target_order_number
    INNER JOIN pipeline_staging.order_products_prior AS op
        ON op.order_id = o.order_id
    GROUP BY
        t.user_id,
        t.target_order_id,
        t.target_order_number,
        op.product_id;

    CREATE UNIQUE CLUSTERED INDEX IX_mlv1_history
        ON #mlv1_history(target_order_id, product_id);

    IF EXISTS (
        SELECT 1
        FROM #mlv1_labels AS l
        LEFT JOIN #mlv1_history AS h
            ON h.user_id = l.user_id
            AND h.target_order_id = l.order_id
            AND h.product_id = l.product_id
        WHERE l.source_reordered <> CASE
            WHEN h.product_id IS NULL THEN 0
            ELSE 1
        END
    )
        THROW 51104, 'Source reorder flags disagree with earlier purchase history.', 1;

    -- Assign each customer to one group using a fixed hash order.
    -- The customer ID breaks hash ties.
    WITH ranked_users AS (
        SELECT
            user_id,
            ROW_NUMBER() OVER (
                ORDER BY
                    HASHBYTES('SHA2_256', CONCAT('instacart-reorder-v1:42:', user_id)),
                    user_id
            ) AS split_rank
        FROM #mlv1_targets
    )
    SELECT
        user_id,
        CAST(CASE
            WHEN split_rank <= 2240 THEN 'train'
            WHEN split_rank <= 2720 THEN 'validation'
            ELSE 'test'
        END AS VARCHAR(10)) AS dataset_split
    INTO #mlv1_splits
    FROM ranked_users;

    CREATE UNIQUE CLUSTERED INDEX IX_mlv1_splits
        ON #mlv1_splits(user_id);

    -- Keep every historical candidate and assign its next-order answer.
    SELECT
        h.user_id,
        h.target_order_id,
        h.product_id,
        h.target_order_number,
        h.prior_purchase_count,
        h.last_prior_order_number,
        CAST(CASE WHEN l.product_id IS NULL THEN 0 ELSE 1 END AS INT) AS buy_next,
        s.dataset_split
    INTO #mlv1_examples
    FROM #mlv1_history AS h
    INNER JOIN #mlv1_splits AS s ON s.user_id = h.user_id
    LEFT JOIN #mlv1_labels AS l
        ON l.user_id = h.user_id
        AND l.order_id = h.target_order_id
        AND l.product_id = h.product_id;

    CREATE UNIQUE CLUSTERED INDEX IX_mlv1_examples
        ON #mlv1_examples(target_order_id, product_id);

    IF (SELECT COUNT_BIG(*) FROM #mlv1_examples) <> 198544
        OR (SELECT COUNT_BIG(DISTINCT user_id) FROM #mlv1_examples) <> 3200
        OR (SELECT COUNT_BIG(DISTINCT target_order_id) FROM #mlv1_examples) <> 3200
        OR (SELECT COUNT_BIG(*) FROM #mlv1_examples WHERE buy_next = 1) <> 20229
        OR (SELECT COUNT_BIG(*) FROM #mlv1_examples WHERE buy_next = 0) <> 178315
        THROW 51105, 'Candidate totals do not match the verified live preview.', 1;

    IF EXISTS (
        SELECT 1
        FROM #mlv1_examples AS c
        WHERE c.prior_purchase_count <= 0
            OR c.last_prior_order_number IS NULL
            OR c.last_prior_order_number < 1
            OR c.last_prior_order_number >= c.target_order_number
            OR NOT EXISTS (
                SELECT 1
                FROM pipeline_staging.products AS p
                WHERE p.product_id = c.product_id
            )
    )
        THROW 51106, 'Invalid history cutoff or missing candidate product.', 1;

    IF (SELECT COUNT_BIG(DISTINCT user_id)
        FROM #mlv1_examples WHERE dataset_split = 'train') <> 2240
        OR (SELECT COUNT_BIG(DISTINCT user_id)
            FROM #mlv1_examples WHERE dataset_split = 'validation') <> 480
        OR (SELECT COUNT_BIG(DISTINCT user_id)
            FROM #mlv1_examples WHERE dataset_split = 'test') <> 480
        OR EXISTS (
            SELECT user_id
            FROM #mlv1_examples
            GROUP BY user_id
            HAVING COUNT(DISTINCT dataset_split) <> 1
        )
        OR EXISTS (
            SELECT dataset_split
            FROM #mlv1_examples
            GROUP BY dataset_split
            HAVING MIN(buy_next) = MAX(buy_next)
        )
        THROW 51107, 'The customer split or its label coverage is invalid.', 1;

    IF OBJECT_ID(N'pipeline_ml.reorder_candidates_v1', N'U') IS NULL
    BEGIN
        CREATE TABLE pipeline_ml.reorder_candidates_v1 (
            user_id INT NOT NULL CHECK (user_id > 0),
            target_order_id INT NOT NULL CHECK (target_order_id > 0),
            product_id INT NOT NULL CHECK (product_id > 0),
            target_order_number INT NOT NULL CHECK (target_order_number > 1),
            prior_purchase_count BIGINT NOT NULL CHECK (prior_purchase_count > 0),
            last_prior_order_number INT NOT NULL CHECK (last_prior_order_number > 0),
            buy_next INT NOT NULL CHECK (buy_next IN (0, 1)),
            dataset_split VARCHAR(10) NOT NULL
                CHECK (dataset_split IN ('train', 'validation', 'test')),
            CHECK (last_prior_order_number < target_order_number),
            PRIMARY KEY (target_order_id, product_id)
        );

        INSERT INTO pipeline_ml.reorder_candidates_v1 (
            user_id,
            target_order_id,
            product_id,
            target_order_number,
            prior_purchase_count,
            last_prior_order_number,
            buy_next,
            dataset_split
        )
        SELECT
            user_id,
            target_order_id,
            product_id,
            target_order_number,
            prior_purchase_count,
            last_prior_order_number,
            buy_next,
            dataset_split
        FROM #mlv1_examples;

        SET @publication_action = 'CREATED';
    END
    ELSE
        SET @publication_action = 'UNCHANGED';

    SELECT @saved_rows = COUNT_BIG(*)
    FROM pipeline_ml.reorder_candidates_v1 WITH (TABLOCKX, HOLDLOCK);

    -- Compare all saved values in both directions before committing.
    IF @saved_rows <> 198544
        OR EXISTS (
            SELECT user_id, target_order_id, product_id, target_order_number,
                prior_purchase_count, last_prior_order_number, buy_next, dataset_split
            FROM #mlv1_examples
            EXCEPT
            SELECT user_id, target_order_id, product_id, target_order_number,
                prior_purchase_count, last_prior_order_number, buy_next, dataset_split
            FROM pipeline_ml.reorder_candidates_v1
        )
        OR EXISTS (
            SELECT user_id, target_order_id, product_id, target_order_number,
                prior_purchase_count, last_prior_order_number, buy_next, dataset_split
            FROM pipeline_ml.reorder_candidates_v1
            EXCEPT
            SELECT user_id, target_order_id, product_id, target_order_number,
                prior_purchase_count, last_prior_order_number, buy_next, dataset_split
            FROM #mlv1_examples
        )
        THROW 51108, 'The saved v1 table differs from the verified build. Investigate before changing it.', 1;

    COMMIT TRANSACTION;
    SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;

    SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
    THROW;
END CATCH;

SELECT
    @publication_action AS publication_action,
    @saved_rows AS saved_candidate_rows;

SELECT
    dataset_split,
    COUNT_BIG(DISTINCT user_id) AS customers,
    COUNT_BIG(*) AS candidate_rows,
    COUNT_BIG(CASE WHEN buy_next = 1 THEN 1 END) AS positive_examples,
    COUNT_BIG(CASE WHEN buy_next = 0 THEN 1 END) AS negative_examples
FROM #mlv1_examples
GROUP BY dataset_split
ORDER BY CASE dataset_split
    WHEN 'train' THEN 1
    WHEN 'validation' THEN 2
    ELSE 3
END;