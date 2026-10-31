import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.check_inputs import load_baseline


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(
        description="Record fingerprints from a successful input inspection."
    )
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    report_path = args.report if args.report.is_absolute() else PROJECT_ROOT / args.report
    output_path = PROJECT_ROOT / "config" / "input_baseline.json"

    try:
        manifest = json.loads(
            (PROJECT_ROOT / "config/input_manifest.json").read_text(encoding="utf-8-sig")
        )
        source = json.loads(report_path.read_text(encoding="utf-8-sig"))
        entries = load_baseline(report_path, manifest["files"], manifest["dataset_label"])
        if source.get("status") != "PASS" or any(
            entry.get("status") != "PASS" for entry in entries.values()
        ):
            raise ValueError("Only a successful input report can become a baseline.")

        baseline = {
            "dataset_label": manifest["dataset_label"],
            "source_run_id": source["run_id"],
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "files": [
                {
                    key: entries[specification["name"]][key]
                    for key in ("file", "size_bytes", "header", "sha256")
                }
                for specification in manifest["files"]
            ],
        }

        # Exclusive creation prevents silently replacing an existing baseline.
        with output_path.open("x", encoding="utf-8") as output:
            json.dump(baseline, output, indent=2)
            output.write("\n")
    except FileExistsError:
        print("ERROR | Input baseline already exists; no changes made.")
        return 1
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
        print(f"ERROR | Could not record input baseline: {error}")
        return 1

    print(f"Recorded baseline for {len(baseline['files'])} files.")
    print(f"Baseline saved: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
