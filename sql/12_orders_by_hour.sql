-- At what hours do customers place the most orders?

USE InstacartAnalytics
GO

SELECT
	order_hour_of_day,
	COUNT_BIG(*) AS total_prior_orders

FROM staging.orders
WHERE eval_set = 'prior'
GROUP BY order_hour_of_day
ORDER BY 
	total_prior_orders DESC,
    order_hour_of_day ASC;