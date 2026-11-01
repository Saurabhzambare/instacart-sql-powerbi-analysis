SELECT
    p.product_id,
    p.product_name,
    COUNT(*) AS prior_orders_with_product,
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
WHERE o.eval_set = 'prior'
GROUP BY p.product_id, p.product_name
ORDER BY prior_orders_with_product DESC, p.product_id ASC
LIMIT 10;