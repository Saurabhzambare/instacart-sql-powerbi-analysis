-- Which combinations of day code and hour have the most orders?

USE InstacartAnalytics
GO

SELECT
	order_dow,
	order_hour_of_day,
	COUNT_BIG(*) total_prior_orders
FROM staging.orders
WHERE eval_set = 'prior'
GROUP BY 
	order_dow,
	order_hour_of_day
ORDER BY
	total_prior_orders DESC,
    order_dow ASC,
    order_hour_of_day ASC;
