SELECT
    COUNT(*) AS total_rows,
    COUNT(DISTINCT department_id) AS unique_department_ids,
    COUNTIF(department_id IS NULL) AS missing_ids,
    COUNTIF(
        department IS NULL OR TRIM(department) = ''
    ) AS missing_or_blank_names,
    COUNTIF(
        department_id NOT BETWEEN 1 AND 21
    ) AS out_of_range_ids
FROM `instacart-analytics-practice.instacart_raw.departments`;