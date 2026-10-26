USE InstacartAnalytics;
GO

IF OBJECT_ID(N'staging.aisles', N'U') IS NULL
BEGIN
    CREATE TABLE staging.aisles
    (
        aisle_id INT NULL,
        aisle NVARCHAR(100) NULL
    );
END;
GO

IF NOT EXISTS (SELECT 1 FROM staging.aisles)
BEGIN
    BULK INSERT staging.aisles
    FROM 'D:\DataProjects\data-download\aisles.csv'
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

-- Validate aisle identifiers and names.
SELECT
    COUNT(*) AS total_aisles,
    COUNT(DISTINCT aisle_id) AS unique_aisle_ids,
    SUM(CASE WHEN aisle_id IS NULL THEN 1 ELSE 0 END)
        AS missing_aisle_ids,
    SUM(CASE
        WHEN aisle IS NULL OR LTRIM(RTRIM(aisle)) = ''
        THEN 1 ELSE 0
    END) AS missing_or_blank_names
FROM staging.aisles;

-- Check that every product references an existing aisle.
SELECT
    COUNT(*) AS products_without_matching_aisle
FROM staging.products AS p
LEFT JOIN staging.aisles AS a
    ON p.aisle_id = a.aisle_id
WHERE a.aisle_id IS NULL;

-- Display products with both category names.
SELECT TOP (5)
    p.product_id,
    p.product_name,
    a.aisle,
    d.department
FROM staging.products AS p
LEFT JOIN staging.aisles AS a
    ON p.aisle_id = a.aisle_id
LEFT JOIN staging.departments AS d
    ON p.department_id = d.department_id
ORDER BY p.product_id;