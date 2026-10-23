-- Check the SQL Server instance used for this project.
SELECT
    SERVERPROPERTY('ServerName') AS server_name,
    SERVERPROPERTY('Edition') AS edition,
    SERVERPROPERTY('ProductVersion') AS product_version,
    DB_NAME() AS current_database;
