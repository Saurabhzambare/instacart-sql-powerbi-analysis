-- Reference: docs/cloud_evidence/reconciliation_review.json at f800de2.
-- The ten product rows and their order were manually reconciled earlier.
-- Dataset: instacart_cloud_5000_users_v1.
-- This fixed regression reference does not execute a new SQL Server query.
with expected as (
    select *
    from unnest([
        struct(1 as product_rank, 24852 as product_id, 'Banana' as product_name, 10625 as prior_orders_with_product, 8879 as reordered_entries, numeric '83.57' as reorder_rate_pct),
        struct(2, 13176, 'Bag of Organic Bananas', 8921, 7406, numeric '83.02'),
        struct(3, 21137, 'Organic Strawberries', 6384, 4964, numeric '77.76'),
        struct(4, 21903, 'Organic Baby Spinach', 5570, 4246, numeric '76.23'),
        struct(5, 47209, 'Organic Hass Avocado', 5253, 4197, numeric '79.90'),
        struct(6, 47766, 'Organic Avocado', 3939, 2927, numeric '74.31'),
        struct(7, 47626, 'Large Lemon', 3797, 2686, numeric '70.74'),
        struct(8, 27966, 'Organic Raspberries', 3560, 2763, numeric '77.61'),
        struct(9, 16797, 'Strawberries', 3414, 2376, numeric '69.60'),
        struct(10, 26209, 'Limes', 3348, 2291, numeric '68.43')
    ])
),

actual as (
    select
        product_rank,
        product_id,
        product_name,
        prior_orders_with_product,
        reordered_entries,
        reorder_rate_pct
    from {{ ref('mart_top_products') }}
)

select
    coalesce(e.product_rank, a.product_rank) as product_rank,
    e.product_id as expected_product_id,
    a.product_id as actual_product_id,
    e.product_name as expected_product_name,
    a.product_name as actual_product_name,
    e.prior_orders_with_product as expected_prior_orders,
    a.prior_orders_with_product as actual_prior_orders,
    e.reordered_entries as expected_reordered_entries,
    a.reordered_entries as actual_reordered_entries,
    e.reorder_rate_pct as expected_reorder_rate_pct,
    a.reorder_rate_pct as actual_reorder_rate_pct
from expected as e
full outer join actual as a
    on e.product_rank = a.product_rank
where
    e.product_rank is null
    or a.product_rank is null
    or e.product_id is distinct from a.product_id
    or e.product_name is distinct from a.product_name
    or e.prior_orders_with_product is distinct from a.prior_orders_with_product
    or e.reordered_entries is distinct from a.reordered_entries
    or e.reorder_rate_pct is distinct from a.reorder_rate_pct

