"""Transactionally publish the validated 5,000-user cohort's target purchases."""

import argparse
import json
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from scripts.check_ml_train_labels import bulk_sql, check_input, load_spec, read_checks


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET = "pipeline_ml.train_labels_5000_users_v1"
EXPECTED_TABLE = "#ml_expected_labels"
COLUMNS = ("user_id", "order_id", "product_id", "add_to_cart_order", "source_reordered")
COLUMN_SQL = ", ".join(f"[{name}]" for name in COLUMNS)
OBSERVATIONS = ("label_entries", "target_orders", "distinct_products", "historically_reordered_entries")


class SimulatedMLLoadFailure(RuntimeError):
    """Expected failure after clearing a previously verified target, before commit."""


def load_publication_spec(path, input_spec):
    spec = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(spec, dict):
        raise ValueError("ML publication contract must be an object.")
    identities = {
        "dataset_label": input_spec["subset"]["dataset_label"],
        "source_dataset_label": input_spec["dataset_label"],
        "source_sha256": input_spec["sha256"],
        "target": TARGET,
        "selected_users": input_spec["subset"]["selected_users"],
        "selected_train_users": input_spec["subset"]["selected_train_users"],
    }
    if any(spec.get(key) != value for key, value in identities.items()):
        raise ValueError("ML publication identity differs from the input contract or fixed target.")
    for name in ("selected_users", "selected_train_users", *OBSERVATIONS):
        if type(spec.get(name)) is not int or spec[name] < (0 if name == "historically_reordered_entries" else 1):
            raise ValueError(f"Invalid ML publication count: {name}")
    if (
        spec["target_orders"] != spec["selected_train_users"]
        or not spec["target_orders"] <= spec["label_entries"] <= input_spec["rows"]
        or spec["distinct_products"] > spec["label_entries"]
        or spec["historically_reordered_entries"] > spec["label_entries"]
    ):
        raise ValueError("Inconsistent ML publication counts.")
    return spec


def require_observations(observations, spec):
    expected = {name: spec[name] for name in OBSERVATIONS}
    if observations != expected:
        raise ValueError(f"Selected labels differ from accepted observations: {observations}; expected {expected}")


def prepare_expected(cursor):
    # Plain session-scoped CREATE statements deliberately have no SQL parameters.
    cursor.execute("""
        CREATE TABLE #ml_expected_labels (
            user_id INT NOT NULL, order_id INT NOT NULL,
            product_id INT NOT NULL, add_to_cart_order INT NOT NULL,
            source_reordered INT NOT NULL,
            PRIMARY KEY (order_id, product_id),
            UNIQUE (order_id, add_to_cart_order)
        );
    """)
    cursor.execute("""
        INSERT INTO #ml_expected_labels
            (user_id, order_id, product_id, add_to_cart_order, source_reordered)
        SELECT o.user_id, l.order_id, l.product_id, l.add_to_cart_order, l.reordered
        FROM #ml_train_input AS l
        INNER JOIN pipeline_staging.orders AS o ON o.order_id = l.order_id
        INNER JOIN #ml_selected_users AS u ON u.user_id = o.user_id
        WHERE o.eval_set = 'train';
    """)


def read_metrics(cursor, source):
    if source not in (EXPECTED_TABLE, TARGET):
        raise ValueError("Unapproved ML metric source.")
    cursor.execute(f"""
        SELECT COUNT_BIG(*), COUNT_BIG(DISTINCT user_id),
            COUNT_BIG(DISTINCT order_id), COUNT_BIG(DISTINCT product_id),
            COALESCE(SUM(CAST(source_reordered AS BIGINT)), 0)
        FROM {source};
    """)
    return dict(zip(("label_entries", "selected_train_users", "target_orders",
                     "distinct_products", "historically_reordered_entries"),
                    cursor.fetchone(), strict=True))


def require_metrics(metrics, spec):
    expected = {key: spec[key] for key in ("label_entries", "selected_train_users", *OBSERVATIONS[1:])}
    if metrics != expected:
        raise ValueError(f"ML table metrics differ: {metrics}; expected {expected}")


def acquire_publication_lock(cursor):
    cursor.execute("""
        DECLARE @lock_result INT;
        EXEC @lock_result = sys.sp_getapplock
            @Resource = N'instacart_ml_train_labels_5000_users_v1',
            @LockMode = 'Exclusive', @LockOwner = 'Transaction', @LockTimeout = 15000;
        SELECT @lock_result;
    """)
    if cursor.fetchone()[0] < 0:
        raise RuntimeError("Could not acquire the ML publication lock; target not changed.")


def ensure_target(cursor):
    cursor.execute("""
        IF SCHEMA_ID(N'pipeline_ml') IS NULL
            EXEC(N'CREATE SCHEMA pipeline_ml AUTHORIZATION dbo');
        IF OBJECT_ID(N'pipeline_ml.train_labels_5000_users_v1', N'U') IS NULL
            CREATE TABLE pipeline_ml.train_labels_5000_users_v1 (
                user_id INT NOT NULL CHECK (user_id > 0),
                order_id INT NOT NULL CHECK (order_id > 0),
                product_id INT NOT NULL CHECK (product_id > 0),
                add_to_cart_order INT NOT NULL CHECK (add_to_cart_order > 0),
                source_reordered INT NOT NULL CHECK (source_reordered IN (0, 1)),
                PRIMARY KEY (order_id, product_id),
                UNIQUE (order_id, add_to_cart_order)
            );
    """)
    # Reject an unexpected pre-existing table instead of attempting to reshape it.
    cursor.execute("""
        SELECT name, TYPE_NAME(user_type_id), is_nullable, is_identity, is_computed
        FROM sys.columns
        WHERE object_id = OBJECT_ID(N'pipeline_ml.train_labels_5000_users_v1', N'U')
        ORDER BY column_id;
    """)
    if [tuple(row) for row in cursor.fetchall()] != [(name, "int", False, False, False) for name in COLUMNS]:
        raise ValueError("Existing ML target has an unexpected column definition.")
    cursor.execute("""
        SELECT i.is_primary_key, i.is_unique,
            STRING_AGG(CONVERT(NVARCHAR(MAX), c.name), N',')
                WITHIN GROUP (ORDER BY ic.key_ordinal)
        FROM sys.indexes AS i
        INNER JOIN sys.index_columns AS ic
            ON ic.object_id = i.object_id AND ic.index_id = i.index_id
        INNER JOIN sys.columns AS c
            ON c.object_id = ic.object_id AND c.column_id = ic.column_id
        WHERE i.object_id = OBJECT_ID(N'pipeline_ml.train_labels_5000_users_v1', N'U')
            AND i.is_unique = 1 AND i.is_disabled = 0 AND i.has_filter = 0
            AND ic.key_ordinal > 0
        GROUP BY i.index_id, i.is_primary_key, i.is_unique;
    """)
    keys = {tuple(row) for row in cursor.fetchall()}
    if not {(True, True, "order_id,product_id"), (False, True, "order_id,add_to_cart_order")} <= keys:
        raise ValueError("Existing ML target is missing its expected unique keys.")


def data_differs(cursor):
    cursor.execute(f"""
        SELECT CASE WHEN EXISTS (
            SELECT {COLUMN_SQL} FROM {EXPECTED_TABLE}
            EXCEPT SELECT {COLUMN_SQL} FROM {TARGET}
        ) OR EXISTS (
            SELECT {COLUMN_SQL} FROM {TARGET}
            EXCEPT SELECT {COLUMN_SQL} FROM {EXPECTED_TABLE}
        ) THEN 1 ELSE 0 END;
    """)
    return bool(cursor.fetchone()[0])


def run_load(connection, path, input_spec, publication_spec, report, simulate_failure=False):
    connection.autocommit = False
    commit_attempted = False
    report.update(transaction_outcome="IN_PROGRESS", target=TARGET,
                  action="NOT_PUBLISHED", rows_written=0, target_write_attempted=False)
    try:
        with closing(connection.cursor()) as cursor:
            cursor.execute("SET NOCOUNT ON; SET XACT_ABORT ON; SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;")
            cursor.execute("SELECT DB_NAME(), CAST(SERVERPROPERTY('ServerName') AS NVARCHAR(128));")
            report["database"], report["server"] = cursor.fetchone()
            cursor.execute("""
                CREATE TABLE #ml_train_input (
                    order_id INT NULL, product_id INT NULL,
                    add_to_cart_order INT NULL, reordered INT NULL
                );
            """)
            print("Bulk loading and validating the full training-label file...", flush=True)
            cursor.execute(bulk_sql(path))
            report["input_after_bulk"] = check_input(path, input_spec)
            read_checks(cursor, input_spec, report)
            require_observations(report["selected_label_observations"], publication_spec)
            prepare_expected(cursor)
            report["expected_metrics"] = read_metrics(cursor, EXPECTED_TABLE)
            require_metrics(report["expected_metrics"], publication_spec)

            acquire_publication_lock(cursor)
            ensure_target(cursor)
            cursor.execute(f"SELECT COUNT_BIG(*) FROM {TARGET} WITH (TABLOCKX, HOLDLOCK);")
            before = report["target_rows_before"] = cursor.fetchone()[0]
            differs = data_differs(cursor)
            if simulate_failure:
                if before != publication_spec["label_entries"] or differs:
                    raise ValueError("Rollback exercise requires an existing target that exactly matches validated labels.")
                report.update(action="SIMULATED_FAILURE", target_write_attempted=True)
                cursor.execute(f"DELETE FROM {TARGET};")
                raise SimulatedMLLoadFailure("Deliberate failure after clearing the ML target; rollback requested.")

            if before != publication_spec["label_entries"] or differs:
                report.update(action="REPLACED", target_write_attempted=True)
                cursor.execute(f"DELETE FROM {TARGET};")
                cursor.execute(f"INSERT INTO {TARGET} ({COLUMN_SQL}) SELECT {COLUMN_SQL} FROM {EXPECTED_TABLE};")
                report["rows_inserted_in_transaction"] = publication_spec["label_entries"]
            else:
                report["action"] = "UNCHANGED"

            report["target_metrics"] = read_metrics(cursor, TARGET)
            require_metrics(report["target_metrics"], publication_spec)
            if data_differs(cursor):
                raise ValueError("Published ML rows do not exactly match the validated selected labels.")
        commit_attempted = True
        connection.commit()
        report["transaction_outcome"] = "COMMITTED"
        report["rows_written"] = report.get("rows_inserted_in_transaction", 0)
    except Exception:
        report["transaction_outcome"] = "UNKNOWN"
        try:
            connection.rollback()
            if not commit_attempted:
                report["transaction_outcome"] = "ROLLED_BACK"
        except Exception as error:
            report["rollback_error"] = str(error)
        # An unknown commit outcome must never be described as zero writes.
        report["rows_written"] = None if commit_attempted or report["transaction_outcome"] == "UNKNOWN" else 0
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--input-spec", type=Path, default=Path("config/ml_train_labels_spec.json"))
    parser.add_argument("--load-spec", type=Path, default=Path("config/ml_train_labels_load_spec.json"))
    parser.add_argument("--simulate-failure", action="store_true",
                        help="Clear-and-rollback exercise; requires an already correct target.")
    args = parser.parse_args()
    started = time.perf_counter()
    report = dict(run_id=uuid4().hex, started_at_utc=datetime.now(timezone.utc).isoformat(),
                  target=TARGET, transaction_outcome="NOT_STARTED", action="NOT_PUBLISHED",
                  rows_written=0, target_write_attempted=False, simulate_failure=args.simulate_failure)
    try:
        resolve = lambda path: path if path.is_absolute() else PROJECT_ROOT / path
        input_spec = load_spec(resolve(args.input_spec))
        publication_spec = load_publication_spec(resolve(args.load_spec), input_spec)
        path = (args.data_dir / input_spec["file"]).resolve()
        report.update(dataset_label=publication_spec["dataset_label"],
                      source_file=str(path), input_specification=str(resolve(args.input_spec)),
                      load_specification=str(resolve(args.load_spec)), source_sha256=input_spec["sha256"],
                      expected_selected_label_observations={name: publication_spec[name] for name in OBSERVATIONS})
        report["input_before_bulk"] = check_input(path, input_spec)
        from scripts.db_connection import get_connection

        with closing(get_connection()) as connection:
            run_load(connection, path, input_spec, publication_spec, report, args.simulate_failure)
        report["status"] = "PASS"
    except (ValueError, SimulatedMLLoadFailure) as error:
        report.update(status="FAIL", error=str(error), error_type=type(error).__name__)
    except Exception as error:
        report.update(status="ERROR", error=str(error), error_type=type(error).__name__)
    report.update(ended_at_utc=datetime.now(timezone.utc).isoformat(),
                  duration_seconds=round(time.perf_counter() - started, 3))
    report_path = PROJECT_ROOT / "logs/ml_loading" / f"{report['run_id']}.json"
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    except OSError as error:
        print(f"ERROR | Could not save ML load report: {error}")
        print(f"Database transaction outcome: {report['transaction_outcome']}")
        return 1
    print(f"Result: {report['status']}")
    print(f"Action: {report['action']}")
    print(f"Target: {TARGET}")
    if report["status"] == "PASS":
        print(f"Rows in target: {report['target_metrics']['label_entries']:,}")
    else:
        print(f"Reason: {report['error']}")
    print(f"Rows written: {report['rows_written'] if report['rows_written'] is not None else 'UNKNOWN'}")
    print(f"Transaction: {report['transaction_outcome']}")
    print(f"Report saved: {report_path}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
