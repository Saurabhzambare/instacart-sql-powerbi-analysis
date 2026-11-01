SELECT
    COUNT(*) AS total_rows,
    COUNT(DISTINCT department_id) AS unique_department_ids,
    COUNTIF(department_id IS NULL) AS missing_ids,
    COUNTIF(
        department IS NULL OR TRIM(department) = ''
    ) AS missing_or_blank_names
FROM `instacart-analytics-practice.instacart_dbt.stg_departments`;