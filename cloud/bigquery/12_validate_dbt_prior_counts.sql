SELECT
    COUNT(*) AS prior_product_entries,
    COUNT(DISTINCT order_id) AS distinct_prior_orders,
    COUNT(DISTINCT product_id) AS distinct_products,
    COUNTIF(reordered = 1) AS reordered_entries
FROM `instacart-analytics-practice.instacart_dbt.stg_order_products_prior`;