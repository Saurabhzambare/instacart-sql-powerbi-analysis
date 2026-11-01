with order_metrics as (
    select
        count(*) as total_orders,
        count(distinct user_id) as selected_users,
        countif(eval_set = 'prior') as prior_orders,
        countif(eval_set = 'train') as train_orders,
        countif(eval_set = 'test') as test_orders
    from {{ ref('stg_orders') }}
)

select *
from order_metrics
where
    total_orders != 81832
    or selected_users != 5000
    or prior_orders != 76832
    or train_orders != 3200
    or test_orders != 1800