USE InstacartAnalytics;
GO

WITH SelectedUsers AS (
    SELECT TOP (5000)
        user_id
    FROM pipeline_staging.orders
    GROUP BY user_id
    ORDER BY user_id
)
SELECT
    d.department_id,
    d.department,
    COUNT_BIG(*) AS product_entries,
    COUNT_BIG(DISTINCT op.order_id) AS distinct_orders,
    SUM(CAST(op.reordered AS BIGINT)) AS reordered_entries,
    CAST(
        100.0 * SUM(CAST(op.reordered AS BIGINT))
        / NULLIF(COUNT_BIG(*), 0)
        AS DECIMAL(10, 2)
    ) AS reorder_rate_pct
FROM pipeline_staging.order_products_prior AS op
INNER JOIN pipeline_staging.orders AS o
    ON op.order_id = o.order_id
INNER JOIN SelectedUsers AS u
    ON o.user_id = u.user_id
INNER JOIN pipeline_staging.products AS p
    ON op.product_id = p.product_id
INNER JOIN pipeline_staging.departments AS d
    ON p.department_id = d.department_id
WHERE o.eval_set = 'prior'
GROUP BY d.department_id, d.department
ORDER BY d.department_id;