-- ML-02 preview. Run the ENTIRE file in a new SSMS query tab.
-- Select database InstacartAnalytics. Only session temporary tables are written.
-- Starting checkpoint: 54dd4bb. No model fitting or permanent publication.
USE InstacartAnalytics;
GO

SET NOCOUNT ON;
SET XACT_ABORT ON;

IF @@TRANCOUNT <> 0
    THROW 51000, 'Use a query tab with no existing transaction.', 1;

DROP TABLE IF EXISTS #mlp_candidates;
DROP TABLE IF EXISTS #mlp_history;
DROP TABLE IF EXISTS #mlp_targets;
DROP TABLE IF EXISTS #mlp_users;
DROP TABLE IF EXISTS #mlp_labels;

SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
BEGIN TRY
    BEGIN TRANSACTION;

    SELECT user_id, order_id, product_id, add_to_cart_order, source_reordered
    INTO #mlp_labels
    FROM pipeline_ml.train_labels_5000_users_v1;

    IF (SELECT COUNT_BIG(*) FROM #mlp_labels) <> 33782
        OR (SELECT COUNT_BIG(DISTINCT user_id) FROM #mlp_labels) <> 3200
        OR (SELECT COUNT_BIG(DISTINCT order_id) FROM #mlp_labels) <> 3200
        OR (SELECT COUNT_BIG(DISTINCT product_id) FROM #mlp_labels) <> 9850
        OR (SELECT COALESCE(SUM(CAST(source_reordered AS BIGINT)), 0) FROM #mlp_labels) <> 20229
        THROW 51001, 'The saved labels differ from the accepted live totals.', 1;

    IF EXISTS (
        SELECT 1 FROM #mlp_labels
        WHERE user_id IS NULL OR order_id IS NULL OR product_id IS NULL
            OR add_to_cart_order IS NULL OR source_reordered IS NULL
            OR user_id <= 0 OR order_id <= 0 OR product_id <= 0
            OR add_to_cart_order <= 0 OR source_reordered NOT IN (0, 1)
    )
        THROW 51002, 'Invalid values in the saved label table.', 1;

    CREATE UNIQUE CLUSTERED INDEX IX_mlp_labels ON #mlp_labels(order_id, product_id);

    SELECT TOP (5000) user_id
    INTO #mlp_users
    FROM pipeline_staging.orders
    GROUP BY user_id
    ORDER BY user_id;

    IF (SELECT COUNT_BIG(*) FROM #mlp_users) <> 5000
        THROW 51003, 'Expected the same 5,000-user cohort.', 1;

    IF EXISTS (
        SELECT 1 FROM #mlp_labels AS l
        LEFT JOIN pipeline_staging.orders AS o ON o.order_id = l.order_id
        LEFT JOIN #mlp_users AS u ON u.user_id = l.user_id
        WHERE o.order_id IS NULL OR o.user_id IS NULL OR o.user_id <> l.user_id
            OR o.eval_set IS NULL OR o.eval_set <> 'train'
            OR o.order_number IS NULL OR o.order_number <= 1 OR u.user_id IS NULL
    )
        THROW 51004, 'Target orders do not match the selected labeled customers.', 1;

    CREATE TABLE #mlp_targets (
        user_id INT NOT NULL PRIMARY KEY,
        target_order_id INT NOT NULL UNIQUE,
        target_order_number INT NOT NULL
    );
    INSERT INTO #mlp_targets(user_id, target_order_id, target_order_number)
    SELECT l.user_id, l.order_id, o.order_number
    FROM #mlp_labels AS l
    INNER JOIN pipeline_staging.orders AS o ON o.order_id = l.order_id
    GROUP BY l.user_id, l.order_id, o.order_number;

    IF (SELECT COUNT_BIG(*) FROM #mlp_targets) <> 3200
        THROW 51005, 'Expected one target order for each of 3,200 customers.', 1;

    IF EXISTS (
        SELECT 1 FROM pipeline_staging.orders AS o
        INNER JOIN #mlp_users AS u ON u.user_id = o.user_id
        WHERE o.eval_set = 'train' AND NOT EXISTS (
            SELECT 1 FROM #mlp_targets AS t
            WHERE t.user_id = o.user_id AND t.target_order_id = o.order_id
        )
    )
        THROW 51012, 'A selected train order is missing from the target set.', 1;

    -- Candidate products must come from earlier orders, never from the target basket.
    -- CORE_HISTORY_BEGIN
    SELECT t.user_id, t.target_order_id, t.target_order_number, op.product_id,
        COUNT_BIG(*) AS prior_purchase_count,
        MAX(o.order_number) AS last_prior_order_number
    INTO #mlp_history
    FROM #mlp_targets AS t
    INNER JOIN pipeline_staging.orders AS o
        ON o.user_id = t.user_id
        AND o.eval_set = 'prior'
        AND o.order_number < t.target_order_number
    INNER JOIN pipeline_staging.order_products_prior AS op
        ON op.order_id = o.order_id
    GROUP BY t.user_id, t.target_order_id, t.target_order_number, op.product_id;
    -- CORE_HISTORY_END

    CREATE UNIQUE CLUSTERED INDEX IX_mlp_history ON #mlp_history(user_id, product_id);

    IF EXISTS (
        SELECT 1 FROM #mlp_targets AS t
        WHERE NOT EXISTS (SELECT 1 FROM #mlp_history AS h WHERE h.user_id = t.user_id)
    )
        THROW 51006, 'A selected customer has no earlier purchased-product candidates.', 1;

    DECLARE @flag_history_mismatches BIGINT;
    SELECT @flag_history_mismatches = COUNT_BIG(*)
    FROM #mlp_labels AS l
    LEFT JOIN #mlp_history AS h
        ON h.user_id = l.user_id AND h.target_order_id = l.order_id AND h.product_id = l.product_id
    WHERE l.source_reordered <> CASE WHEN h.product_id IS NULL THEN 0 ELSE 1 END;

    IF @flag_history_mismatches <> 0
        THROW 51007, 'Source reordered flags disagree with reconstructed earlier history.', 1;

    -- Target answers come only from next-order product presence.
    -- source_reordered and target add_to_cart_order are deliberately excluded.
    -- CORE_CANDIDATES_BEGIN
    SELECT h.user_id, h.target_order_id, h.product_id,
        h.target_order_number, h.prior_purchase_count, h.last_prior_order_number,
        CAST(CASE WHEN l.product_id IS NULL THEN 0 ELSE 1 END AS INT) AS buy_next
    INTO #mlp_candidates
    FROM #mlp_history AS h
    LEFT JOIN #mlp_labels AS l
        ON l.user_id = h.user_id AND l.order_id = h.target_order_id AND l.product_id = h.product_id;
    -- CORE_CANDIDATES_END

    CREATE UNIQUE CLUSTERED INDEX IX_mlp_candidates
        ON #mlp_candidates(target_order_id, product_id);

    DECLARE @invalid_history_or_targets BIGINT;
    SELECT @invalid_history_or_targets = COUNT_BIG(*) FROM #mlp_candidates
    WHERE product_id IS NULL OR product_id <= 0
        OR prior_purchase_count IS NULL OR prior_purchase_count <= 0
        OR last_prior_order_number IS NULL OR last_prior_order_number < 1
        OR last_prior_order_number >= target_order_number
        OR buy_next IS NULL OR buy_next NOT IN (0, 1);
    IF @invalid_history_or_targets <> 0
        THROW 51008, 'Invalid candidate history, prediction cutoff, or target.', 1;

    DECLARE @missing_candidate_products BIGINT;
    SELECT @missing_candidate_products = COUNT_BIG(*) FROM #mlp_candidates AS c
    WHERE NOT EXISTS (
        SELECT 1 FROM pipeline_staging.products AS p WHERE p.product_id = c.product_id
    );
    IF @missing_candidate_products <> 0
        THROW 51009, 'Candidate products are missing from the full product lookup.', 1;

    IF (SELECT COUNT_BIG(DISTINCT user_id) FROM #mlp_candidates) <> 3200
        OR (SELECT COUNT_BIG(DISTINCT target_order_id) FROM #mlp_candidates) <> 3200
        THROW 51010, 'Candidate construction lost selected customers or targets.', 1;

    -- The independently reconstructed history/flag check above must pass first.
    IF (SELECT COUNT_BIG(*) FROM #mlp_candidates WHERE buy_next = 1) <> 20229
        THROW 51011, 'Positive candidates do not reconcile with validated repeat purchases.', 1;

    COMMIT TRANSACTION;
    SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

    -- RESULT 1: candidate totals. Total/negative counts are new live observations.
    SELECT COUNT_BIG(*) AS candidate_rows,
        COUNT_BIG(DISTINCT user_id) AS labeled_users,
        COUNT_BIG(DISTINCT target_order_id) AS target_orders,
        COUNT_BIG(CASE WHEN buy_next = 1 THEN 1 END) AS positive_examples,
        COUNT_BIG(CASE WHEN buy_next = 0 THEN 1 END) AS negative_examples,
        CAST(100.0 * COUNT_BIG(CASE WHEN buy_next = 1 THEN 1 END)
            / NULLIF(COUNT_BIG(*), 0) AS DECIMAL(10, 2)) AS positive_rate_pct
    FROM #mlp_candidates;

    -- RESULT 2: all three must be zero; uniqueness is enforced by the temporary index.
    SELECT @flag_history_mismatches AS source_flag_history_mismatches,
        @invalid_history_or_targets AS invalid_history_or_targets,
        @missing_candidate_products AS missing_candidate_products;

    -- RESULT 3: new target-basket products correctly excluded from repeat candidates.
    SELECT COUNT_BIG(*) AS target_entries,
        COUNT_BIG(CASE WHEN h.product_id IS NOT NULL THEN 1 END) AS previously_purchased_entries,
        COUNT_BIG(CASE WHEN h.product_id IS NULL THEN 1 END) AS first_purchase_entries_excluded
    FROM #mlp_labels AS l
    LEFT JOIN #mlp_history AS h
        ON h.user_id = l.user_id AND h.target_order_id = l.order_id AND h.product_id = l.product_id;
    -- Expected after history reconciliation: 33782 | 20229 | 13553.

    -- RESULT 4: example candidate rows; the first thirty need not include both target values.
    SELECT TOP (30) c.user_id, c.target_order_id, c.product_id, p.product_name,
        c.prior_purchase_count, c.last_prior_order_number, c.target_order_number, c.buy_next
    FROM #mlp_candidates AS c
    INNER JOIN pipeline_staging.products AS p ON p.product_id = c.product_id
    ORDER BY c.user_id, c.product_id;

    PRINT 'Candidate preview completed. No permanent tables were changed.';
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
    SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
    THROW;
END CATCH;
