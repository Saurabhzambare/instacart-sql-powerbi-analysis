
-- What are the reorder rates of our 10 most frequently ordered products?

USE InstacartAnalytics;
GO

WITH product_metrics AS
(
    SELECT
        product_id,
        COUNT_BIG(*) AS orders_containing_product,
        SUM(CAST(reordered AS BIGINT))
            AS reordered_product_entries
    FROM staging.order_products_prior
    GROUP BY product_id
)
SELECT TOP (10)
    p.product_id,
    p.product_name,
    pm.orders_containing_product,
    pm.reordered_product_entries,

    CAST(
        100.0 * pm.reordered_product_entries
        / NULLIF(pm.orders_containing_product, 0)
        AS DECIMAL(5,2)
    ) AS reorder_rate_pct

FROM product_metrics AS pm

INNER JOIN staging.products AS p
    ON pm.product_id = p.product_id

ORDER BY
    pm.orders_containing_product DESC,
    p.product_id ASC;