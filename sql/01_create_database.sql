USE master;
GO

-- Create the project database only if it does not exist.
IF DB_ID(N'InstacartAnalytics') IS NULL
BEGIN
    EXEC(N'CREATE DATABASE InstacartAnalytics;');
END;
GO

-- Switch to the project database.
USE InstacartAnalytics;
GO

-- Area for tables imported from the source CSV files.
IF SCHEMA_ID(N'staging') IS NULL
BEGIN
    EXEC(N'CREATE SCHEMA staging AUTHORIZATION dbo;');
END;
GO

-- Area for reporting views and analytical outputs.
IF SCHEMA_ID(N'analytics') IS NULL
BEGIN
    EXEC(N'CREATE SCHEMA analytics AUTHORIZATION dbo;');
END;
GO

-- Confirm the database and project schemas.
SELECT
    DB_NAME() AS database_name,
    name AS schema_name
FROM sys.schemas
WHERE name IN (N'staging', N'analytics')
ORDER BY name;