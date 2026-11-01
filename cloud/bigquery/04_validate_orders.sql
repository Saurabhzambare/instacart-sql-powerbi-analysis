-- Validate the selected users' order metadata.
SELECT
    COUNT(*) AS total_rows,
    COUNT(DISTINCT order_id) AS unique_order_ids,
    COUNT(DISTINCT user_id) AS selected_users,

    COUNTIF(eval_set = 'prior') AS prior_orders,
    COUNTIF(eval_set = 'train') AS train_orders,
    COUNTIF(eval_set = 'test') AS test_orders,

    COUNTIF(
        order_id IS NULL OR user_id IS NULL
    ) AS rows_with_missing_ids,

    COUNTIF(
        order_id <= 0 OR user_id <= 0
    ) AS nonpositive_ids,

    COUNTIF(
        eval_set IS NULL
        OR eval_set NOT IN ('prior', 'train', 'test')
    ) AS invalid_eval_sets,

    COUNTIF(
        order_number IS NULL OR order_number < 1
    ) AS invalid_order_numbers,

    COUNTIF(
        order_dow IS NULL
        OR order_dow NOT BETWEEN 0 AND 6
    ) AS invalid_day_codes,

    COUNTIF(
        order_hour_of_day IS NULL
        OR order_hour_of_day NOT BETWEEN 0 AND 23
    ) AS invalid_hours,

    COUNTIF(
        (order_number = 1 AND days_since_prior_order IS NOT NULL)
        OR (order_number > 1 AND days_since_prior_order IS NULL)
        OR days_since_prior_order < 0
        OR days_since_prior_order > 30
    ) AS invalid_gap_logic

FROM `instacart-analytics-practice.instacart_raw.orders`;