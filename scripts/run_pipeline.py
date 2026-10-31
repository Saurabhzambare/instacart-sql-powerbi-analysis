"""Run baseline checks, transactional loaders and final validation in order."""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_stages(data_dir, baseline):
    common = ["--data-dir", str(data_dir), "--baseline", str(baseline)]
    stages = [
        ("Input baseline", ["scripts.check_inputs", *common]),
        ("Load departments", ["scripts.load_departments", *common]),
        *[(f"Load {table}", ["scripts.load_table", "--table", table, *common])
          for table in ("aisles", "products", "orders", "order_products_prior")],
        ("Validate automation tables", ["scripts.validate_pipeline"]),
    ]
    return [
        {"name": name, "command": [sys.executable, "-u", "-m", *arguments],
         "status": "NOT_RUN", "exit_code": None}
        for name, arguments in stages
    ]


def execute_stage(stage):
    """Stream merged output and retain it, including partial output on errors."""
    environment = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    stage["output"] = ""
    lines = []
    process = None
    try:
        process = subprocess.Popen(
            stage["command"], cwd=PROJECT_ROOT, env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
        )
        for line in process.stdout:
            lines.append(line)
            print(line, end="", flush=True)
        return process.wait()
    finally:
        if process is not None:
            try:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
            finally:
                if process.stdout is not None:
                    process.stdout.close()
        stage["output"] = "".join(lines)
        stage["child_report_paths"] = [
            line.removeprefix("Report saved:").strip()
            for line in lines if line.startswith("Report saved:")
        ]


def write_report(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    temporary_path.replace(path)


def run_pipeline(stages, report_path):
    started = time.perf_counter()
    report = {
        "run_id": report_path.stem,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "RUNNING", "stages": stages,
        "transaction_scope": "Each loader commits separately; no whole-pipeline rollback",
    }
    # Fail before starting any child if the coordinator cannot save its report.
    write_report(report_path, report)
    for stage in stages:
        print(f"\nRunning: {stage['name']}", flush=True)
        stage_started = time.perf_counter()
        stage.update(status="RUNNING", started_at_utc=datetime.now(timezone.utc).isoformat())
        write_report(report_path, report)
        try:
            stage["exit_code"] = execute_stage(stage)
            stage["status"] = "PASS" if stage["exit_code"] == 0 else "FAIL"
        except KeyboardInterrupt:
            stage.update(status="INTERRUPTED", error="Stopped by user; inspect the active loader before rerunning.")
        except Exception as error:
            stage.update(status="ERROR", error=str(error), error_type=type(error).__name__)
        stage["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
        stage["duration_seconds"] = round(time.perf_counter() - stage_started, 3)
        print(f"Stage result: {stage['status']}", flush=True)
        if stage["status"] != "PASS":
            report["status"] = stage["status"]
            report["stopped_at_stage"] = stage["name"]
            break
        write_report(report_path, report)
    else:
        report["status"] = "PASS"
    report["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["duration_seconds"] = round(time.perf_counter() - started, 3)
    write_report(report_path, report)
    return report


def main():
    parser = argparse.ArgumentParser(description="Run the five-table Instacart baseline pipeline.")
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--baseline", type=Path, default=Path("config/input_baseline.json"))
    args = parser.parse_args()
    baseline = args.baseline if args.baseline.is_absolute() else PROJECT_ROOT / args.baseline
    path = PROJECT_ROOT / "logs/pipeline" / f"{uuid4().hex}.json"
    try:
        report = run_pipeline(build_stages(args.data_dir.resolve(), baseline.resolve()), path)
    except OSError as error:
        print(f"ERROR | Could not run pipeline or update its report: {error}")
        print("Remaining stages were not started. Earlier loader commits may remain.")
        return 1
    print(f"\nOverall pipeline result: {report['status']}")
    if report["status"] != "PASS":
        print(f"Stopped at: {report['stopped_at_stage']}")
        print("Later stages: NOT_RUN. Earlier loader commits may remain.")
    print(f"Report saved: {path}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
