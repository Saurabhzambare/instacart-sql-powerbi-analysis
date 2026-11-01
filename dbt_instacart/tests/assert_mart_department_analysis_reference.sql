-- Reference: docs/cloud_evidence/reconciliation_review.json at f800de2.
-- These 21 rows were manually reconciled between SQL Server and BigQuery.
-- Dataset: instacart_cloud_5000_users_v1.
-- This is a fixed regression reference, not a new live SQL Server comparison.
with expected as (
    select *
    from unnest([
        struct(1 as department_id, 'frozen' as department, 51523 as product_entries, 27311 as distinct_orders, 27621 as reordered_entries, numeric '53.61' as reorder_rate_pct),
        struct(2, 'other', 826, 776, 358, numeric '43.34'),
        struct(3, 'bakery', 28291, 21159, 17969, numeric '63.51'),
        struct(4, 'produce', 219676, 56880, 142306, numeric '64.78'),
        struct(5, 'alcohol', 3631, 2011, 2043, numeric '56.27'),
        struct(6, 'international', 6448, 5302, 2473, numeric '38.35'),
        struct(7, 'beverages', 63757, 34834, 41317, numeric '64.80'),
        struct(8, 'pets', 2426, 1371, 1477, numeric '60.88'),
        struct(9, 'dry goods pasta', 19627, 13670, 8922, numeric '45.46'),
        struct(10, 'bulk', 845, 816, 490, numeric '57.99'),
        struct(11, 'personal care', 10930, 7792, 3684, numeric '33.71'),
        struct(12, 'meat seafood', 16434, 13473, 9121, numeric '55.50'),
        struct(13, 'pantry', 44107, 26262, 15432, numeric '34.99'),
        struct(14, 'breakfast', 16600, 12185, 9118, numeric '54.93'),
        struct(15, 'canned goods', 23918, 15441, 10741, numeric '44.91'),
        struct(16, 'dairy eggs', 128801, 52142, 86641, numeric '67.27'),
        struct(17, 'household', 17780, 11211, 7233, numeric '40.68'),
        struct(18, 'babies', 9365, 4094, 5363, numeric '57.27'),
        struct(19, 'snacks', 70538, 33478, 40608, numeric '57.57'),
        struct(20, 'deli', 24514, 18137, 14766, numeric '60.23'),
        struct(21, 'missing', 1713, 1404, 697, numeric '40.69')
    ])
),

actual as (
    select
        department_id,
        department,
        product_entries,
        distinct_orders,
        reordered_entries,
        reorder_rate_pct
    from {{ ref('mart_department_analysis') }}
)

select
    coalesce(e.department_id, a.department_id) as department_id,
    e.department as expected_department,
    a.department as actual_department,
    e.product_entries as expected_product_entries,
    a.product_entries as actual_product_entries,
    e.distinct_orders as expected_distinct_orders,
    a.distinct_orders as actual_distinct_orders,
    e.reordered_entries as expected_reordered_entries,
    a.reordered_entries as actual_reordered_entries,
    e.reorder_rate_pct as expected_reorder_rate_pct,
    a.reorder_rate_pct as actual_reorder_rate_pct
from expected as e
full outer join actual as a
    on e.department_id = a.department_id
where
    e.department_id is null
    or a.department_id is null
    or e.department is distinct from a.department
    or e.product_entries is distinct from a.product_entries
    or e.distinct_orders is distinct from a.distinct_orders
    or e.reordered_entries is distinct from a.reordered_entries
    or e.reorder_rate_pct is distinct from a.reorder_rate_pct

