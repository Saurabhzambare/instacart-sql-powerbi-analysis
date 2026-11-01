select
    order_id,
    user_id,
    order_number,
    order_dow,
    order_hour_of_day,
    days_since_prior_order
from {{ ref('stg_orders') }}
where
    order_id <= 0
    or user_id <= 0
    or order_number < 1
    or order_dow not between 0 and 6
    or order_hour_of_day not between 0 and 23
    or (
        order_number = 1
        and days_since_prior_order is not null
    )
    or (
        order_number > 1
        and (
            days_since_prior_order is null
            or days_since_prior_order not between 0 and 30
        )
    )