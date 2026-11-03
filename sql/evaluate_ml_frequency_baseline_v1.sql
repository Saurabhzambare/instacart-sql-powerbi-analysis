USE [InstacartAnalytics];
GO

WITH ranked_candidates AS (
    SELECT
        target_order_id,
        buy_next,
        ROW_NUMBER() OVER (
            PARTITION BY target_order_id
            ORDER BY prior_purchase_count DESC,
                     last_prior_order_number DESC,
                     product_id
        ) AS product_rank
    FROM pipeline_ml.reorder_candidates_v1
    WHERE dataset_split = 'validation'
),
cutoffs AS (
    SELECT k
    FROM (VALUES (1), (3), (5), (10), (15), (20)) AS options(k)
),
order_results AS (
    SELECT
        c.k,
        r.target_order_id,
        COUNT(CASE WHEN r.buy_next = 1 THEN 1 END) AS actual_reorders,
        COUNT(CASE WHEN r.product_rank <= c.k THEN 1 END) AS predicted_reorders,
        COUNT(CASE
            WHEN r.product_rank <= c.k AND r.buy_next = 1 THEN 1
        END) AS correct_reorders
    FROM ranked_candidates AS r
    CROSS JOIN cutoffs AS c
    GROUP BY c.k, r.target_order_id
)
SELECT
    k AS top_k,
    COUNT(*) AS evaluated_orders,
    SUM(actual_reorders) AS actual_reorders,
    SUM(predicted_reorders) AS predicted_reorders,
    SUM(correct_reorders) AS correct_reorders,
    CAST(AVG(
        2.0 * correct_reorders
        / NULLIF(actual_reorders + predicted_reorders, 0)
    ) AS DECIMAL(8, 6)) AS mean_order_f1
FROM order_results
GROUP BY k
ORDER BY mean_order_f1 DESC, top_k ASC;