-- Find repeated order-product pairs.
WITH DuplicatePairs AS (
    SELECT order_id, product_id
    FROM `instacart-analytics-practice.instacart_raw.order_products_prior`
    GROUP BY order_id, product_id
    HAVING COUNT(*) > 1
)
SELECT
    COUNT(*) AS total_rows,
    COUNT(DISTINCT op.order_id) AS distinct_orders,
    COUNT(DISTINCT op.product_id) AS distinct_products,
    COUNTIF(op.reordered = 1) AS reordered_entries,

    (SELECT COUNT(*) FROM DuplicatePairs) AS duplicate_pair_groups,

    COUNTIF(
        op.order_id IS NULL OR op.product_id IS NULL
    ) AS rows_with_missing_ids,

    COUNTIF(
        op.order_id <= 0 OR op.product_id <= 0
    ) AS nonpositive_ids,

    COUNTIF(
        op.add_to_cart_order IS NULL
        OR op.add_to_cart_order < 1
    ) AS invalid_cart_positions,

    COUNTIF(
        op.reordered IS NULL
        OR op.reordered NOT IN (0, 1)
    ) AS invalid_reordered_flags,

    COUNTIF(o.order_id IS NULL) AS unmatched_orders,
    COUNTIF(p.product_id IS NULL) AS unmatched_products,

    COUNTIF(
        o.order_id IS NOT NULL
        AND (o.eval_set IS NULL OR o.eval_set <> 'prior')
    ) AS entries_linked_to_nonprior_orders

FROM `instacart-analytics-practice.instacart_raw.order_products_prior` AS op

LEFT JOIN `instacart-analytics-practice.instacart_raw.orders` AS o
    ON op.order_id = o.order_id

LEFT JOIN `instacart-analytics-practice.instacart_raw.products` AS p
    ON op.product_id = p.product_id;