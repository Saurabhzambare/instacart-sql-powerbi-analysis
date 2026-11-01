-- Save this BigQuery query as 14_validate_dbt_department_analysis.
select
    department_id,
    department,
    product_entries,
    distinct_orders,
    reordered_entries,
    reorder_rate_pct
from `instacart-analytics-practice.instacart_dbt.mart_department_analysis`
order by department_id;

