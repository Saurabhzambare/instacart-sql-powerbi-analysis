"""Fixed loading contracts for the remaining four baseline CSV files."""

# Column tuples: name, SQL type, required in target, binary comparison length.
TABLES = {
    "aisles": {
        "file": "aisles.csv",
        "rows": 134,
        "columns": (
            ("aisle_id", "INT", True, None),
            ("aisle", "NVARCHAR(100)", True, 200),
        ),
        "keys": ("aisle_id",),
        "invalid": ("aisle_id < 1", "LTRIM(RTRIM(aisle)) = ''"),
        "aggregates": (),
        "references": (),
    },
    "products": {
        "file": "products.csv",
        "rows": 49_688,
        "columns": (
            ("product_id", "INT", True, None),
            ("product_name", "NVARCHAR(500)", True, 1000),
            ("aisle_id", "INT", True, None),
            ("department_id", "INT", True, None),
        ),
        "keys": ("product_id",),
        "invalid": (
            "product_id < 1", "aisle_id < 1", "department_id < 1",
            "LTRIM(RTRIM(product_name)) = ''",
        ),
        "aggregates": (),
        "references": (
            ("missing_aisles", """
                SELECT COUNT_BIG(*) FROM {source} AS p
                WHERE NOT EXISTS (SELECT 1 FROM pipeline_staging.aisles AS a
                                  WHERE a.aisle_id = p.aisle_id);
            """),
            ("missing_departments", """
                SELECT COUNT_BIG(*) FROM {source} AS p
                WHERE NOT EXISTS (SELECT 1 FROM pipeline_staging.departments AS d
                                  WHERE d.department_id = p.department_id);
            """),
        ),
    },
    "orders": {
        "file": "orders.csv",
        "rows": 3_421_083,
        "columns": (
            ("order_id", "INT", True, None),
            ("user_id", "INT", True, None),
            ("eval_set", "VARCHAR(10)", True, 10),
            ("order_number", "INT", True, None),
            ("order_dow", "INT", True, None),
            ("order_hour_of_day", "INT", True, None),
            ("days_since_prior_order", "DECIMAL(4,1)", False, None),
        ),
        "keys": ("order_id",),
        "invalid": (
            "order_id < 1", "user_id < 1", "order_number < 1",
            "order_dow NOT BETWEEN 0 AND 6",
            "order_hour_of_day NOT BETWEEN 0 AND 23",
            "eval_set NOT IN ('prior', 'train', 'test')",
            "days_since_prior_order < 0", "days_since_prior_order > 30",
            "(order_number = 1 AND days_since_prior_order IS NOT NULL)",
            "(order_number > 1 AND days_since_prior_order IS NULL)",
        ),
        "aggregates": (
            ("prior_orders", "COUNT_BIG(CASE WHEN eval_set = 'prior' THEN 1 END)", 3_214_874),
            ("train_orders", "COUNT_BIG(CASE WHEN eval_set = 'train' THEN 1 END)", 131_209),
            ("test_orders", "COUNT_BIG(CASE WHEN eval_set = 'test' THEN 1 END)", 75_000),
            ("customers", "COUNT_BIG(DISTINCT user_id)", 206_209),
        ),
        "references": (),
    },
    "order_products_prior": {
        "file": "order_products__prior.csv",
        "rows": 32_434_489,
        "columns": (
            ("order_id", "INT", True, None),
            ("product_id", "INT", True, None),
            ("add_to_cart_order", "INT", True, None),
            ("reordered", "INT", True, None),
        ),
        "keys": ("order_id", "product_id"),
        "invalid": (
            "order_id < 1", "product_id < 1", "add_to_cart_order < 1",
            "reordered NOT IN (0, 1)",
        ),
        "aggregates": (
            ("distinct_orders", "COUNT_BIG(DISTINCT order_id)", 3_214_874),
            ("reordered_entries", "COALESCE(SUM(CAST(reordered AS BIGINT)), 0)", 19_126_536),
        ),
        "references": (
            ("missing_products", """
                SELECT COUNT_BIG(*) FROM {source} AS op
                WHERE NOT EXISTS (SELECT 1 FROM pipeline_staging.products AS p
                                  WHERE p.product_id = op.product_id);
            """),
            ("missing_prior_orders", """
                SELECT COUNT_BIG(*) FROM {source} AS op
                WHERE NOT EXISTS (SELECT 1 FROM pipeline_staging.orders AS o
                                  WHERE o.order_id = op.order_id AND o.eval_set = 'prior');
            """),
        ),
    },
}
