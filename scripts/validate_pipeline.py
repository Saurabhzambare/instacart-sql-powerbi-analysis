"""Read-only validation of all five committed automation tables."""

import json
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from scripts.load_departments import TARGET, read_stats, validate_stats
from scripts.load_table import TABLES, read_source_checks


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def validate_tables(connection, report):
    # These are separate read-only checks, not a cross-table snapshot.
    connection.autocommit = True
    report["tables"] = []
    with closing(connection.cursor()) as cursor:
        cursor.execute("SET NOCOUNT ON;")
        cursor.execute("SELECT DB_NAME(), CAST(SERVERPROPERTY('ServerName') AS NVARCHAR(128));")
        database, server = cursor.fetchone()
        report.update(database=database, server=server)

        for table in ("departments", *TABLES):
            result = {"target": f"pipeline_staging.{table}"}
            started = time.perf_counter()
            print(f"Validating {result['target']}...", flush=True)
            try:
                if table == "departments":
                    result["checks"] = read_stats(cursor, TARGET)
                    validate_stats(result["checks"])
                else:
                    result["checks"] = read_source_checks(
                        cursor, TABLES[table], source=f"pipeline_staging.[{table}]"
                    )
                result["status"] = "PASS"
            except ValueError as error:
                result.update(status="FAIL", error=str(error))
            except Exception as error:
                result.update(status="ERROR", error=str(error), error_type=type(error).__name__)
            result["duration_seconds"] = round(time.perf_counter() - started, 3)
            report["tables"].append(result)
            print(f"{result['status']} | {result['target']}", flush=True)
            if "error" in result:
                print(result["error"], flush=True)

    statuses = {result["status"] for result in report["tables"]}
    return "ERROR" if "ERROR" in statuses else "FAIL" if "FAIL" in statuses else "PASS"


def main():
    started = time.perf_counter()
    report = {
        "run_id": uuid4().hex,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Committed pipeline_staging tables; fixed Instacart baseline",
        "consistency": "Separate read-only queries; run without concurrent loaders or edits",
        "tables": [],
    }
    try:
        from scripts.db_connection import get_connection

        with closing(get_connection()) as connection:
            report["status"] = validate_tables(connection, report)
    except Exception as error:
        report.update(status="ERROR", error=str(error), error_type=type(error).__name__)
        print(f"ERROR | {error}", flush=True)

    report["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["duration_seconds"] = round(time.perf_counter() - started, 3)
    path = PROJECT_ROOT / "logs/pipeline_validation" / f"{report['run_id']}.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    except OSError as error:
        print(f"ERROR | Could not save pipeline validation report: {error}")
        return 1
    print(f"Overall automation-table result: {report['status']}")
    print(f"Report saved: {path}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
