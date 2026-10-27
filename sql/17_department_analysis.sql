-- Which departments account for the most product entries, and what are their reorder rates?

USE InstacartAnalytics
GO

SELECT
    d.department_id,
    
    d.department,
    
    COUNT_BIG(*) AS total_product_entries,
    
    SUM(CAST(op.reordered AS BIGINT))
        AS reordered_product_entries,

    CAST(
        100.0 * SUM(CAST(op.reordered AS BIGINT))
        /NULLIF(COUNT_BIG(*), 0)
        AS DECIMAL(5,2)
    ) AS reorder_rate_pct

FROM staging.order_products_prior op

INNER JOIN staging.products AS p
    ON op.product_id = p.product_id

INNER JOIN staging.departments AS d
    ON p.department_id = d.department_id

GROUP BY d.department_id,
         d.department

ORDER BY
    total_product_entries DESC,
    d.department_id ASC;
