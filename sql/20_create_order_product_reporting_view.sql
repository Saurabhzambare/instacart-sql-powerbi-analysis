-- we’ll create the purchase reporting view.

USE InstacartAnalytics;
GO

-- One row per product within a prior order.
CREATE OR ALTER VIEW reporting.fact_order_products
AS
SELECT
	order_id,
	product_id,
	add_to_cart_order,
	reordered
FROM staging.order_products_prior
GO

-- Reconcile the reporting view to validated staging totals.

SELECT
    COUNT_BIG(*) AS total_product_entries,

    SUM(CAST(reordered AS BIGINT))
        AS reordered_product_entries,

    CAST(
        100.0 * SUM(CAST(reordered AS BIGINT))
        / NULLIF(COUNT_BIG(*), 0)
        AS DECIMAL(5,2)
    ) AS reorder_rate_pct

FROM reporting.fact_order_products;
GO

-- Preview a previously checked order.
SELECT
    order_id,
    product_id,
    add_to_cart_order,
    reordered
FROM reporting.fact_order_products
WHERE order_id = 2
ORDER BY add_to_cart_order;








