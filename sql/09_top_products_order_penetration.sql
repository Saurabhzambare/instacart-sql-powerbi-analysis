Use InstacartAnalytics;
GO

WITH product_order_counts AS
(
	SELECT
		product_id,
		COUNT_BIG(*) AS orders_containing_product
	FROM staging.order_products_prior
	GROUP BY product_id
),
prior_order_total AS
(
	SELECT
		COUNT_BIG(*) AS total_prior_orders
	FROM staging.orders
	WHERE eval_set = 'prior'
)
SELECT TOP (10)
    p.product_id,
    p.product_name,
    d.department,
    pc.orders_containing_product,
	CAST(
		100.0 * pc.orders_containing_product
		/ NULLIF(pt.total_prior_orders, 0)
		AS DECIMAL(5,2)
    ) AS order_penetration_pct
FROM product_order_counts AS pc

INNER JOIN staging.products AS p
    ON pc.product_id = p.product_id

INNER JOIN staging.departments AS d
    ON p.department_id = d.department_id

CROSS JOIN prior_order_total as pt 

ORDER BY
    pc.orders_containing_product DESC,
    p.product_id ASC;