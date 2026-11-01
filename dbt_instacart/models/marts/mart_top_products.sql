-- Grain: one product among the ten most frequently ordered prior products.
-- The staging pair-uniqueness test establishes one product row per order.
with product_metrics as (
    select
        p.product_id,
        p.product_name,
        count(*) as prior_orders_with_product,
        countif(op.reordered = 1) as reordered_entries,
        round(
            safe_divide(
                cast(countif(op.reordered = 1) as numeric) * 100,
                count(*)
            ),
            2
        ) as reorder_rate_pct
    from {{ ref('stg_order_products_prior') }} as op
    inner join {{ ref('stg_orders') }} as o
        on op.order_id = o.order_id
    inner join {{ ref('stg_products') }} as p
        on op.product_id = p.product_id
    where o.eval_set = 'prior'
    group by
        p.product_id,
        p.product_name
),

ranked_products as (
    select
        row_number() over (
            order by prior_orders_with_product desc, product_id asc
        ) as product_rank,
        product_id,
        product_name,
        prior_orders_with_product,
        reordered_entries,
        reorder_rate_pct
    from product_metrics
)

select
    product_rank,
    product_id,
    product_name,
    prior_orders_with_product,
    reordered_entries,
    reorder_rate_pct
from ranked_products
where product_rank <= 10

