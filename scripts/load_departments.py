import argparse
import json
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from scripts.check_inputs import inspect_file, load_baseline


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET = "pipeline_staging.departments"
INPUT_TABLE = "#departments_input"
STAT_NAMES = ("rows", "unique_ids", "missing_ids", "blank_names", "invalid_ids")
EXPECTED_STATS = dict(zip(STAT_NAMES, (21, 21, 0, 0, 0)))


class SimulatedLoadFailure(RuntimeError):
    pass


def validate_stats(stats):
    if stats != EXPECTED_STATS:
        raise ValueError(f"Department checks failed. Expected {EXPECTED_STATS}; got {stats}")


def bulk_sql(path):
    # SQL Server's BULK INSERT filename requires a SQL string literal.
    filename = str(path).replace("'", "''")
    return f"""
        BULK INSERT #departments_input
        FROM '{filename}'
        WITH (
            FORMAT = 'CSV', FIRSTROW = 2, FIELDTERMINATOR = ',',
            ROWTERMINATOR = '0x0a', CODEPAGE = '65001'
        );
    """


def read_stats(cursor, table):
    if table not in (INPUT_TABLE, TARGET):
        raise ValueError("Unexpected department table.")
    cursor.execute(f"""
        SELECT
            COUNT_BIG(*),
            COUNT_BIG(DISTINCT department_id),
            COALESCE(SUM(CASE WHEN department_id IS NULL THEN 1 ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN department IS NULL
                OR LTRIM(RTRIM(department)) = '' THEN 1 ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN department_id NOT BETWEEN 1 AND 21
                THEN 1 ELSE 0 END), 0)
        FROM {table};
    """)
    return dict(zip(STAT_NAMES, cursor.fetchone(), strict=True))


def data_differs(cursor):
    # Binary conversion makes case and trailing-space differences observable.
    cursor.execute("""
        SELECT CASE WHEN EXISTS (
            SELECT department_id, CONVERT(VARBINARY(100), department)
            FROM #departments_input
            EXCEPT
            SELECT department_id, CONVERT(VARBINARY(100), department)
            FROM pipeline_staging.departments
        ) OR EXISTS (
            SELECT department_id, CONVERT(VARBINARY(100), department)
            FROM pipeline_staging.departments
            EXCEPT
            SELECT department_id, CONVERT(VARBINARY(100), department)
            FROM #departments_input
        ) THEN 1 ELSE 0 END;
    """)
    return bool(cursor.fetchone()[0])


def run_load(connection, path, specification, baseline_entry, report, simulate_failure=False):
    connection.autocommit = False
    commit_attempted = False
    report["transaction_outcome"] = "IN_PROGRESS"

    try:
        with closing(connection.cursor()) as cursor:
            cursor.execute("SET NOCOUNT ON; SET XACT_ABORT ON;")
            cursor.execute("SELECT DB_NAME(), CAST(SERVERPROPERTY('ServerName') AS NVARCHAR(128));")
            database, server = cursor.fetchone()
            report.update(database=database, server=server)

            cursor.execute("""
                IF SCHEMA_ID(N'pipeline_staging') IS NULL
                    EXEC(N'CREATE SCHEMA pipeline_staging AUTHORIZATION dbo');
                IF OBJECT_ID(N'pipeline_staging.departments', N'U') IS NULL
                    CREATE TABLE pipeline_staging.departments (
                        department_id INT NOT NULL PRIMARY KEY,
                        department VARCHAR(100) NOT NULL
                    );
                CREATE TABLE #departments_input (
                    department_id INT NULL,
                    department VARCHAR(100) NULL
                );
            """)

            cursor.execute(bulk_sql(path))
            report["input_row_checks"] = read_stats(cursor, INPUT_TABLE)
            validate_stats(report["input_row_checks"])

            # Recheck the file after SQL Server has read it.
            report["input_after_bulk"] = inspect_file(path.parent, specification, baseline_entry)
            if report["input_after_bulk"]["status"] != "PASS":
                raise ValueError("Input fingerprint check failed after bulk loading.")

            cursor.execute("SELECT COUNT_BIG(*) FROM pipeline_staging.departments WITH (TABLOCKX, HOLDLOCK);")
            report["target_rows_before"] = cursor.fetchone()[0]

            if simulate_failure:
                # This exercise is only allowed after a valid initial load.
                validate_stats(read_stats(cursor, TARGET))
                cursor.execute("DELETE FROM pipeline_staging.departments;")
                cursor.execute("SELECT COUNT_BIG(*) FROM pipeline_staging.departments;")
                report["target_rows_during_failure"] = cursor.fetchone()[0]
                raise SimulatedLoadFailure("Deliberate failure after clearing the automation target, before insert/commit.")

            if data_differs(cursor):
                cursor.execute("DELETE FROM pipeline_staging.departments;")
                cursor.execute("""
                    INSERT INTO pipeline_staging.departments (department_id, department)
                    SELECT department_id, department FROM #departments_input;
                """)
                report.update(action="LOADED", rows_written=21)
            else:
                report.update(action="UNCHANGED", rows_written=0)

            report["target_row_checks"] = read_stats(cursor, TARGET)
            validate_stats(report["target_row_checks"])
            if data_differs(cursor):
                raise ValueError("Automation target does not match the loaded input.")

        commit_attempted = True
        connection.commit()
        report["transaction_outcome"] = "COMMITTED"
    except Exception:
        # A commit exception can have an uncertain outcome; never claim rollback
        # proves a commit did not happen if the commit itself raised an error.
        report["transaction_outcome"] = "UNKNOWN"
        try:
            connection.rollback()
            if not commit_attempted:
                report["transaction_outcome"] = "ROLLED_BACK"
        except Exception as rollback_error:
            report["rollback_error"] = str(rollback_error)
        raise


def main():
    parser = argparse.ArgumentParser(description="Load the 21-department baseline into an automation table.")
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--baseline", type=Path, default=Path("config/input_baseline.json"))
    parser.add_argument("--simulate-failure", action="store_true", help="Exercise rollback after a valid initial load.")
    args = parser.parse_args()
    started = time.perf_counter()
    report = {
        "run_id": uuid4().hex,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "target": TARGET,
        "simulate_failure": args.simulate_failure,
        "transaction_outcome": "NOT_STARTED",
    }

    try:
        manifest = json.loads((PROJECT_ROOT / "config/input_manifest.json").read_text(encoding="utf-8-sig"))
        baseline_path = args.baseline if args.baseline.is_absolute() else PROJECT_ROOT / args.baseline
        entries = load_baseline(baseline_path, manifest["files"], manifest["dataset_label"])
        specification = next(item for item in manifest["files"] if item["name"] == "departments.csv")
        path = (args.data_dir / specification["name"]).resolve()
        report.update(dataset_label=manifest["dataset_label"], source_file=str(path))
        report["input_before_bulk"] = inspect_file(path.parent, specification, entries[path.name])
        if report["input_before_bulk"]["status"] != "PASS":
            raise ValueError(f"Input check failed: {report['input_before_bulk'].get('error')}")

        print("Input fingerprint matched. Starting departments load...", flush=True)
        # Deferred import allows pure/mocked loader tests without a database driver.
        from scripts.db_connection import get_connection

        with closing(get_connection()) as connection:
            run_load(connection, path, specification, entries[path.name], report, args.simulate_failure)
        report["status"] = "PASS"
    except (ValueError, SimulatedLoadFailure) as error:
        report.update(status="FAIL", error=str(error), error_type=type(error).__name__)
    except Exception as error:
        report.update(status="ERROR", error=str(error), error_type=type(error).__name__)

    report["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["duration_seconds"] = round(time.perf_counter() - started, 3)
    report_path = PROJECT_ROOT / "logs/loading" / f"{report['run_id']}.json"
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    except OSError as error:
        print(f"ERROR | Could not save load report: {error}")
        print(f"Database transaction outcome: {report['transaction_outcome']}")
        return 1

    print(f"Result: {report['status']}")
    if report["status"] == "PASS":
        print(f"Action: {report['action']}")
        print(f"Target: {TARGET}")
        print(f"Rows in target: {report['target_row_checks']['rows']}")
    else:
        print(f"Reason: {report['error']}")
    print(f"Transaction: {report['transaction_outcome']}")
    print(f"Report saved: {report_path}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
