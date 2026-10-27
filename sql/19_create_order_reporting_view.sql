-- Create an order reporting view.

USE InstacartAnalytics;
GO

CREATE OR ALTER VIEW reporting.fact_orders
AS
WITH order_baskets AS
(	
	SELECT
		order_id,
		COUNT_BIG(*) AS distinct_products_in_order
	FROM staging.order_products_prior
	GROUP BY order_id
)
SELECT
    o.order_id,
    o.user_id,
    o.order_number,
    o.order_dow,
    o.order_hour_of_day,
    o.days_since_prior_order,
    b.distinct_products_in_order

FROM staging.orders AS o

LEFT JOIN order_baskets AS b
    ON o.order_id = b.order_id

WHERE o.eval_set = 'prior';
GO

-- Validate the order-level reporting view.
SELECT
    COUNT_BIG(*) AS total_prior_orders,

    COUNT_BIG(DISTINCT order_id) AS unique_order_ids,

    SUM(CAST(
        CASE
            WHEN distinct_products_in_order IS NULL
            THEN 1 ELSE 0
        END
        AS BIGINT
    )) AS orders_without_basket_size,

    SUM(distinct_products_in_order)
        AS total_product_entries

FROM reporting.fact_orders;

-- Preview customer 1's prior orders.
SELECT
    order_id,
    user_id,
    order_number,
    order_dow,
    order_hour_of_day,
    days_since_prior_order,
    distinct_products_in_order

FROM reporting.fact_orders

WHERE user_id = 1

ORDER BY order_number;