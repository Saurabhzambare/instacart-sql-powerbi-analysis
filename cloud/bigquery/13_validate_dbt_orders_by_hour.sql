SELECT
    order_hour_of_day,
    prior_orders
FROM `instacart-analytics-practice.instacart_dbt.mart_orders_by_hour`
ORDER BY order_hour_of_day;