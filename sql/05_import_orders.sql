USE InstacartAnalytics;
GO

IF OBJECT_ID(N'staging.orders', N'U') IS NULL
BEGIN
    CREATE TABLE staging.orders
    (
        order_id INT NULL,
        user_id INT NULL,
        eval_set VARCHAR(10) NULL,
        order_number INT NULL,
        order_dow INT NULL,
        order_hour_of_day INT NULL,
        days_since_prior_order DECIMAL(4,1) NULL
    );
END;
GO

IF NOT EXISTS (SELECT 1 FROM staging.orders)
BEGIN
    BULK INSERT staging.orders
    FROM 'D:\DataProjects\data-download\orders.csv'
    WITH
    (
        FORMAT = 'CSV',
        FIRSTROW = 2,
        FIELDTERMINATOR = ',',
        ROWTERMINATOR = '0x0a',
        CODEPAGE = '65001',
        KEEPNULLS
    );
END;
ELSE
BEGIN
    PRINT 'Table already contains rows. Import skipped.';
END;
GO


-- Count orders, unique identifiers and customers.
SELECT
    COUNT(*) AS total_orders,
    COUNT(DISTINCT order_id) AS unique_order_ids,
    COUNT(DISTINCT user_id) AS unique_customers,
    SUM(CASE WHEN order_id IS NULL THEN 1 ELSE 0 END)
        AS missing_order_ids,
    SUM(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END)
        AS missing_user_ids,
    SUM(CASE WHEN days_since_prior_order IS NULL THEN 1 ELSE 0 END)
        AS missing_previous_order_gaps
FROM staging.orders;

-- Inspect the dataset groups.
SELECT
    eval_set,
    COUNT(*) AS total_orders
FROM staging.orders
GROUP BY eval_set
ORDER BY eval_set;

-- Check whether missing gaps occur in the expected circumstances.
SELECT
    SUM(CASE
        WHEN order_number = 1
         AND days_since_prior_order IS NOT NULL
        THEN 1 ELSE 0
    END) AS first_orders_with_a_gap,

    SUM(CASE
        WHEN order_number > 1
         AND days_since_prior_order IS NULL
        THEN 1 ELSE 0
    END) AS later_orders_without_a_gap
FROM staging.orders;

-- Inspect customer 1's order history.
SELECT
    order_id,
    user_id,
    eval_set,
    order_number,
    order_dow,
    order_hour_of_day,
    days_since_prior_order
FROM staging.orders
WHERE user_id = 1
ORDER BY order_number;

-- check whether the recorded values fall within valid ranges.
USE InstacartAnalytics;
GO

SELECT
    SUM(CASE
        WHEN order_number IS NULL OR order_number < 1
        THEN 1 ELSE 0
    END) AS invalid_order_numbers,

    SUM(CASE
        WHEN order_dow IS NULL OR order_dow NOT BETWEEN 0 AND 6
        THEN 1 ELSE 0
    END) AS invalid_day_codes,

    SUM(CASE
        WHEN order_hour_of_day IS NULL
          OR order_hour_of_day NOT BETWEEN 0 AND 23
        THEN 1 ELSE 0
    END) AS invalid_order_hours,

    SUM(CASE
        WHEN days_since_prior_order < 0
          OR days_since_prior_order > 30
        THEN 1 ELSE 0
    END) AS invalid_order_gaps,

    SUM(CASE
        WHEN eval_set IS NULL
          OR eval_set NOT IN ('prior', 'train', 'test')
        THEN 1 ELSE 0
    END) AS invalid_dataset_groups
FROM staging.orders;