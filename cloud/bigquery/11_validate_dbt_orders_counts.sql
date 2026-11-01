SELECT
    COUNT(*) AS total_orders,
    COUNT(DISTINCT user_id) AS selected_users,
    COUNTIF(eval_set = 'prior') AS prior_orders,
    COUNTIF(eval_set = 'train') AS train_orders,
    COUNTIF(eval_set = 'test') AS test_orders
FROM `instacart-analytics-practice.instacart_dbt.stg_orders`;