# Products & Reordering reporting specification

This retrospective specification documents the implemented Power BI page. See the [project scope](PROJECT_SCOPE.md) for business context and the [SQL technical report](SQL_PROJECT_REPORT.md) for DAX and validation details.

**Intended reader:** A retail analyst comparing reach and repeat purchasing. The page supports historical product and department comparisons using the public prior-orders cohort.

| Rule | Expected behaviour | Acceptance evidence |
|---|---|---|
| Orders containing a product | Count distinct prior orders containing the product. A product occurs at most once per order in the validated order-product grain. | With all days selected, Banana appears in 472,565 orders. |
| Order penetration | Divide orders containing the product by all prior orders in the current order context. Product and department filters affect the numerator through OrderProducts and do not filter the Orders denominator. | Banana is 14.70% overall and 13.55% with Day Code 2 selected. |
| Reorder rate | Divide repeat-marked entries by all product entries in the selected product, department, and day context. | Banana reorder rate is 84.35% overall. |
| Day and department filters | Day Code syncs across report pages. Department applies on Products & Reordering. Preserve source day codes 0–6. | The recorded Day Code 2 check returns 59,881 orders containing Banana. |
| Reporting reconciliation | The reporting layer preserves source cohort counts and valid order and product references. | 3,214,874 prior orders, 32,434,489 entries, and zero unmatched references in the documented checks. |

The page describes historical order behaviour. Its source has no sales revenue, unit quantity, or retention outcome for these measures. The cloud subset and ML evaluation have separate scopes.
