-- Overall repeat-purchase share across prior order-product entries.
USE InstacartAnalytics;
GO

SELECT
    COUNT_BIG(*) AS total_product_entries,
    SUM(CAST(reordered AS BIGINT)) AS reordered_product_entries,
    CAST(
        100.0 * SUM(CAST(reordered AS BIGINT))
        / NULLIF(COUNT_BIG(*), 0)
        AS DECIMAL(5,2)
    ) AS reorder_rate_pct
FROM staging.order_products_prior;
GO

-- Expected on the validated project data:
-- total_product_entries     = 32434489
-- reordered_product_entries = 19126536
-- reorder_rate_pct          = 58.97