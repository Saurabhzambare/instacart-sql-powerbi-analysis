# Automated Reporting Validation

Owner: Saurabh Zambare  
Verified: 30 October 2026

## Purpose and scope

This workflow runs 18 read-only SQL checks against the three reporting views in `InstacartAnalytics`. Python compares the query results with the validation rules and saves a JSON run report. SQL Server performs the queries; the full dataset is not loaded into Python memory.

The workflow validates an existing reporting layer. Automated CSV loading, source-table validation, CI, cloud workflows and machine learning are separate roadmap items. Passing these checks establishes the listed properties, rather than proving every possible aspect of data correctness.

## Requirements and setup

- Windows with Python 3.14 and uv.
- Microsoft ODBC Driver 18 for SQL Server.
- A running SQL Server instance containing the project's existing reporting views.
- A Windows account with permission to connect and query those views.

From the repository root, recreate the Python environment:

```powershell
uv sync --locked
```

Dependencies are declared in `pyproject.toml` and resolved in `uv.lock`. The local `.venv` directory is excluded from Git.

The connection defaults to server `localhost` and database `InstacartAnalytics`. Optional PowerShell overrides apply to the current terminal session:

```powershell
$env:INSTACART_SQL_SERVER = 'YOUR_SERVER_NAME'
$env:INSTACART_SQL_DATABASE = 'InstacartAnalytics'
```

The local connection uses Windows Authentication and requests encryption with `TrustServerCertificate=yes`, which skips server-certificate validation. This configuration describes the local learning environment.

## Run and inspect

Run all validation groups:

```powershell
uv run python -m scripts.run_validations
```

Immediately inspect the process exit code:

```powershell
$LASTEXITCODE
```

Individual groups can also run independently:

```powershell
uv run python -m scripts.validate_row_counts
uv run python -m scripts.validate_required_ids
uv run python -m scripts.validate_unique_keys
uv run python -m scripts.validate_relationships
uv run python -m scripts.validate_values
```

Run these commands from the repository root. The `scripts` directory is a Python package, and the validators share `scripts/db_connection.py`.

## Validation rules

| Group | Checks | Passing rule |
| --- | ---: | --- |
| Row counts | 3 | Products: 49,688; prior orders: 3,214,874; order-product entries: 32,434,489. |
| Required IDs | 3 | No missing product IDs; no missing order/user IDs; no missing order/product IDs in entries. |
| Unique keys | 3 | No duplicate product IDs, order IDs or order-product pairs. |
| Relationships | 2 | Every order-product entry matches a product and an order in the reporting views. |
| Valid values | 7 | Rules listed below. |
| Total | 18 | All five groups pass. |

Value checks require:

1. A non-null order hour between 0 and 23.
2. A non-null day code between 0 and 6. No weekday-name mapping is assumed.
3. A non-null order number of at least 1.
4. A non-null reordered flag of 0 or 1.
5. A non-null add-to-cart position of at least 1.
6. A null previous-order gap for a first order, a non-null gap for later orders, and any non-null gap within 0–30 days. Zero is valid; 30 is the dataset's capped value.
7. A non-null basket size of at least 1.

Fixed row counts belong to this dataset snapshot and should not be changed simply to make a failed run pass. An intentional dataset change requires a reviewed baseline update. Duplicate checks count duplicate key groups, not the number of extra rows.

## Reports and status behaviour

Each completed runner invocation creates a separate file:

```text
logs/validation/<run-id>.json
```

The report contains a unique run ID, UTC start/end timestamps, elapsed time, overall status and a list of validation groups. Each group records its module, status, exit code, timings, standard output and error output. Individual query results are preserved in the group's output text; they are not separate structured JSON check records.

- `PASS`: every group returned 0.
- `FAIL`: a child process returned a nonzero exit code. This can indicate a rule mismatch or an error reported by that validator; inspect its output.
- `ERROR`: the runner could not start a child process.
- Runner exit code 0: all groups passed and the report was saved.
- Runner exit code 1: validation failed, a launch error occurred or the report could not be saved. A report-write failure is printed to the terminal.

The runner continues through all five groups after a group failure. Group output is displayed after that group finishes. The current runner does not guarantee a completed report following manual interruption.

Generated reports remain local under the ignored `logs/` directory. Selected evidence copies are stored under `docs/validation_evidence/` for this milestone.

## Verified failure-and-recovery exercise

The exercise changed only the expected product count in Python. No database rows were changed.

| Run | Run ID | Result |
| --- | --- | --- |
| Initial combined run | `7a0d0a2d2b5947d1b8486eeceb58bdef` | All 18 checks passed; runner exit code 0. |
| Deliberate mismatch | `cfe1db95585e41cf95014893047b0a3e` | Expected 49,689 products; actual 49,688. Row counts failed; the other four groups passed. Overall FAIL; runner exit code 1. |
| Recovery | `c38059380fd64134ba2037ba8bb4c10b` | Expected count restored to 49,688. All 18 checks passed. Overall PASS; runner exit code 0. |

The failed run's saved JSON was inspected in PowerShell and confirmed the same group statuses and exit codes as the runner's result.

Selected evidence:

- [Count-mismatch failure report](validation_evidence/failure_count_mismatch.json)
- [Recovery report](validation_evidence/recovery_pass.json)

### Troubleshooting

1. Read the failed group's standard and error output in the JSON report.
2. For connection errors, check the server name, database availability, ODBC driver and Windows account permissions.
3. For rule failures, investigate the corresponding SQL query and underlying data before changing a rule.
4. Correct the cause and rerun the complete workflow.
5. Preserve the failed and recovered run IDs when documenting an incident.

## Current completion boundary

Completed: uv environment, SQL Server connectivity, 18 reporting-view checks, one-command execution, saved run reports and a verified count-mismatch failure-and-recovery exercise.

Still to implement: repeatable loading with safe reruns, input manifests, source-data checks, additional business reconciliations and automated fixture tests/CI. This milestone does not establish a complete ingestion pipeline, automated deployment or production operations experience.
