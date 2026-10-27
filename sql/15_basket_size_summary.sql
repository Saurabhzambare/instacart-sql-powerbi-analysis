-- How many different products does a typical order contain?

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
	COUNT_BIG(*) AS orders_with_product_entries,
	
	CAST(
        AVG(CAST(distinct_products_in_order AS DECIMAL(10,2)))
        AS DECIMAL(10,2)
    ) AS average_distinct_products_per_order,
	
	MIN(distinct_products_in_order)
        AS smallest_basket,

    MAX(distinct_products_in_order)
        AS largest_basket

FROM order_baskets

