-- Create our first reporting view for Power BI.

USE InstacartAnalytics;
GO

-- Create a place for our reporting views.

IF SCHEMA_ID(N'reporting') IS NULL
BEGIN
    EXEC(N'CREATE SCHEMA reporting AUTHORIZATION dbo;');
END;
GO

-- One row per product, with readable category names.
CREATE OR ALTER VIEW reporting.dim_products
AS
SELECT
    p.product_id,
    p.product_name,
    p.aisle_id,
    a.aisle,
    p.department_id,
    d.department

FROM staging.products AS p

INNER JOIN staging.aisles AS a
    ON p.aisle_id = a.aisle_id

INNER JOIN staging.departments AS d
    ON p.department_id = d.department_id;
GO

-- Check that the view preserves all products.
SELECT
    COUNT_BIG(*) AS total_products,
    COUNT_BIG(DISTINCT product_id) AS unique_product_ids
FROM reporting.dim_products;

-- Preview the view.
SELECT TOP (5)
    product_id,
    product_name,
    aisle_id,
    aisle,
    department_id,
    department
FROM reporting.dim_products
ORDER BY product_id;

