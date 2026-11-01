SELECT
    order_hour_of_day,
    COUNT(*) AS prior_orders
FROM `instacart-analytics-practice.instacart_raw.orders`
WHERE eval_set = 'prior'
GROUP BY order_hour_of_day
ORDER BY order_hour_of_day;