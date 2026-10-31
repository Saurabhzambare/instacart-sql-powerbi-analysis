# Input Checks and Fingerprint Baseline

Owner: Saurabh Zambare  
Verified: 31 October 2026

## Purpose

The input checker confirms that the five baseline CSV files exist, are nonempty and have the expected column names in the expected order. It calculates a SHA-256 fingerprint while reading each file in 1 MiB chunks. When a baseline is explicitly supplied, byte size and fingerprint must match the recorded reference.

This is input inspection and file-identity checking. It does not validate every CSV data row, establish CSV record counts, or load data into SQL Server. SHA-256 identifies the selected file bytes; it is not a comparison against an independently published official checksum.

## Files and verified sizes

The current local input directory is `D:\DataProjects\data-download`. The directory is supplied as a command argument rather than embedded in the checker.

| Baseline input | Verified bytes |
| --- | ---: |
| `departments.csv` | 270 |
| `aisles.csv` | 2,603 |
| `products.csv` | 2,166,953 |
| `orders.csv` | 108,968,645 |
| `order_products__prior.csv` | 577,550,706 |

`orders.csv` contains metadata for prior, train and test orders. The separately available `order_products__train.csv` is outside this five-file baseline and remains available for the planned ML extension.

## Configuration and code

- `config/input_manifest.json`: the dataset label, filenames and ordered column lists.
- `config/input_baseline.json`: reference byte sizes, headers and SHA-256 fingerprints, with source run ID and recording timestamp. It does not store the original report's local input-directory path.
- `scripts/check_inputs.py`: input inspection, optional baseline comparison and run-report output.
- `scripts/record_input_baseline.py`: one-time baseline creation from a successful report matching the manifest.
- `tests/test_check_inputs.py` and `tests/test_input_baseline.py`: 15 tests using temporary sample files.

## Run commands

From the repository root, prepare dependencies if needed:

```powershell
uv sync --locked
```

Run the automated tests:

```powershell
uv run python -m unittest discover -s tests -v
```

Inspect inputs without comparing them to a baseline:

```powershell
uv run python -m scripts.check_inputs --data-dir "D:\DataProjects\data-download"
```

Verify input bytes against the recorded baseline:

```powershell
uv run python -m scripts.check_inputs --data-dir "D:\DataProjects\data-download" --baseline "config/input_baseline.json"
```

Check the exit code immediately after a command:

```powershell
$LASTEXITCODE
```

A successful check and report save return 0. File-check failures or configuration/report-write errors return 1. Invalid command-line usage is handled by `argparse` and can return 2.

The `--baseline` option is required to enforce a fingerprint comparison. Without it, changed content with valid headers can pass inspection and receive a new recorded fingerprint.

## Initial baseline creation

The current baseline was recorded from successful inspection run `c582bc5d622b498b965db14b69302cd2`:

```powershell
uv run python -m scripts.record_input_baseline --report "logs/inputs/c582bc5d622b498b965db14b69302cd2.json"
```

This command is for initial creation, not routine runs. It requires a successful report with all expected files, matching headers and valid fingerprint metadata. It uses exclusive file creation and refuses to overwrite an existing baseline.

If inputs differ from the baseline, investigate the change. An intentional dataset update needs a reviewed version/baseline decision; repeatedly creating a baseline from changed files would remove the comparison's purpose. Keep the baseline and manifest together under version control.

## Test coverage

The 15 passing tests cover valid inputs, missing and empty files, incorrect column names/order, UTF-8 byte-order marks, changed fingerprints for same-size edits, matching baseline acceptance, baseline size mismatch, rejection of changed bytes, baseline loading, missing entries, wrong dataset labels, missing baseline files and malformed hashes.

Tests use small temporary files and clean them up afterward. They do not require the original CSVs or a running SQL Server. These tests have been run locally; a GitHub Actions workflow has not yet been added for this milestone.

## Verified baseline comparison

| Verification | Result |
| --- | --- |
| Local automated test suite | 15 tests passed; exit code 0. |
| Initial baseline | Five reference files recorded successfully. |
| Actual CSV comparison | All five files matched headers, byte sizes and fingerprints. |
| Comparison run ID | `f0354211c85942d586f599ef5f2da34a` |
| Overall comparison status | PASS; exit code 0. |

[Saved baseline-comparison evidence](validation_evidence/input_baseline_pass.json)

Reports are generated under `logs/inputs/<run-id>.json`. They include file results and, for a baseline comparison, `baseline_checked: true` and the baseline path. Routine reports are excluded from Git by `logs/`; selected evidence is copied into `docs/validation_evidence/`.

## Next implementation boundary

The next task is a loader that requires the recorded baseline, loads into an isolated project-owned area and validates loaded results. Safe reruns and recovery need to be demonstrated against actual loading behaviour. The existing SQL reporting layer and its separate 18-check validation workflow remain the established analytics baseline.
