SELECT
    'stg_departments' AS model_name,
    COUNT(*) AS total_rows
FROM `instacart-analytics-practice.instacart_dbt.stg_departments`

UNION ALL

SELECT
    'stg_aisles',
    COUNT(*)
FROM `instacart-analytics-practice.instacart_dbt.stg_aisles`

UNION ALL

SELECT
    'stg_products',
    COUNT(*)
FROM `instacart-analytics-practice.instacart_dbt.stg_products`

ORDER BY model_name;