-- Run in SSMS against InstacartAnalytics after a successful load or rollback exercise.
-- Read-only inspection of permanent tables; no raw file access is needed.

USE InstacartAnalytics;
GO

SET NOCOUNT ON;

SELECT
    COUNT_BIG(*) AS label_entries,
    COUNT_BIG(DISTINCT user_id) AS labeled_users,
    COUNT_BIG(DISTINCT order_id) AS target_orders,
    COUNT_BIG(DISTINCT product_id) AS distinct_products,
    COALESCE(SUM(CAST(source_reordered AS BIGINT)), 0) AS historically_reordered_entries
FROM pipeline_ml.train_labels_5000_users_v1;
-- Expected: 33782 | 3200 | 3200 | 9850 | 20229

WITH SelectedUsers AS (
    SELECT TOP (5000) user_id
    FROM pipeline_staging.orders
    GROUP BY user_id
    ORDER BY user_id
)
SELECT
    COALESCE(SUM(CAST(CASE WHEN l.user_id IS NULL OR l.order_id IS NULL
        OR l.product_id IS NULL OR l.add_to_cart_order IS NULL OR l.source_reordered IS NULL
        OR l.user_id <= 0 OR l.order_id <= 0 OR l.product_id <= 0
        OR l.add_to_cart_order <= 0 OR l.source_reordered NOT IN (0, 1)
        THEN 1 ELSE 0 END AS BIGINT)), 0) AS invalid_rows,
    COALESCE(SUM(CAST(CASE WHEN o.order_id IS NULL OR o.eval_set <> 'train'
        OR o.eval_set IS NULL OR o.user_id <> l.user_id OR o.user_id IS NULL
        THEN 1 ELSE 0 END AS BIGINT)), 0) AS invalid_order_or_user_references,
    COALESCE(SUM(CAST(CASE WHEN p.product_id IS NULL THEN 1 ELSE 0 END AS BIGINT)), 0)
        AS unmatched_products,
    COALESCE(SUM(CAST(CASE WHEN u.user_id IS NULL THEN 1 ELSE 0 END AS BIGINT)), 0)
        AS users_outside_selected_cohort
FROM pipeline_ml.train_labels_5000_users_v1 AS l
LEFT JOIN pipeline_staging.orders AS o ON o.order_id = l.order_id
LEFT JOIN pipeline_staging.products AS p ON p.product_id = l.product_id
LEFT JOIN SelectedUsers AS u ON u.user_id = l.user_id;
-- Expected: all zero.

SELECT COUNT_BIG(*) AS duplicate_order_product_groups
FROM (
    SELECT order_id, product_id FROM pipeline_ml.train_labels_5000_users_v1
    GROUP BY order_id, product_id HAVING COUNT_BIG(*) > 1
) AS duplicates;

SELECT COUNT_BIG(*) AS duplicate_order_cart_groups
FROM (
    SELECT order_id, add_to_cart_order FROM pipeline_ml.train_labels_5000_users_v1
    GROUP BY order_id, add_to_cart_order HAVING COUNT_BIG(*) > 1
) AS duplicates;
-- Both expected zero.

SELECT TOP (10) user_id, order_id, product_id, add_to_cart_order, source_reordered
FROM pipeline_ml.train_labels_5000_users_v1 
ORDER BY user_id, order_id, add_to_cart_order;
