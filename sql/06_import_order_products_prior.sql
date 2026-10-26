USE InstacartAnalytics;
GO

IF OBJECT_ID(N'staging.order_products_prior', N'U') IS NULL
BEGIN
    CREATE TABLE staging.order_products_prior
    (
        order_id INT NULL,
        product_id INT NULL,
        add_to_cart_order INT NULL,
        reordered INT NULL
    );
END;
GO

IF NOT EXISTS (SELECT 1 FROM staging.order_products_prior)
BEGIN
    BULK INSERT staging.order_products_prior
    FROM 'D:\DataProjects\data-download\order_products__prior.csv'
    WITH
    (
        FORMAT = 'CSV',
        FIRSTROW = 2,
        FIELDTERMINATOR = ',',
        ROWTERMINATOR = '0x0a',
        CODEPAGE = '65001',
        KEEPNULLS,
        TABLOCK
    );
END;
ELSE
BEGIN
    PRINT 'Table already contains rows. Import skipped.';
END;
GO

-- Check the imported row count and basic field validity.
SELECT
    COUNT_BIG(*) AS total_order_product_rows,

    SUM(CASE
        WHEN order_id IS NULL OR product_id IS NULL
        THEN 1 ELSE 0
    END) AS rows_with_missing_ids,

    SUM(CASE
        WHEN add_to_cart_order IS NULL
          OR add_to_cart_order < 1
        THEN 1 ELSE 0
    END) AS invalid_cart_positions,

    SUM(CASE
        WHEN reordered IS NULL
          OR reordered NOT IN (0, 1)
        THEN 1 ELSE 0
    END) AS invalid_reordered_flags
FROM staging.order_products_prior;

-- Inspect all products recorded for order 2.
SELECT
    order_id,
    product_id,
    add_to_cart_order,
    reordered
FROM staging.order_products_prior
WHERE order_id = 2
ORDER BY add_to_cart_order;