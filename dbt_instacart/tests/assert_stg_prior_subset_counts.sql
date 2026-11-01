with entry_metrics as (
    select
        count(*) as prior_product_entries,
        count(distinct order_id) as distinct_prior_orders,
        count(distinct product_id) as distinct_products,
        countif(reordered = 1) as reordered_entries
    from {{ ref('stg_order_products_prior') }}
)

select *
from entry_metrics
where
    prior_product_entries != 761750
    or distinct_prior_orders != 76832
    or distinct_products != 28854
    or reordered_entries != 448380