select
    order_id,
    product_id,
    add_to_cart_order
from {{ ref('stg_order_products_prior') }}
where
    order_id <= 0
    or product_id <= 0
    or add_to_cart_order <= 0