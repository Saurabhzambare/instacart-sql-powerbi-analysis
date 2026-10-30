import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[1]

VALIDATORS = (
    ("Row counts", "scripts.validate_row_counts"),
    ("Required IDs", "scripts.validate_required_ids"),
    ("Unique keys", "scripts.validate_unique_keys"),
    ("Relationships", "scripts.validate_relationships"),
    ("Valid values", "scripts.validate_values"),
)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def main():
    started = time.perf_counter()
    report = {
        "run_id": uuid4().hex,
        "started_at_utc": utc_now(),
        "groups": [],
    }

    for name, module in VALIDATORS:
        print(f"\nRunning: {name}", flush=True)
        group_started = time.perf_counter()
        group = {
            "name": name,
            "module": module,
            "started_at_utc": utc_now(),
        }

        try:
            result = subprocess.run(
                [sys.executable, "-m", module],
                cwd=PROJECT_ROOT,
                env=os.environ | {"PYTHONIOENCODING": "utf-8"},
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            group.update(
                status="PASS" if result.returncode == 0 else "FAIL",
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        except OSError as error:
            group.update(
                status="ERROR",
                exit_code=None,
                stdout="",
                stderr=str(error),
            )

        group["ended_at_utc"] = utc_now()
        group["duration_seconds"] = round(
            time.perf_counter() - group_started, 3
        )
        report["groups"].append(group)

        if group["stdout"]:
            print(group["stdout"], end="")
        if group["stderr"]:
            print(group["stderr"], end="\n")

        print(f"Group result: {group['status']}", flush=True)

    statuses = [group["status"] for group in report["groups"]]
    report["status"] = (
        "ERROR" if "ERROR" in statuses else
        "FAIL" if "FAIL" in statuses else "PASS"
    )
    report["ended_at_utc"] = utc_now()
    report["duration_seconds"] = round(
        time.perf_counter() - started, 3
    )

    report_path = (
        PROJECT_ROOT / "logs" / "validation"
        / f"{report['run_id']}.json"
    )

    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2),
            encoding="utf-8",
        )
    except OSError as error:
        print(f"ERROR | Could not save run report: {error}")
        return 1

    print(f"\nOverall result: {report['status']}")
    print(f"Report saved: {report_path}")

    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())