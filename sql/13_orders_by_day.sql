-- Which day-of-week codes have the most orders?

USE InstacartAnalytics
GO

SELECT
	order_dow,
	COUNT_BIG(*) AS total_prior_orders
FROM staging.orders
WHERE eval_set = 'prior'
GROUP BY order_dow
ORDER BY
	total_prior_orders DESC,
	order_dow ASC;
	