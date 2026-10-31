# Cloud Subset Export Runbook

**Owner:** Saurabh Lalit Zambare  
**Prepared:** 31 October 2026  
**Status:** CLD-01 subset definition/export milestone verified locally. All 71 Windows tests passed; the real SQL Server export passed; all five exported files matched their manifest byte sizes and SHA-256 fingerprints. BigQuery loading and cross-platform reconciliation have not started.  
**Verified export run:** `ea95847fec9d4b6b864f0903f7a30a63`  
**Git checkpoint:** Source files and selected evidence are ready for commit; the new hosted CI run is pending push.

## Purpose and selection

Create a reproducible small five-file dataset for the planned BigQuery/dbt branch. Select the 5,000 lowest user IDs from `pipeline_staging.orders`, retain all their order metadata, and retain all product entries for their prior orders. This is an engineering subset, not a random or representative sample.

The selected products are those referenced by the retained prior entries. Keep the full, small aisle and department lookup tables. The train-product label CSV remains outside this export. Train/test order metadata is included, but descriptive comparisons must filter prior orders where appropriate.

## Verified SQL preview and expected export

| Measure | Verified preview |
| --- | ---: |
| Users | 5,000 |
| All orders | 81,832 |
| Prior orders | 76,832 |
| Train orders | 3,200 |
| Test orders | 1,800 |
| Prior product entries | 761,750 |
| Distinct referenced products | 28,854 |
| Reordered entries | 448,380 |

| Export file | Expected and exported data rows |
| --- | ---: |
| departments.csv | 21 |
| aisles.csv | 134 |
| products.csv | 28,854 |
| orders.csv | 81,832 |
| order_products__prior.csv | 761,750 |

Headers are excluded from the data-row counts. The department/aisle counts come from the established baseline and were rechecked by the exporter. The other subset counts come from the live SSMS preview. The verified export matched the expected metrics and passed the configured zero-error checks. The later PowerShell check verified saved bytes against the manifest; it did not independently recount parsed CSV records.

## Added files

| File | Role |
| --- | --- |
| `config/cloud_subset_spec.json` | Separate dataset label, deterministic selection, expected metrics |
| `scripts/export_cloud_subset.py` | Capture/validate SQL subset, stream CSVs, fingerprint and publish output |
| `tests/test_export_cloud_subset.py` | Contract, CSV, transaction, streaming, and publication tests |
| `docs/CLOUD_SUBSET_RUNBOOK.md` | Selection, operating instructions, expected results, and boundaries |
| `sql/cloud_subset_preview.sql` | Read-only SQL preview used to establish the selected-user cohort and reference counts |
| `docs/validation_evidence/cloud_export_temp_scope_fail.json` | Selected failed capture report before the temporary-table correction |
| `docs/validation_evidence/cloud_export_recovery_pass.json` | Successful Windows SQL Server export report after the correction |
| `docs/validation_evidence/cloud_subset_manifest.json` | Saved copy of the accepted exported-file manifest |

The original `input_manifest.json`, `input_baseline.json`, and five-table loading workflow stay as the accepted full-data baseline. The subset has its own label, `instacart_cloud_5000_users_v1`.

## How export works

1. Require an output directory outside the repository that does not already exist.
2. Read the separate subset contract.
3. Use serializable SQL reads to materialize user/order/entry/product/lookup data into session-local `#cloud_*` tables. Only temporary SQL objects are created.
4. Require unique keys, exact preview/cohort counts, valid values/names, and matching product/lookup references. Unique temporary indexes reject duplicate keys.
5. Commit the checked temporary capture, releasing source read locks before file writing. The temporary tables remain available on the same connection.
6. Stream each ordered query in batches of at most 10,000 rows to a staging directory beside the intended destination.
7. Require each written row count and calculate file byte sizes and SHA-256 fingerprints.
8. Reserve a new output directory exclusively, publish five CSVs, then publish `_manifest.json` last.
9. Save a local execution report under ignored `logs/cloud_export/<run-id>.json`.

Use a quiet local data window: do not run a loader concurrently with source capture. Serializable reads can block competing writes while capture is underway. This is a consistent checked temporary capture, not a change to SQL Server snapshot-isolation database settings.

CSV uses UTF-8, LF record endings, a header, standard quoting, and empty fields for NULLs. Product-name commas/quotes/newlines are handled by `csv.writer`. First-order gaps stay empty; zero gaps remain numeric text. Read file record counts from the manifest rather than counting physical lines, because quoted text can contain a newline.

## Test and run

From the repository root:

```powershell
uv run python -m unittest discover -s tests -v
$LASTEXITCODE
```

The following command already completed successfully. It documents the accepted first export; do not rerun it against the now-existing destination:

```powershell
uv run python -m scripts.export_cloud_subset --output-dir "D:\DataProjects\Instacart\exports\cloud_5000_users_v1"
$LASTEXITCODE
```

On success, expect five file PASS results, overall PASS, exit 0, and the path to `_manifest.json`. Inspect the manifest:

```powershell
$subsetManifest = Get-Content "D:\DataProjects\Instacart\exports\cloud_5000_users_v1\_manifest.json" -Raw | ConvertFrom-Json
$subsetManifest | Select-Object dataset_label, status, run_id | Format-Table -AutoSize
$subsetManifest.files | Select-Object file, rows, size_bytes | Format-Table -AutoSize
```

For a future intentional export, choose a new directory outside the repository and do not create the final directory first. For example, use `cloud_5000_users_repeat_01` instead of the existing `cloud_5000_users_v1`. A new directory does not change the dataset contract: changing cohort rules or accepted metrics requires a separate contract decision.

## Verify the saved CSV bytes

Run this read-only check against the accepted export:

```powershell
$subsetDirectory = "D:\DataProjects\Instacart\exports\cloud_5000_users_v1"
$subsetManifest = Get-Content "$subsetDirectory\_manifest.json" -Raw | ConvertFrom-Json
$exportFileChecks = @(
    foreach ($file in $subsetManifest.files) {
        $filePath = Join-Path $subsetDirectory $file.file
        $actualSize = (Get-Item -LiteralPath $filePath).Length
        $actualHash = (Get-FileHash -LiteralPath $filePath -Algorithm SHA256).Hash
        [pscustomobject]@{
            File = $file.file
            Rows = $file.rows
            SizeMatch = $actualSize -eq $file.size_bytes
            HashMatch = $actualHash -eq $file.sha256
        }
    }
)
$exportFileChecks | Format-Table -AutoSize
if (
    $subsetManifest.status -ne "PASS" -or
    $exportFileChecks.Count -ne 5 -or
    @($exportFileChecks | Where-Object {
        -not $_.SizeMatch -or -not $_.HashMatch
    }).Count -gt 0
) {
    throw "Export file verification failed."
}
Write-Host "All five exported files match the manifest."
```

The verified run returned five rows with `SizeMatch = True` and `HashMatch = True`. This establishes that the saved CSV bytes still match the accepted exporter manifest. It does not establish that the files have been loaded into BigQuery or tested there.

## Manifest and error behavior

The manifest contains the selection policy, source database/schema/server, accepted metrics, exporter/specification fingerprints, CSV format, and each file's header/row count/bytes/hash. These hashes describe exported bytes; they are not the original full-data input fingerprints.

Existing output folders are refused instead of overwritten. For a second intentional export, choose a new versioned destination. Ordinary export/validation failures leave no published successful manifest. The code cleans its own staged files; a publication failure attempts to remove only files it created. A hard process/machine interruption can leave partial files or staging data, so require a PASS manifest and verify its file hashes before a later cloud load.

A log-write failure can occur after output publication; the command returns 1 and prints the already-published manifest path. Inspect that state before retrying. Closing the database connection removes session-local temporary tables. No permanent source data is deleted, inserted, or updated by this exporter.

The unit tests use fixtures and mock SQL results. The successful Windows export provides the separate SQL Server integration check. BigQuery setup, cloud upload, reconciliation, and dbt are later steps.

## Temporary-table scope correction

The first Windows attempts failed with SQL Server error 208, `Invalid object name '#cloud_users'`, before CSV writing. The two recorded failed run IDs are `de772c98746c48678ef5d97ab0a0c567` and `fa8d28eaaef94e56aaf3634de19bc322`. The missing output manifest after these failures is expected.

The original code used `SELECT TOP (?) ... INTO #cloud_users` in one parameterized ODBC execution. The likely cause is that the prepared execution created the temporary table in an inner execution scope, making it unavailable to the next batch. The corrected code first creates `#cloud_users` in a separate unparameterized batch, then uses a parameterized `INSERT INTO` to populate that existing session table. The primary key preserves the original unique clustered user-ID check. Subsequent capture batches and CSV queries use the same connection.

A new offline regression test models that scope boundary. It fails when a parameterized batch creates a temporary table that later batches need. The full suite now contains 71 tests. This test checks the execution contract; it does not run the Microsoft ODBC driver or SQL Server. All 71 tests passed on Windows in 0.934 seconds with exit code 0. The corrected real export then passed with exit code 0, confirming recovery for the configured SQL Server/ODBC environment.

The earlier failed attempts did not publish the destination. The corrected run created the accepted destination and manifest; preserve it and choose a different path for any repeat export.

References: [Microsoft: Prepared execution](https://learn.microsoft.com/en-us/sql/relational-databases/native-client-odbc-queries/executing-statements/prepared-execution?view=sql-server-ver15) documents restrictions on creating temporary objects with prepared statements; [Microsoft: sp_prepexec](https://learn.microsoft.com/en-us/sql/relational-databases/system-stored-procedures/sp-prepexec-transact-sql?view=sql-server-ver17) describes parameterized preparation and execution. The specific driver path in the failed runs was not traced.

## Evidence and acceptance record

The following results were verified through the owner's Windows terminal output on 31 October 2026. The selected JSON files were copied into the repository by the owner; this documentation update does not independently reread those local Windows files.

| Check | Verified outcome | Preserved evidence |
| --- | --- | --- |
| Original capture | ERROR 208, missing `#cloud_users`, exit 1 | [Failed capture report](validation_evidence/cloud_export_temp_scope_fail.json), run `fa8d28eaaef94e56aaf3634de19bc322` |
| Unit tests after correction | 71 tests, OK, exit 0 | Recorded Windows terminal output; hosted CI for this change pending push |
| Real SQL Server export | PASS, five expected file counts, exit 0 | [Recovery report](validation_evidence/cloud_export_recovery_pass.json), run `ea95847fec9d4b6b864f0903f7a30a63` |
| Manifest | Label `instacart_cloud_5000_users_v1`, PASS, matching recovery run ID | [Accepted manifest copy](validation_evidence/cloud_subset_manifest.json) |
| Saved file integrity | All five byte sizes and SHA-256 fingerprints match | Recorded PowerShell verification table; the manifest contains the expected sizes and hashes |

The CSVs remain at `D:\DataProjects\Instacart\exports\cloud_5000_users_v1`, outside the Git repository. Commit the exporter, contract, tests, SQL preview, this runbook, and the three selected JSON evidence files. Routine execution logs remain ignored. The original full-data input baseline, loading targets, reporting views, and Power BI workflow retain their existing roles.

## Roadmap handoff

CLD-01's subset definition and export are complete locally. Existing SQL preview metrics provide the initial local reference counts. After the Git checkpoint, confirm the expanded test suite passes in GitHub Actions. Then proceed to CLD-02: set up the BigQuery practice environment, select explicit load schemas and matching CSV options, load these exact five files, and reconcile table counts, relationships, and selected analytical results with SQL Server on the same subset. Define and preserve any additional analytical reference outputs during that reconciliation work.

BigQuery upload, cloud query results, dbt, model training, scheduling, and deployment are not outcomes of this milestone. The full Python automation report and earlier hosted CI evidence remain historical records of their named checkpoints and test counts.
