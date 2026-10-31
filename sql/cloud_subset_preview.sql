-- Cloud learning subset preview only: no permanent tables or files are created.
-- Select the 5,000 lowest user IDs deterministically, retaining their histories.
-- This is an engineering subset, not a random or representative sample.
USE InstacartAnalytics;
GO

-- Group the orders by user_id, sort ascending, and select the first 5,000.
WITH SelectedUsers AS
(
    SELECT TOP (5000)
        user_id
    FROM pipeline_staging.orders
    GROUP BY user_id
    ORDER BY user_id
),

-- Join those users back to orders.
SubsetOrders AS
(
    SELECT
        o.order_id,
        o.user_id,
        o.eval_set
    FROM pipeline_staging.orders AS o
    INNER JOIN SelectedUsers AS u
        ON o.user_id = u.user_id
),

-- Count orders overall and separately for prior, train, and test.
OrderSummary AS
(
    SELECT
        COUNT_BIG(DISTINCT user_id) AS selected_users,
        COUNT_BIG(*) AS total_orders,
        COUNT_BIG(CASE WHEN eval_set = 'prior' THEN 1 END) AS prior_orders,
        COUNT_BIG(CASE WHEN eval_set = 'train' THEN 1 END) AS train_orders,
        COUNT_BIG(CASE WHEN eval_set = 'test' THEN 1 END) AS test_orders
    FROM SubsetOrders
),

-- Join the selected prior orders to their product entries.
-- Count entries, distinct products, and reordered entries.
EntrySummary AS
(
    SELECT
        COUNT_BIG(*) AS prior_product_entries,
        COUNT_BIG(DISTINCT op.product_id) AS distinct_products,
        COALESCE(SUM(CAST(op.reordered AS BIGINT)), 0) AS reordered_entries
    FROM pipeline_staging.order_products_prior AS op
    INNER JOIN SubsetOrders AS o
        ON op.order_id = o.order_id
    WHERE o.eval_set = 'prior'
)
SELECT
    o.selected_users,
    o.total_orders,
    o.prior_orders,
    o.train_orders,
    o.test_orders,
    e.prior_product_entries,
    e.distinct_products,
    e.reordered_entries
FROM OrderSummary AS o
CROSS JOIN EntrySummary AS e;
