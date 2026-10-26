USE InstacartAnalytics;
GO

-- Count the orders containing each product.
WITH product_order_counts AS
(
    SELECT
        product_id,
        COUNT_BIG(*) AS orders_containing_product
    FROM staging.order_products_prior
    GROUP BY product_id
)

-- Add product descriptions and show the top 10.
SELECT TOP (10)
    p.product_id,
    p.product_name,
    d.department,
    pc.orders_containing_product
FROM product_order_counts AS pc

INNER JOIN staging.products AS p
    ON pc.product_id = p.product_id

INNER JOIN staging.departments AS d
    ON p.department_id = d.department_id

ORDER BY
    pc.orders_containing_product DESC,
    p.product_id ASC;