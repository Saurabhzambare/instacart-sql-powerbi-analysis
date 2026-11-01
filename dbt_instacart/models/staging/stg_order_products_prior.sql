select
    order_id,
    product_id,
    add_to_cart_order,
    reordered
from {{ source('instacart_raw', 'order_products_prior') }}