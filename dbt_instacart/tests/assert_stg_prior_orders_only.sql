select
    op.order_id,
    op.product_id,
    o.eval_set
from {{ ref('stg_order_products_prior') }} as op
left join {{ ref('stg_orders') }} as o
    on op.order_id = o.order_id
where
    o.order_id is null
    or o.eval_set is null
    or o.eval_set != 'prior'