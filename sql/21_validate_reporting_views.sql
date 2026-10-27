-- The final SQL step is to check that they work together without losing or multiplying entries.

USE InstacartAnalytics;
GO

-- 1. Check references between reporting views.
SELECT
    SUM(CAST(
        CASE WHEN p.product_id IS NULL THEN 1 ELSE 0 END
        AS BIGINT
    )) AS entries_without_product,

    SUM(CAST(
        CASE WHEN o.order_id IS NULL THEN 1 ELSE 0 END
        AS BIGINT
    )) AS entries_without_order

FROM reporting.fact_order_products AS op

LEFT JOIN reporting.dim_products AS p
    ON op.product_id = p.product_id

LEFT JOIN reporting.fact_orders AS o
    ON op.order_id = o.order_id;
GO

-- 2. Confirm that joins preserve purchase totals.
SELECT
    COUNT_BIG(*) AS joined_product_entries,

    SUM(CAST(op.reordered AS BIGINT))
        AS joined_reordered_entries

FROM reporting.fact_order_products AS op

INNER JOIN reporting.dim_products AS p
    ON op.product_id = p.product_id

INNER JOIN reporting.fact_orders AS o
    ON op.order_id = o.order_id;
GO

-- 3. Reconcile order-level basket totals.
SELECT
    COUNT_BIG(*) AS total_prior_orders,

    SUM(distinct_products_in_order)
        AS total_basket_product_entries

FROM reporting.fact_orders;
GO