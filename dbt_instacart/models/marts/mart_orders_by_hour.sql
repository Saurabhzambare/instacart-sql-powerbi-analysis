select
    order_hour_of_day,
    count(*) as prior_orders
from {{ ref('stg_orders') }}
where eval_set = 'prior'
group by order_hour_of_day