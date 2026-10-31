"""Export a checked five-file cloud subset without modifying permanent SQL tables."""

import argparse
import csv
import hashlib
import json
import tempfile
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[1]
METRIC_NAMES = (
    "selected_users", "total_orders", "prior_orders", "train_orders", "test_orders",
    "prior_product_entries", "distinct_products", "reordered_entries",
    "distinct_prior_orders", "departments", "aisles", "invalid_orders",
    "invalid_entries", "invalid_product_names", "invalid_lookup_names",
    "missing_products", "missing_aisles", "missing_departments",
)

# file, temporary source, output header, ordering columns, expected-count metric
EXPORTS = (
    ("departments.csv", "#cloud_departments", ("department_id", "department"),
     "department_id", "departments"),
    ("aisles.csv", "#cloud_aisles", ("aisle_id", "aisle"), "aisle_id", "aisles"),
    ("products.csv", "#cloud_products", ("product_id", "product_name", "aisle_id", "department_id"),
     "product_id", "distinct_products"),
    ("orders.csv", "#cloud_orders", ("order_id", "user_id", "eval_set", "order_number",
     "order_dow", "order_hour_of_day", "days_since_prior_order"), "order_id", "total_orders"),
    ("order_products__prior.csv", "#cloud_entries", ("order_id", "product_id",
     "add_to_cart_order", "reordered"), "order_id, product_id", "prior_product_entries"),
)

SNAPSHOT_SQL = """
    SELECT o.order_id, o.user_id, o.eval_set, o.order_number, o.order_dow,
           o.order_hour_of_day, o.days_since_prior_order
    INTO #cloud_orders
    FROM pipeline_staging.orders AS o
    INNER JOIN #cloud_users AS u ON u.user_id = o.user_id;
    CREATE UNIQUE CLUSTERED INDEX ix_cloud_orders ON #cloud_orders(order_id);

    SELECT op.order_id, op.product_id, op.add_to_cart_order, op.reordered
    INTO #cloud_entries
    FROM pipeline_staging.order_products_prior AS op
    INNER JOIN #cloud_orders AS o ON o.order_id = op.order_id
    WHERE o.eval_set = 'prior';
    CREATE UNIQUE CLUSTERED INDEX ix_cloud_entries ON #cloud_entries(order_id, product_id);

    SELECT p.product_id, p.product_name, p.aisle_id, p.department_id
    INTO #cloud_products
    FROM pipeline_staging.products AS p
    WHERE EXISTS (SELECT 1 FROM #cloud_entries AS e WHERE e.product_id = p.product_id);
    CREATE UNIQUE CLUSTERED INDEX ix_cloud_products ON #cloud_products(product_id);

    SELECT department_id, department INTO #cloud_departments FROM pipeline_staging.departments;
    CREATE UNIQUE CLUSTERED INDEX ix_cloud_departments ON #cloud_departments(department_id);
    SELECT aisle_id, aisle INTO #cloud_aisles FROM pipeline_staging.aisles;
    CREATE UNIQUE CLUSTERED INDEX ix_cloud_aisles ON #cloud_aisles(aisle_id);
"""

METRICS_SQL = """
    SELECT
      (SELECT COUNT_BIG(*) FROM #cloud_users),
      (SELECT COUNT_BIG(*) FROM #cloud_orders),
      (SELECT COUNT_BIG(*) FROM #cloud_orders WHERE eval_set = 'prior'),
      (SELECT COUNT_BIG(*) FROM #cloud_orders WHERE eval_set = 'train'),
      (SELECT COUNT_BIG(*) FROM #cloud_orders WHERE eval_set = 'test'),
      (SELECT COUNT_BIG(*) FROM #cloud_entries),
      (SELECT COUNT_BIG(DISTINCT product_id) FROM #cloud_entries),
      (SELECT COALESCE(SUM(CAST(reordered AS BIGINT)), 0) FROM #cloud_entries),
      (SELECT COUNT_BIG(DISTINCT order_id) FROM #cloud_entries),
      (SELECT COUNT_BIG(*) FROM #cloud_departments),
      (SELECT COUNT_BIG(*) FROM #cloud_aisles),
      (SELECT COUNT_BIG(*) FROM #cloud_orders WHERE
          order_id IS NULL OR order_id < 1 OR user_id IS NULL OR user_id < 1
          OR eval_set IS NULL OR eval_set NOT IN ('prior', 'train', 'test')
          OR order_number IS NULL OR order_number < 1
          OR order_dow IS NULL OR order_dow NOT BETWEEN 0 AND 6
          OR order_hour_of_day IS NULL OR order_hour_of_day NOT BETWEEN 0 AND 23
          OR (order_number = 1 AND days_since_prior_order IS NOT NULL)
          OR (order_number > 1 AND days_since_prior_order IS NULL)
          OR days_since_prior_order < 0 OR days_since_prior_order > 30),
      (SELECT COUNT_BIG(*) FROM #cloud_entries WHERE
          order_id IS NULL OR order_id < 1 OR product_id IS NULL OR product_id < 1
          OR add_to_cart_order IS NULL OR add_to_cart_order < 1
          OR reordered IS NULL OR reordered NOT IN (0, 1)),
      (SELECT COUNT_BIG(*) FROM #cloud_products WHERE
          product_id IS NULL OR product_id < 1 OR product_name IS NULL
          OR LTRIM(RTRIM(product_name)) = ''),
      (SELECT COUNT_BIG(*) FROM #cloud_departments WHERE
          department_id IS NULL OR department_id NOT BETWEEN 1 AND 21
          OR department IS NULL OR LTRIM(RTRIM(department)) = '')
        + (SELECT COUNT_BIG(*) FROM #cloud_aisles WHERE
          aisle_id IS NULL OR aisle_id < 1 OR aisle IS NULL OR LTRIM(RTRIM(aisle)) = ''),
      (SELECT COUNT_BIG(*) FROM #cloud_entries AS e WHERE NOT EXISTS
          (SELECT 1 FROM #cloud_products AS p WHERE p.product_id = e.product_id)),
      (SELECT COUNT_BIG(*) FROM #cloud_products AS p WHERE NOT EXISTS
          (SELECT 1 FROM #cloud_aisles AS a WHERE a.aisle_id = p.aisle_id)),
      (SELECT COUNT_BIG(*) FROM #cloud_products AS p WHERE NOT EXISTS
          (SELECT 1 FROM #cloud_departments AS d WHERE d.department_id = p.department_id));
"""


def load_spec(path):
    specification = json.loads(path.read_text(encoding="utf-8-sig"))
    if specification.get("dataset_label") != "instacart_cloud_5000_users_v1":
        raise ValueError("Unexpected cloud subset dataset label.")
    selection = specification["selection"]
    if selection != {"user_limit": 5000, "order_by": "user_id_ascending",
                     "lookup_policy": "all_aisles_and_departments"}:
        raise ValueError("Unexpected subset selection policy.")
    expected = specification["expected_metrics"]
    if set(expected) != set(METRIC_NAMES) or any(type(v) is not int or v < 0 for v in expected.values()):
        raise ValueError("Subset metrics need the complete nonnegative integer contract.")
    if expected["selected_users"] != 5000 or expected["total_orders"] != sum(
        expected[name] for name in ("prior_orders", "train_orders", "test_orders")
    ) or expected["distinct_prior_orders"] != expected["prior_orders"]:
        raise ValueError("Subset counts are inconsistent.")
    for name in METRIC_NAMES[11:]:
        if expected[name] != 0:
            raise ValueError(f"Quality metric must require zero: {name}")
    return specification


def validate_metrics(actual, expected):
    if actual != expected:
        differences = {key: {"expected": value, "actual": actual.get(key)}
                       for key, value in expected.items() if actual.get(key) != value}
        raise ValueError(f"Subset checks failed: {differences}")


def materialize_subset(connection, specification, report):
    """Capture checked session-local tables under serializable source reads."""
    connection.autocommit = False
    try:
        with closing(connection.cursor()) as cursor:
            cursor.execute("SET NOCOUNT ON; SET XACT_ABORT ON; SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;")
            cursor.execute("SELECT DB_NAME(), CAST(SERVERPROPERTY('ServerName') AS NVARCHAR(128));")
            database, server = cursor.fetchone()
            report.update(database=database, server=server)
            # Create the temp table in a direct, unparameterized batch. A table
            # created inside a prepared parameterized batch can disappear when
            # that batch's execution scope ends. Later batches need this table.
            cursor.execute("""
                CREATE TABLE #cloud_users (user_id INT NOT NULL PRIMARY KEY CLUSTERED);
            """)
            # Binding the limit is safe here: this statement fills an existing
            # session-local table rather than creating a shorter-lived one.
            cursor.execute("""
                INSERT INTO #cloud_users (user_id)
                SELECT TOP (?) user_id
                FROM pipeline_staging.orders GROUP BY user_id ORDER BY user_id;
            """, specification["selection"]["user_limit"])
            cursor.execute(SNAPSHOT_SQL)
            cursor.execute(METRICS_SQL)
            report["metrics"] = dict(zip(METRIC_NAMES, cursor.fetchone(), strict=True))
            validate_metrics(report["metrics"], specification["expected_metrics"])
        connection.commit()
        # Committed session-local temp tables remain available on this connection.
        # Source read locks are released before CSV writing begins.
        connection.autocommit = True
        report["capture_status"] = "VALIDATED"
    except Exception:
        try:
            connection.rollback()
        except Exception as error:
            report["rollback_error"] = str(error)
        raise


def fingerprint(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"size_bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def export_csv(cursor, path, header, expected_rows, batch_size=10_000):
    if tuple(column[0] for column in cursor.description) != tuple(header):
        raise ValueError(f"Export SQL column order does not match {path.name}.")
    rows_written = 0
    with path.open("x", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(header)
        while rows := cursor.fetchmany(batch_size):
            writer.writerows(rows)
            rows_written += len(rows)
    if rows_written != expected_rows:
        raise ValueError(f"{path.name}: expected {expected_rows:,} rows, wrote {rows_written:,}.")
    return {"file": path.name, "rows": rows_written, "header": list(header), **fingerprint(path)}


def write_export(connection, specification, output_dir, report):
    """Stage new files, then publish exclusively; manifest is the last file."""
    if output_dir.exists():
        raise FileExistsError("Output directory already exists; choose a new destination.")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    published = []
    reserved = False
    with tempfile.TemporaryDirectory(prefix=".instacart-cloud-", dir=output_dir.parent) as temporary:
        stage = Path(temporary)
        files = []
        with closing(connection.cursor()) as cursor:
            for filename, source, header, order_by, metric in EXPORTS:
                print(f"Exporting {filename}...", flush=True)
                columns = ", ".join(f"[{name}]" for name in header)
                cursor.execute(f"SELECT {columns} FROM {source} ORDER BY {order_by};")
                result = export_csv(cursor, stage / filename, header,
                                    specification["expected_metrics"][metric])
                files.append(result)
                print(f"PASS | {filename} | {result['rows']:,} rows", flush=True)
        manifest = {
            "dataset_label": specification["dataset_label"], "status": "PASS",
            "run_id": report["run_id"], "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "selection": specification["selection"], "source": {
                "schema": "pipeline_staging", "database": report["database"], "server": report["server"],
                "capture": "Serializable reads materialized into checked session-local tables before export",
            },
            "metrics": report["metrics"], "spec_sha256": report["spec_sha256"],
            "script_sha256": report["script_sha256"],
            "format": {"encoding": "utf-8", "delimiter": ",", "header": True,
                       "line_ending": "LF", "null_representation": "empty field"},
            "files": files,
        }
        (stage / "_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        try:
            output_dir.mkdir(exist_ok=False)
            reserved = True
            for filename in [item[0] for item in EXPORTS] + ["_manifest.json"]:
                destination = output_dir / filename
                (stage / filename).replace(destination)
                published.append(destination)
        except Exception:
            # Only remove files created by this invocation, not pre-existing data.
            for path in published:
                path.unlink(missing_ok=True)
            if reserved:
                try:
                    output_dir.rmdir()
                except OSError:
                    pass
            raise
    report["files"] = files
    report["manifest"] = str(output_dir / "_manifest.json")


def main():
    parser = argparse.ArgumentParser(description="Export the checked 5,000-user cloud learning subset.")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    output_dir = args.output_dir.resolve()
    report = {"run_id": uuid4().hex, "started_at_utc": datetime.now(timezone.utc).isoformat(),
              "output_directory": str(output_dir), "status": "ERROR"}
    try:
        if output_dir.is_relative_to(PROJECT_ROOT):
            raise ValueError("Choose an export directory outside the Git repository.")
        if output_dir.exists():
            raise FileExistsError("Output directory already exists; choose a new destination.")
        spec_path = PROJECT_ROOT / "config/cloud_subset_spec.json"
        specification = load_spec(spec_path)
        report.update(dataset_label=specification["dataset_label"],
                      spec_sha256=fingerprint(spec_path)["sha256"],
                      script_sha256=fingerprint(Path(__file__))["sha256"])
        from scripts.db_connection import get_connection

        print("Capturing and checking the 5,000-user SQL subset...", flush=True)
        with closing(get_connection()) as connection:
            materialize_subset(connection, specification, report)
            print("Subset checks passed. Writing CSV files...", flush=True)
            write_export(connection, specification, output_dir, report)
        report["status"] = "PASS"
    except (ValueError, FileExistsError) as error:
        report.update(status="FAIL", error=str(error), error_type=type(error).__name__)
    except Exception as error:
        report.update(status="ERROR", error=str(error), error_type=type(error).__name__)
    report["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["duration_seconds"] = round(time.perf_counter() - started, 3)
    path = PROJECT_ROOT / "logs/cloud_export" / f"{report['run_id']}.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    except OSError as error:
        print(f"ERROR | Could not save export log: {error}")
        if "manifest" in report:
            print(f"Export manifest already published: {report['manifest']}")
        return 1
    print(f"Overall export result: {report['status']}")
    if "error" in report:
        print(f"Reason: {report['error']}")
    if "manifest" in report:
        print(f"Manifest saved: {report['manifest']}")
    print(f"Report saved: {path}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
