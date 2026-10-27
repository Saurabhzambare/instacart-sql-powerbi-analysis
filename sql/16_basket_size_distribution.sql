-- How many orders have each basket size?
USE InstacartAnalytics
GO

WITH order_baskets AS
(	
	SELECT
		order_id,
		COUNT_BIG(*) AS distinct_products_in_order
	FROM staging.order_products_prior
	GROUP BY order_id
)
SELECT 
	distinct_products_in_order,
	COUNT_BIG(*) AS number_of_orders
FROM order_baskets
GROUP BY distinct_products_in_order
ORDER BY
    number_of_orders DESC,
    distinct_products_in_order ASC;