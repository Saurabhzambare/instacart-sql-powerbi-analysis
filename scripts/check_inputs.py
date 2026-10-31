import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_baseline(path, specifications, dataset_label):
    baseline = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(baseline, dict):
        raise ValueError("Baseline must be a JSON object.")
    if baseline.get("dataset_label") != dataset_label:
        raise ValueError("Baseline dataset label does not match the manifest.")
    if not isinstance(baseline.get("files"), list):
        raise ValueError("Baseline must contain a files list.")

    entries = {}
    for entry in baseline["files"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("file"), str):
            raise ValueError("Each baseline entry needs a filename.")
        name = entry["file"]
        if name in entries:
            raise ValueError(f"Duplicate baseline filename: {name}")
        digest = entry.get("sha256")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError(f"Invalid SHA-256 in baseline: {name}")
        if type(entry.get("size_bytes")) is not int or entry["size_bytes"] <= 0:
            raise ValueError(f"Invalid byte size in baseline: {name}")
        entries[name] = entry

    if set(entries) != {specification["name"] for specification in specifications}:
        raise ValueError("Baseline filenames do not exactly match the manifest.")
    for specification in specifications:
        if entries[specification["name"]].get("header") != specification["columns"]:
            raise ValueError(f"Baseline header mismatch: {specification['name']}")
    return entries


def inspect_file(data_directory, specification, baseline_entry=None):
    path = data_directory / specification["name"]
    result = {"file": specification["name"], "status": "FAIL"}

    try:
        before = path.stat()
        result["size_bytes"] = before.st_size
        if before.st_size == 0:
            raise ValueError("File is empty.")

        with path.open("r", encoding="utf-8-sig", newline="") as source:
            header = next(csv.reader(source, strict=True), [])
        result["header"] = header
        if header != specification["columns"]:
            raise ValueError(
                f"Header mismatch. Expected: {specification['columns']}; "
                f"actual: {header}"
            )

        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)

        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (
            after.st_size, after.st_mtime_ns
        ):
            raise ValueError("File changed during inspection. Rerun with stable inputs.")

        result["sha256"] = digest.hexdigest()
        if baseline_entry is not None:
            result["expected_size_bytes"] = baseline_entry["size_bytes"]
            result["expected_sha256"] = baseline_entry["sha256"]
            if (
                result["size_bytes"] != baseline_entry["size_bytes"]
                or result["sha256"] != baseline_entry["sha256"]
            ):
                raise ValueError("Input differs from the recorded baseline.")
        result["status"] = "PASS"
    except (OSError, UnicodeError, csv.Error, ValueError) as error:
        result["error"] = str(error)

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Check baseline CSV files and record their fingerprints."
    )
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument(
        "--baseline", type=Path,
        help="Require input bytes to match this recorded JSON baseline.",
    )
    args = parser.parse_args()

    baseline_path = None
    baseline_entries = {}
    try:
        manifest_path = PROJECT_ROOT / "config" / "input_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        specifications = manifest["files"]
        if not isinstance(specifications, list) or not specifications:
            raise ValueError("Manifest must contain a nonempty files list.")
        for specification in specifications:
            if (
                not isinstance(specification["name"], str)
                or not isinstance(specification["columns"], list)
                or not specification["columns"]
            ):
                raise ValueError("Each manifest entry needs a filename and columns.")
        if args.baseline is not None:
            baseline_path = (
                args.baseline if args.baseline.is_absolute()
                else PROJECT_ROOT / args.baseline
            )
            baseline_entries = load_baseline(
                baseline_path, specifications, manifest.get("dataset_label")
            )
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
        print(f"ERROR | Could not read input configuration: {error}")
        return 1

    report = {
        "run_id": uuid4().hex,
        "dataset_label": manifest.get("dataset_label"),
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_directory": str(args.data_dir.resolve()),
        "baseline_checked": baseline_path is not None,
        "baseline_path": str(baseline_path) if baseline_path is not None else None,
        "files": [],
    }

    for specification in specifications:
        print(f"Checking and fingerprinting {specification['name']}...", flush=True)
        result = inspect_file(
            args.data_dir, specification, baseline_entries.get(specification["name"])
        )
        report["files"].append(result)
        detail = (
            f"{result['size_bytes']:,} bytes; header matched; "
            + ("fingerprint matched baseline" if baseline_path is not None
               else "SHA-256 recorded")
            if result["status"] == "PASS" else result["error"]
        )
        print(f"{result['status']} | {result['file']} | {detail}", flush=True)

    passed = all(result["status"] == "PASS" for result in report["files"])
    report["status"] = "PASS" if passed else "FAIL"
    report["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
    report_path = PROJECT_ROOT / "logs" / "inputs" / f"{report['run_id']}.json"

    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    except OSError as error:
        print(f"ERROR | Could not save input report: {error}")
        return 1

    print(f"\nOverall input result: {report['status']}")
    print(f"Report saved: {report_path}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
