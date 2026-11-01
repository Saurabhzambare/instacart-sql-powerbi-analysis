SELECT
    d.department_id,
    d.department,
    COUNT(*) AS product_entries,
    COUNT(DISTINCT op.order_id) AS distinct_orders,
    COUNTIF(op.reordered = 1) AS reordered_entries,
    ROUND(
        SAFE_DIVIDE(
            CAST(COUNTIF(op.reordered = 1) AS NUMERIC) * 100,
            COUNT(*)
        ),
        2
    ) AS reorder_rate_pct
FROM `instacart-analytics-practice.instacart_raw.order_products_prior` AS op
INNER JOIN `instacart-analytics-practice.instacart_raw.orders` AS o
    ON op.order_id = o.order_id
INNER JOIN `instacart-analytics-practice.instacart_raw.products` AS p
    ON op.product_id = p.product_id
INNER JOIN `instacart-analytics-practice.instacart_raw.departments` AS d
    ON p.department_id = d.department_id
WHERE o.eval_set = 'prior'
GROUP BY d.department_id, d.department
ORDER BY d.department_id;