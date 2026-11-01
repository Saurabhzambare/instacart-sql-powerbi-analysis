-- Reference: docs/cloud_evidence/reconciliation_review.json
-- Dataset: instacart_cloud_5000_users_v1
-- Previously reconciled SQL Server and BigQuery hourly results.

with expected as (
    select *
    from unnest([
        struct(0 as order_hour_of_day, 440 as prior_orders),
        struct(1, 235),
        struct(2, 152),
        struct(3, 119),
        struct(4, 156),
        struct(5, 215),
        struct(6, 737),
        struct(7, 2078),
        struct(8, 4073),
        struct(9, 5900),
        struct(10, 6559),
        struct(11, 6484),
        struct(12, 6139),
        struct(13, 6263),
        struct(14, 6246),
        struct(15, 6293),
        struct(16, 6073),
        struct(17, 5225),
        struct(18, 4218),
        struct(19, 3166),
        struct(20, 2251),
        struct(21, 1676),
        struct(22, 1293),
        struct(23, 841)
    ])
),

actual as (
    select
        order_hour_of_day,
        prior_orders
    from {{ ref('mart_orders_by_hour') }}
)

select
    coalesce(e.order_hour_of_day, a.order_hour_of_day)
        as order_hour_of_day,
    e.prior_orders as expected_prior_orders,
    a.prior_orders as actual_prior_orders
from expected as e
full outer join actual as a
    on e.order_hour_of_day = a.order_hour_of_day
where
    e.order_hour_of_day is null
    or a.order_hour_of_day is null
    or a.prior_orders is null
    or e.prior_orders != a.prior_orders