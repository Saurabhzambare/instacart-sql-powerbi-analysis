USE InstacartAnalytics;
GO

-- Reproduce the export's selection: 5,000 lowest user IDs.
WITH SelectedUsers AS (
    SELECT TOP (5000)
        user_id
    FROM pipeline_staging.orders
    GROUP BY user_id
    ORDER BY user_id
)
SELECT
    o.order_hour_of_day,
    COUNT_BIG(*) AS prior_orders
FROM pipeline_staging.orders AS o
INNER JOIN SelectedUsers AS u
    ON o.user_id = u.user_id
WHERE o.eval_set = 'prior'
GROUP BY o.order_hour_of_day
ORDER BY o.order_hour_of_day;