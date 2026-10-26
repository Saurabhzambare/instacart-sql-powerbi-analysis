-- Check that every entry references a valid product and a prior order
USE InstacartAnalytics;
GO

SELECT
    SUM(CASE
        WHEN p.product_id IS NULL
        THEN 1 ELSE 0
    END) AS rows_without_matching_product,

    SUM(CASE
        WHEN o.order_id IS NULL
        THEN 1 ELSE 0
    END) AS rows_without_matching_order,

    SUM(CASE
        WHEN o.order_id IS NOT NULL
         AND o.eval_set <> 'prior'
        THEN 1 ELSE 0
    END) AS rows_linked_to_non_prior_orders

FROM staging.order_products_prior AS op

LEFT JOIN staging.products AS p
    ON op.product_id = p.product_id

LEFT JOIN staging.orders AS o
    ON op.order_id = o.order_id;

--Check duplicate order-product combinations
WITH duplicate_pairs AS
(
    SELECT
        order_id,
        product_id,
        COUNT_BIG(*) AS occurrences
    FROM staging.order_products_prior
    GROUP BY
        order_id,
        product_id
    HAVING COUNT_BIG(*) > 1
)
SELECT
    COUNT_BIG(*) AS duplicate_order_product_pairs
FROM duplicate_pairs;