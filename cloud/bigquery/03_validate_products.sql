-- Validate product rows and their lookup relationships.
SELECT
    COUNT(*) AS total_rows,
    COUNT(DISTINCT p.product_id) AS unique_product_ids,

    COUNTIF(
        p.product_id IS NULL
        OR p.aisle_id IS NULL
        OR p.department_id IS NULL
    ) AS rows_with_missing_ids,

    COUNTIF(
        p.product_name IS NULL
        OR TRIM(p.product_name) = ''
    ) AS missing_or_blank_names,

    COUNTIF(
        p.product_id <= 0
        OR p.aisle_id <= 0
        OR p.department_id <= 0
    ) AS nonpositive_ids,

    COUNTIF(a.aisle_id IS NULL) AS unmatched_aisles,
    COUNTIF(d.department_id IS NULL) AS unmatched_departments

FROM `instacart-analytics-practice.instacart_raw.products` AS p

LEFT JOIN `instacart-analytics-practice.instacart_raw.aisles` AS a
    ON p.aisle_id = a.aisle_id

LEFT JOIN `instacart-analytics-practice.instacart_raw.departments` AS d
    ON p.department_id = d.department_id;