"""Transactional baseline loading into pipeline_staging; one table per invocation."""

import argparse
import json
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from scripts.check_inputs import inspect_file, load_baseline
from scripts.table_specs import TABLES


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_TABLE = "#pipeline_input"


class SimulatedLoadFailure(RuntimeError):
    pass


def expected_checks(specification):
    return {
        "rows": specification["rows"], "invalid_rows": 0, "duplicate_key_groups": 0,
        **{name: expected for name, _, expected in specification["aggregates"]},
        **{name: 0 for name, _ in specification["references"]},
    }


def validate_checks(actual, specification):
    expected = expected_checks(specification)
    if actual != expected:
        raise ValueError(f"Loaded-data checks failed. Expected {expected}; got {actual}")


def setup_sql(table, specification):
    def columns(landing):
        return ",\n".join(
            f"[{name}] {sql_type} " + ("NULL" if landing or not required else "NOT NULL")
            for name, sql_type, required, _ in specification["columns"]
        )

    keys = ", ".join(f"[{name}]" for name in specification["keys"])
    return f"""
        IF SCHEMA_ID(N'pipeline_staging') IS NULL
            EXEC(N'CREATE SCHEMA pipeline_staging AUTHORIZATION dbo');
        IF OBJECT_ID(N'pipeline_staging.{table}', N'U') IS NULL
            CREATE TABLE pipeline_staging.[{table}] (
                {columns(False)}, PRIMARY KEY ({keys})
            );
        CREATE TABLE #pipeline_input ({columns(True)});
    """


def bulk_sql(path):
    # filename = str(path).replace("'", "''")
    filename = str(path)
    return f"""
        BULK INSERT #pipeline_input FROM '{filename}'
        WITH (FORMAT = 'CSV', FIRSTROW = 2, FIELDTERMINATOR = ',',
              ROWTERMINATOR = '0x0a', CODEPAGE = '65001', KEEPNULLS, TABLOCK);
    """


def read_source_checks(cursor, specification, source=INPUT_TABLE):
    allowed_sources = {INPUT_TABLE} | {
        f"pipeline_staging.[{table}]"
        for table, contract in TABLES.items() if contract == specification
    }
    if source not in allowed_sources:
        raise ValueError("Unexpected validation source for this table contract.")
    missing = [f"[{name}] IS NULL" for name, _, required, _ in specification["columns"] if required]
    invalid = " OR ".join(f"({condition})" for condition in (*missing, *specification["invalid"]))
    selections = [
        "COUNT_BIG(*)",
        f"COALESCE(SUM(CAST(CASE WHEN {invalid} THEN 1 ELSE 0 END AS BIGINT)), 0)",
        *[expression for _, expression, _ in specification["aggregates"]],
    ]
    names = ("rows", "invalid_rows", *[name for name, _, _ in specification["aggregates"]])
    cursor.execute(f"SELECT {', '.join(selections)} FROM {source};")
    checks = dict(zip(names, cursor.fetchone(), strict=True))
    if checks["rows"] != specification["rows"] or checks["invalid_rows"] != 0:
        raise ValueError(f"Table row count or values failed: {checks}")

    keys = ", ".join(f"[{key}]" for key in specification["keys"])
    cursor.execute(f"""
        SELECT COUNT_BIG(*) FROM (
            SELECT {keys} FROM {source} GROUP BY {keys}
            HAVING COUNT_BIG(*) > 1
        ) AS duplicate_keys;
    """)
    checks["duplicate_key_groups"] = cursor.fetchone()[0]
    for name, query in specification["references"]:
        cursor.execute(query.format(source=source))
        checks[name] = cursor.fetchone()[0]
    validate_checks(checks, specification)
    return checks


def data_differs(cursor, table, specification):
    expressions = [
        f"CONVERT(VARBINARY({binary_length}), [{name}])" if binary_length else f"[{name}]"
        for name, _, _, binary_length in specification["columns"]
    ]
    columns = ", ".join(expressions)
    cursor.execute(f"""
        SELECT CASE WHEN EXISTS (
            SELECT {columns} FROM #pipeline_input
            EXCEPT SELECT {columns} FROM pipeline_staging.[{table}]
        ) OR EXISTS (
            SELECT {columns} FROM pipeline_staging.[{table}]
            EXCEPT SELECT {columns} FROM #pipeline_input
        ) THEN 1 ELSE 0 END;
    """)
    return bool(cursor.fetchone()[0])


def run_load(connection, table, path, manifest_entry, baseline_entry, report, simulate_failure=False):
    specification = TABLES[table]
    connection.autocommit = False
    commit_attempted = False
    report["transaction_outcome"] = "IN_PROGRESS"
    try:
        with closing(connection.cursor()) as cursor:
            cursor.execute("SET NOCOUNT ON; SET XACT_ABORT ON;")
            cursor.execute("SELECT DB_NAME(), CAST(SERVERPROPERTY('ServerName') AS NVARCHAR(128));")
            database, server = cursor.fetchone()
            report.update(database=database, server=server)
            cursor.execute(setup_sql(table, specification))
            print(f"Bulk loading {path.name} into a temporary table...", flush=True)
            cursor.execute(bulk_sql(path))
            print("Checking loaded rows, keys, values and references...", flush=True)
            report["source_checks"] = read_source_checks(cursor, specification)
            report["input_after_bulk"] = inspect_file(path.parent, manifest_entry, baseline_entry)
            if report["input_after_bulk"]["status"] != "PASS":
                raise ValueError("Input fingerprint check failed after bulk loading.")

            cursor.execute(f"SELECT COUNT_BIG(*) FROM pipeline_staging.[{table}] WITH (TABLOCKX, HOLDLOCK);")
            report["target_rows_before"] = cursor.fetchone()[0]
            if simulate_failure:
                if report["target_rows_before"] != specification["rows"] or data_differs(cursor, table, specification):
                    raise ValueError("Run a successful normal load before the failure exercise.")
                cursor.execute(f"DELETE FROM pipeline_staging.[{table}];")
                cursor.execute(f"SELECT COUNT_BIG(*) FROM pipeline_staging.[{table}];")
                report["target_rows_during_failure"] = cursor.fetchone()[0]
                raise SimulatedLoadFailure("Deliberate failure after clearing the automation target, before insert/commit.")

            print("Comparing input and automation target...", flush=True)
            if data_differs(cursor, table, specification):
                columns = ", ".join(f"[{name}]" for name, *_ in specification["columns"])
                cursor.execute(f"DELETE FROM pipeline_staging.[{table}];")
                cursor.execute(f"INSERT INTO pipeline_staging.[{table}] ({columns}) SELECT {columns} FROM #pipeline_input;")
                report.update(action="LOADED", rows_written=specification["rows"])
                if data_differs(cursor, table, specification):
                    raise ValueError("Automation target does not match the loaded input.")
            else:
                report.update(action="UNCHANGED", rows_written=0)

            cursor.execute(f"SELECT COUNT_BIG(*) FROM pipeline_staging.[{table}];")
            report["target_rows_after"] = cursor.fetchone()[0]
            if report["target_rows_after"] != specification["rows"]:
                raise ValueError("Automation target row count does not match the expected count.")

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
    parser = argparse.ArgumentParser(description="Load one baseline table into pipeline_staging.")
    parser.add_argument("--table", required=True, choices=tuple(TABLES))
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--baseline", type=Path, default=Path("config/input_baseline.json"))
    parser.add_argument("--simulate-failure", action="store_true", help="Rollback exercise for aisles/products only.")
    args = parser.parse_args()
    started = time.perf_counter()
    report = {
        "run_id": uuid4().hex,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "target": f"pipeline_staging.{args.table}",
        "simulate_failure": args.simulate_failure,
        "transaction_outcome": "NOT_STARTED",
    }
    try:
        specification = TABLES[args.table]
        if args.simulate_failure and args.table not in ("aisles", "products"):
            raise ValueError("The deliberate clear-and-rollback exercise is limited to aisles/products.")
        manifest = json.loads((PROJECT_ROOT / "config/input_manifest.json").read_text(encoding="utf-8-sig"))
        baseline_path = args.baseline if args.baseline.is_absolute() else PROJECT_ROOT / args.baseline
        entries = load_baseline(baseline_path, manifest["files"], manifest["dataset_label"])
        manifest_entry = next(item for item in manifest["files"] if item["name"] == specification["file"])
        expected_columns = [column[0] for column in specification["columns"]]
        if manifest_entry["columns"] != expected_columns:
            raise ValueError("Input manifest columns do not match the loading contract.")
        path = (args.data_dir / specification["file"]).resolve()
        report.update(dataset_label=manifest["dataset_label"], source_file=str(path))
        report["input_before_bulk"] = inspect_file(path.parent, manifest_entry, entries[path.name])
        if report["input_before_bulk"]["status"] != "PASS":
            raise ValueError(f"Input check failed: {report['input_before_bulk'].get('error')}")

        from scripts.db_connection import get_connection

        print(f"Input fingerprint matched. Loading {args.table}...", flush=True)
        with closing(get_connection()) as connection:
            run_load(connection, args.table, path, manifest_entry, entries[path.name], report, args.simulate_failure)
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
        print(f"Rows in target: {report['target_rows_after']:,}")
    else:
        print(f"Reason: {report['error']}")
    print(f"Target: {report['target']}")
    print(f"Transaction: {report['transaction_outcome']}")
    print(f"Report saved: {report_path}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
