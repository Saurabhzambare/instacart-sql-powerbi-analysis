# Load the selected Instacart ML labels

Owner: Saurabh Lalit Zambare  
Prepared: 2 November 2026  
Starting checkpoint: `c7369b7`, verified ML input validation

## 1. What this step does

The previous script checked the labels in temporary tables. This loader saves the
selected customers' actual next-order purchases in a separate permanent SQL table:

`pipeline_ml.train_labels_5000_users_v1`

This is still data preparation. It does not create the model's complete training
table. We will later add candidate products absent from the next order as negative
examples, calculate historical features, split customers, and train a model.

The accepted input report is
[ml_train_labels_validation_pass.json](validation_evidence/ml_train_labels_validation_pass.json).

## 2. What is stored

| Column | Meaning |
|---|---|
| user_id | Customer who placed the order |
| order_id | Their labeled next order |
| product_id | Product actually purchased in that order |
| add_to_cart_order | Position in that target order's cart |
| source_reordered | Original CSV reordered flag, renamed to make its role clear |

`source_reordered` is not the complete ML prediction target. Target cart position
and target reordered flag must not be used as predictor features. Products absent
from the target basket have no row here; we will construct their negative labels
from earlier-history candidates later.

The primary key is `(order_id, product_id)`. Cart positions are also unique within
each order. Columns are required integers, with positive IDs/cart position and a
source flag restricted to 0/1.

## 3. Counts from the accepted live validation

| Measurement | Expected |
|---|---:|
| Complete source product entries | 1,384,617 |
| Selected customers, including official test customers | 5,000 |
| Selected labeled customers | 3,200 |
| Selected target orders | 3,200 |
| Rows to publish | 33,782 |
| Distinct target products | 9,850 |
| Sum of source_reordered | 20,229 |

`config/ml_train_labels_load_spec.json` records the accepted subset totals. It also
binds the publication to the existing input contract's dataset names, source
fingerprint, selection counts, and one fixed target. Do not change the expected
counts merely to make a failed load pass. Investigate changed data or cohort first.

The full source is checked against the full SQL Server orders/products tables.
The loader then selects the same 5,000 lowest user IDs and keeps only their train
orders. It does not infer target rows from the prior-only BigQuery product table.

## 4. Files added

| File | Purpose |
|---|---|
| config/ml_train_labels_load_spec.json | Accepted publication identity and counts |
| scripts/load_ml_train_labels.py | Transactional loader and run report |
| tests/test_load_ml_train_labels.py | Offline contract/transaction-flow tests |
| sql/validate_ml_train_labels.sql | Read-only SSMS inspection queries |
| docs/ML_LABEL_LOADING_RUNBOOK.md | This guide |

These are additions to checkpoint `c7369b7`. They reuse the committed input
validator and existing SQL connection helper. No new dependency is needed.

## 5. How a normal load works

1. Check both contracts, the four CSV columns, file size, and SHA-256 before connecting.
2. Start a transaction and load the CSV into a temporary table.
3. Check the source fingerprint again and run the accepted source validation rules.
4. Require the selected-label observations to match the accepted live totals.
5. Build a temporary expected table containing the five publication columns.
6. Acquire a transaction-owned application lock so copies of this loader serialize publication.
7. Create the separate schema/table if missing; reject incompatible existing columns/keys.
8. Lock the target table and compare its rows with the expected table in both directions.
9. If different, replace its rows inside the transaction. If identical, leave them alone.
10. Check all five table metrics and exact row equality again, then commit and save a JSON report.

The serializable transaction keeps the source-reference reads consistent during
this run. Source changes between separate runs remain possible; each run validates
again. The application lock coordinates this loader, not arbitrary external writers.
No statement modifies the existing `pipeline_staging` tables, BigQuery, or dbt.

## 6. Run the offline tests first — PowerShell

From the repository root:

```powershell
uv run python -m unittest discover -s tests -v
$LASTEXITCODE
```

Expected suite: **118 tests** (the original 94 plus 24 loader tests), all passing,
with exit code 0. These tests use
small fixtures and a transaction test double. They check contract rejection,
publication decisions, failure boundaries and report behavior. They do not prove
that SQL Server executed the new SQL; the following live runs provide that evidence.

## 7. First live load — PowerShell

```powershell
uv run python -m scripts.load_ml_train_labels `
    --data-dir "D:\DataProjects\data-download"

$LASTEXITCODE
```

Expected on a new target: `PASS`, action `REPLACED`, 33,782 target rows,
33,782 rows written, transaction `COMMITTED`, exit code 0.
The JSON report is under ignored `logs/ml_loading/<run_id>.json`.

If a prior invocation already committed, a later attempt can correctly report
`UNCHANGED` instead. Check its report and inspect the table.

## 8. Safe rerun — PowerShell

Run the same normal command again. Expected: `PASS`, `UNCHANGED`, 33,782 target rows,
zero rows written, `COMMITTED`, exit code 0. The loader compares all five columns,
not just the number of rows.

## 9. Inspect the permanent table — SSMS

Open `sql/validate_ml_train_labels.sql`, select the `InstacartAnalytics` database,
and execute it. Compare the totals with section 3. Invalid values, unmatched
references, users outside the selected cohort, and duplicate-group counts must be
zero. The final query shows ten actual rows.

## 10. Rollback exercise — only after a correct live load and rerun

This command deliberately clears the dedicated ML target inside a transaction
and raises an error before commit. It first refuses to proceed unless the target
already exactly matches the validated labels.

```powershell
uv run python -m scripts.load_ml_train_labels `
    --data-dir "D:\DataProjects\data-download" `
    --simulate-failure

$LASTEXITCODE
```

Expected: `FAIL`, action `SIMULATED_FAILURE`, transaction `ROLLED_BACK`, zero committed
rows written, exit code 1. This is the intended failure demonstration, not a passing
load. Re-run the SSMS inspection and then the normal loader command. The table must
still have the accepted totals and the normal loader must report `UNCHANGED`.
Record the actual output before claiming live rollback behavior is verified.

## 11. Failure results

| Result | Meaning |
|---|---|
| PASS / COMMITTED | Normal load or unchanged rerun completed and report saved |
| FAIL / NOT_STARTED | Input or publication contract rejected before transaction |
| FAIL or ERROR / ROLLED_BACK | Failure occurred before commit and rollback succeeded |
| FAIL or ERROR / UNKNOWN | Commit or rollback failed; inspect the target before assuming its state |

An unchanged target can still be reported with an unknown outcome if the connection
fails during commit. The loader does not convert an uncertain outcome into a success.
Failure to save the report returns exit code 1 even if SQL already committed; the
console prints the database outcome. A subsequent normal run checks the target again.

If Windows reports file-sharing error 32, close the application holding the CSV
and retry after it releases the file. Do not weaken the fingerprint or row checks.

## 12. Evidence and completion

After observing the live results, retain the selected JSON reports in
`docs/validation_evidence/` for the initial load, unchanged rerun, deliberate
rollback, and unchanged recovery. Keep routine logs ignored. Review the reports'
status, action, transaction outcome and metrics before archiving them.

Add this guide to `docs/DOCUMENTATION_INDEX.md` after the ML input guide when
publishing the completed checkpoint. Update status wording only after live proof.
The preparation of this package itself does not establish that a permanent table
exists or that live rerun/rollback checks have passed.

Package verification: the complete 118-test suite passed in a local verification
copy of checkpoint `c7369b7` with these additions, using Python 3.12.14. The user
must run the suite in the project's own Windows/uv environment before the live load.

The following milestone will define candidate rows, history cutoffs, user splits,
and historical features. No model is trained by this loader.

## SQL reference documentation

- [Transaction-owned application locks](https://learn.microsoft.com/en-us/sql/relational-databases/system-stored-procedures/sp-getapplock-transact-sql)
- [Ordered STRING_AGG used to inspect key columns](https://learn.microsoft.com/en-us/sql/t-sql/functions/string-agg-transact-sql)
