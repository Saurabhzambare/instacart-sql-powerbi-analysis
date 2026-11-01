-- Save this BigQuery query as 15_validate_dbt_top_products.
select
    product_rank,
    product_id,
    product_name,
    prior_orders_with_product,
    reordered_entries,
    reorder_rate_pct
from `instacart-analytics-practice.instacart_dbt.mart_top_products`
order by product_rank;

