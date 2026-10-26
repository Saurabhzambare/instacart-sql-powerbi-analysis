USE InstacartAnalytics;
GO

IF OBJECT_ID(N'staging.products', N'U') IS NULL
BEGIN
    CREATE TABLE staging.products
    (
        product_id INT NULL,
        product_name NVARCHAR(500) NULL,
        aisle_id INT NULL,
        department_id INT NULL
    );
END;
GO

IF NOT EXISTS (SELECT 1 FROM staging.products)
BEGIN
    BULK INSERT staging.products
    FROM 'D:\DataProjects\data-download\products.csv'
    WITH
    (
        FORMAT = 'CSV',
        FIRSTROW = 2,
        FIELDTERMINATOR = ',',
        ROWTERMINATOR = '0x0a',
        CODEPAGE = '65001'
    );
END;
ELSE
BEGIN
    PRINT 'Table already contains rows. Import skipped.';
END;
GO



-- Check row count, identifier uniqueness and missing values.
SELECT
    COUNT(*) AS total_products,
    COUNT(DISTINCT product_id) AS unique_product_ids,
    SUM(CASE WHEN product_id IS NULL THEN 1 ELSE 0 END)
        AS missing_product_ids,
    SUM(CASE
        WHEN product_name IS NULL
          OR LTRIM(RTRIM(product_name)) = ''
        THEN 1 ELSE 0
    END) AS missing_or_blank_names,
    SUM(CASE WHEN aisle_id IS NULL THEN 1 ELSE 0 END)
        AS missing_aisle_ids,
    SUM(CASE WHEN department_id IS NULL THEN 1 ELSE 0 END)
        AS missing_department_ids
FROM staging.products;

-- Check whether every product links to an existing department.
SELECT
    COUNT(*) AS products_without_matching_department
FROM staging.products AS p
LEFT JOIN staging.departments AS d
    ON p.department_id = d.department_id
WHERE d.department_id IS NULL;

-- Inspect the first five products with their department names.
SELECT TOP (5)
    p.product_id,
    p.product_name,
    p.aisle_id,
    p.department_id,
    d.department
FROM staging.products AS p
LEFT JOIN staging.departments AS d
    ON p.department_id = d.department_id
ORDER BY p.product_id;