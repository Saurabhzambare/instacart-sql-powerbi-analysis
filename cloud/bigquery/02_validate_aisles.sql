SELECT
    COUNT(*) AS total_rows,
    COUNT(DISTINCT aisle_id) AS unique_aisle_ids,
    COUNTIF(aisle_id IS NULL) AS missing_ids,
    COUNTIF(
        aisle IS NULL OR TRIM(aisle) = ''
    ) AS missing_or_blank_names,
    COUNTIF(aisle_id <= 0) AS nonpositive_ids
FROM `instacart-analytics-practice.instacart_raw.aisles`;