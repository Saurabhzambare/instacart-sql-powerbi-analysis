"""Validate the separate train-label input in SQL temporary tables only."""

import argparse
import json
import re
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from scripts.check_inputs import inspect_file


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COLUMNS = ["order_id", "product_id", "add_to_cart_order", "reordered"]
DATASET_LABEL = "instacart_ml_train_labels_v1"
INPUT_TABLE = "#ml_train_input"


def load_spec(path):
    spec = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(spec, dict):
        raise ValueError("ML contract must be a JSON object.")
    if spec.get("dataset_label") != DATASET_LABEL:
        raise ValueError("Unexpected ML input dataset label.")
    if spec.get("file") != "order_products__train.csv" or spec.get("columns") != COLUMNS:
        raise ValueError("ML contract must declare the four train-label columns in order.")
    for name in ("rows", "size_bytes", "full_train_orders"):
        if type(spec.get(name)) is not int or spec[name] <= 0:
            raise ValueError(f"Invalid positive integer in ML contract: {name}")
    if not isinstance(spec.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", spec["sha256"]):
        raise ValueError("Invalid SHA-256 in ML contract.")
    subset = spec.get("subset")
    if not isinstance(subset, dict) or subset.get("selection") != "lowest_user_ids":
        raise ValueError("ML subset must use lowest_user_ids selection.")
    if subset.get("dataset_label") != "instacart_ml_5000_users_v1":
        raise ValueError("Unexpected ML subset dataset label.")
    for name in ("selected_users", "selected_train_users"):
        if type(subset.get(name)) is not int or subset[name] <= 0:
            raise ValueError(f"Invalid subset count: {name}")
    if subset["selected_train_users"] > min(subset["selected_users"], spec["full_train_orders"]):
        raise ValueError("Selected train-user count is inconsistent with the contract.")
    return spec


def check_input(path, spec):
    result = inspect_file(
        path.parent,
        {"name": spec["file"], "columns": spec["columns"]},
        {"size_bytes": spec["size_bytes"], "sha256": spec["sha256"]},
    )
    if result["status"] != "PASS":
        raise ValueError(f"ML input check failed: {result.get('error')}")
    return result


def bulk_sql(path):
    filename = str(path).replace("'", "''")
    return f"""
        BULK INSERT #ml_train_input FROM '{filename}'
        WITH (FORMAT = 'CSV', FIRSTROW = 2, FIELDTERMINATOR = ',',
              ROWTERMINATOR = '0x0a', CODEPAGE = '65001', KEEPNULLS, TABLOCK);
    """


def expected_checks(spec):
    subset = spec["subset"]
    return {
        "rows": spec["rows"],
        "invalid_rows": 0,
        "distinct_train_orders": spec["full_train_orders"],
        "duplicate_order_product_groups": 0,
        "duplicate_order_cart_groups": 0,
        "missing_train_orders": 0,
        "missing_products": 0,
        "train_orders_without_labels": 0,
        "selected_users": subset["selected_users"],
        "selected_train_orders": subset["selected_train_users"],
        "selected_train_users": subset["selected_train_users"],
    }


def validate_checks(checks, spec):
    expected = expected_checks(spec)
    if checks != expected:
        raise ValueError(f"ML label checks failed. Expected {expected}; got {checks}")


def read_checks(cursor, spec, report):
    checks = report["checks"] = {}
    cursor.execute("""
        SELECT COUNT_BIG(*),
            COALESCE(SUM(CAST(CASE WHEN
                order_id IS NULL OR product_id IS NULL OR
                add_to_cart_order IS NULL OR reordered IS NULL OR
                order_id < 1 OR product_id < 1 OR add_to_cart_order < 1 OR
                reordered NOT IN (0, 1)
            THEN 1 ELSE 0 END AS BIGINT)), 0),
            COUNT_BIG(DISTINCT order_id)
        FROM #ml_train_input;
    """)
    checks.update(zip(("rows", "invalid_rows", "distinct_train_orders"), cursor.fetchone(), strict=True))
    if checks["rows"] != spec["rows"] or checks["invalid_rows"] != 0:
        raise ValueError(f"Training-label row count or values failed: {checks}")

    for name, keys in (
        ("duplicate_order_product_groups", "order_id, product_id"),
        ("duplicate_order_cart_groups", "order_id, add_to_cart_order"),
    ):
        cursor.execute(f"""
            SELECT COUNT_BIG(*) FROM (
                SELECT {keys} FROM #ml_train_input
                GROUP BY {keys} HAVING COUNT_BIG(*) > 1
            ) AS duplicate_groups;
        """)
        checks[name] = cursor.fetchone()[0]

    queries = {
        "missing_train_orders": """
            SELECT COUNT_BIG(*) FROM #ml_train_input AS l
            WHERE NOT EXISTS (
                SELECT 1 FROM pipeline_staging.orders AS o
                WHERE o.order_id = l.order_id AND o.eval_set = 'train'
            );
        """,
        "missing_products": """
            SELECT COUNT_BIG(*) FROM #ml_train_input AS l
            WHERE NOT EXISTS (
                SELECT 1 FROM pipeline_staging.products AS p
                WHERE p.product_id = l.product_id
            );
        """,
        "train_orders_without_labels": """
            SELECT COUNT_BIG(*) FROM pipeline_staging.orders AS o
            WHERE o.eval_set = 'train' AND NOT EXISTS (
                SELECT 1 FROM #ml_train_input AS l WHERE l.order_id = o.order_id
            );
        """,
    }
    for name, query in queries.items():
        cursor.execute(query)
        checks[name] = cursor.fetchone()[0]
    expected = expected_checks(spec)
    if any(checks[name] != expected[name] for name in checks):
        raise ValueError(f"Training-label keys, coverage, or references failed: {checks}")

    print("Checking eligibility of the selected 5,000-user cohort...", flush=True)
    # Create local temporary tables in unparameterized session scope, not inside
    # a parameterized/dynamic batch that can hide them from later statements.
    cursor.execute("CREATE TABLE #ml_selected_users (user_id INT NOT NULL PRIMARY KEY);")
    limit = spec["subset"]["selected_users"]  # validated positive int
    cursor.execute(f"""
        INSERT INTO #ml_selected_users (user_id)
        SELECT TOP ({limit}) user_id FROM pipeline_staging.orders
        GROUP BY user_id ORDER BY user_id;
    """)
    cursor.execute("SELECT COUNT_BIG(*) FROM #ml_selected_users;")
    checks["selected_users"] = cursor.fetchone()[0]
    cursor.execute("""
        SELECT COUNT_BIG(*), COUNT_BIG(DISTINCT o.user_id)
        FROM pipeline_staging.orders AS o
        INNER JOIN #ml_selected_users AS u ON o.user_id = u.user_id
        WHERE o.eval_set = 'train';
    """)
    checks.update(zip(("selected_train_orders", "selected_train_users"), cursor.fetchone(), strict=True))
    validate_checks(checks, spec)

    cursor.execute("""
        SELECT COUNT_BIG(*), COUNT_BIG(DISTINCT l.order_id),
            COUNT_BIG(DISTINCT l.product_id),
            COALESCE(SUM(CAST(l.reordered AS BIGINT)), 0)
        FROM #ml_train_input AS l
        INNER JOIN pipeline_staging.orders AS o ON l.order_id = o.order_id
        INNER JOIN #ml_selected_users AS u ON o.user_id = u.user_id
        WHERE o.eval_set = 'train';
    """)
    observations = dict(zip(
        ("label_entries", "target_orders", "distinct_products", "historically_reordered_entries"),
        cursor.fetchone(), strict=True,
    ))
    report["selected_label_observations"] = observations
    if (
        observations["target_orders"] != spec["subset"]["selected_train_users"]
        or not 0 < observations["label_entries"] <= spec["rows"]
        or not 0 < observations["distinct_products"] <= observations["label_entries"]
        or not 0 <= observations["historically_reordered_entries"] <= observations["label_entries"]
    ):
        raise ValueError(f"Selected-label observations are inconsistent: {observations}")


def run_validation(connection, path, spec, report):
    connection.autocommit = False
    commit_attempted = False
    report["transaction_outcome"] = "IN_PROGRESS"
    try:
        with closing(connection.cursor()) as cursor:
            cursor.execute("SET NOCOUNT ON; SET XACT_ABORT ON; SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;")
            cursor.execute("SELECT DB_NAME(), CAST(SERVERPROPERTY('ServerName') AS NVARCHAR(128));")
            database, server = cursor.fetchone()
            report.update(database=database, server=server)
            cursor.execute("""
                CREATE TABLE #ml_train_input (
                    order_id INT NULL,
                    product_id INT NULL,
                    add_to_cart_order INT NULL,
                    reordered INT NULL
                );
            """)
            print("Bulk loading training labels into a temporary table...", flush=True)
            cursor.execute(bulk_sql(path))
            report["input_after_bulk"] = check_input(path, spec)
            print("Checking label values, composite keys, coverage and references...", flush=True)
            read_checks(cursor, spec, report)
        commit_attempted = True
        connection.commit()
        report["transaction_outcome"] = "COMMITTED"
    except Exception:
        report["transaction_outcome"] = "UNKNOWN"
        try:
            connection.rollback()
            if not commit_attempted:
                report["transaction_outcome"] = "ROLLED_BACK"
        except Exception as error:
            report["rollback_error"] = str(error)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--spec", type=Path, default=Path("config/ml_train_labels_spec.json"))
    args = parser.parse_args()
    started = time.perf_counter()
    report = {
        "run_id": uuid4().hex,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "train_label_input_and_selected_user_eligibility",
        "permanent_table_writes": False,
        "transaction_outcome": "NOT_STARTED",
    }
    try:
        spec_path = args.spec if args.spec.is_absolute() else PROJECT_ROOT / args.spec
        spec = load_spec(spec_path)
        path = (args.data_dir / spec["file"]).resolve()
        report.update(dataset_label=spec["dataset_label"], subset_label=spec["subset"]["dataset_label"],
                      specification=str(spec_path), source_file=str(path))
        report["input_before_bulk"] = check_input(path, spec)
        from scripts.db_connection import get_connection

        print("Training-label header and fingerprint matched the separate ML contract.", flush=True)
        with closing(get_connection()) as connection:
            run_validation(connection, path, spec, report)
        report["status"] = "PASS"
    except ValueError as error:
        report.update(status="FAIL", error=str(error), error_type=type(error).__name__)
    except Exception as error:
        report.update(status="ERROR", error=str(error), error_type=type(error).__name__)

    report["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["duration_seconds"] = round(time.perf_counter() - started, 3)
    report_path = PROJECT_ROOT / "logs/ml_inputs" / f"{report['run_id']}.json"
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    except OSError as error:
        print(f"ERROR | Could not save ML validation report: {error}")
        return 1

    print(f"Result: {report['status']}")
    if report["status"] == "PASS":
        print(f"Training-label rows: {report['checks']['rows']:,}")
        print(f"Selected labeled users: {report['checks']['selected_train_users']:,}")
        for name, value in report["selected_label_observations"].items():
            print(f"{name}: {value:,}")
    else:
        print(f"Reason: {report['error']}")
    print("Permanent table writes: NONE")
    print(f"Transaction: {report['transaction_outcome']}")
    print(f"Report saved: {report_path}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
