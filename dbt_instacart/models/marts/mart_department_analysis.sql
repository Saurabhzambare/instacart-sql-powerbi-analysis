-- Grain: one department across selected users' prior product entries.
select
    d.department_id,
    d.department,
    count(*) as product_entries,
    count(distinct op.order_id) as distinct_orders,
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
inner join {{ ref('stg_departments') }} as d
    on p.department_id = d.department_id
where o.eval_set = 'prior'
group by
    d.department_id,
    d.department

