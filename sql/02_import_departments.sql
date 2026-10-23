USE InstacartAnalytics;
GO

-- Create the staging table if it does not already exist.
IF OBJECT_ID(N'staging.departments', N'U') IS NULL
BEGIN
    CREATE TABLE staging.departments
    (
        department_id INT NULL,
        department VARCHAR(100) NULL
    );
END;
GO

-- Load only when the table is empty.
IF NOT EXISTS (SELECT 1 FROM staging.departments)
BEGIN
    BULK INSERT staging.departments
    FROM 'D:\DataProjects\data-download\departments.csv'
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




-- Inspect every imported department.
SELECT department_id, department
FROM staging.departments
ORDER BY department_id;

-- Check completeness and identifier uniqueness.
SELECT
    COUNT(*) AS total_rows,
    COUNT(DISTINCT department_id) AS unique_department_ids,
    SUM(CASE WHEN department_id IS NULL THEN 1 ELSE 0 END)
        AS missing_ids,
    SUM(CASE
        WHEN department IS NULL
          OR LTRIM(RTRIM(department)) = ''
        THEN 1 ELSE 0
    END) AS missing_or_blank_names
FROM staging.departments;