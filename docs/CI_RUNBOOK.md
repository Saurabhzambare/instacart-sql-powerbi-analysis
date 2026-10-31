# Continuous Integration Runbook

**Owner:** Saurabh Lalit Zambare  
**Verified:** 31 October 2026  
**Workflow on main:** `c863046de0c52755228f30ee189f10db0131236b`  
**Recovery demonstration:** branch `ci/failure-recovery-demo`, commit `647d9c21b2621fffa25ed384194d1b9fb8b007f9`

## 1. What this milestone adds

GitHub Actions now runs the existing Python test suite automatically when code is pushed. The workflow also declares pull-request and manual-dispatch triggers. This milestone verified push-triggered runs, a deliberate regression, and a corrected pass.

The checks run on a GitHub-hosted Windows runner. Small fixtures, mocked connections, and controlled Python subprocesses test the program's behavior. The first workflow does not execute the real database loaders or connect to the development laptop's SQL Server. The earlier live database loading/recovery evidence remains a separate proof.

## 2. Workflow file and steps

The file is [`.github/workflows/python-tests.yml`](../.github/workflows/python-tests.yml).

| Setting or step | Meaning |
| --- | --- |
| `on: push` | Start a run after a pushed commit on any branch |
| `on: pull_request` | Configure checks for pull-request activity |
| `workflow_dispatch` | Allow a manual run through the Actions interface |
| `contents: read` | Workflow token permission is limited to reading repository contents |
| Concurrency group | Cancel an older active run for the same workflow/ref when a newer one starts |
| `windows-latest` | Use the hosted Windows runner family |
| Ten-minute timeout | Bound the unit-test job's execution time |
| `shell: pwsh` | Execute run steps in PowerShell |
| Checkout with `lfs: false` | Obtain code without downloading the large PBIX LFS binary |
| Checkout without credential persistence | Do not retain checkout credentials for later Git operations |
| Setup uv | Install uv 0.13.1 and configure Python 3.14.3 selection |
| Install Python | Make the chosen Python patch version available |
| Locked dependency sync | Restore the packages recorded in `uv.lock` |
| Test execution | Run unittest discovery; failure propagates to the workflow |

The setup-uv action is pinned to a full commit with a version comment; checkout uses its reviewed v7 major tag. Future updates should be reviewed. Cache restoration improves setup speed but does not replace test execution or permit lockfile changes.

## 3. Reproduce the local code checks

From the repository root:

```powershell
uv sync --locked
uv run --locked python -m unittest discover -s tests -v
$LASTEXITCODE
```

The accepted suite had 53 tests. The correct future criterion is that the relevant suite passes; test count can change as the implementation evolves. View a hosted run through **Actions → Python tests → run → Unit tests → Run automated tests**.

## 4. Verified pass, failure, and recovery

| Selected phase | Commit | Branch | Outcome |
| --- | --- | --- | --- |
| [Baseline run #1](https://github.com/Saurabhzambare/instacart-sql-powerbi-analysis/actions/runs/41181217619) | `c863046` | `main` | 53 tests passed |
| [Deliberate regression run #3](https://github.com/Saurabhzambare/instacart-sql-powerbi-analysis/actions/runs/41181802743) | `a411277` | `ci/failure-recovery-demo` | 53 tests run; exactly 1 failure; exit 1 |
| [Corrected run #4](https://github.com/Saurabhzambare/instacart-sql-powerbi-analysis/actions/runs/41181974673) | `647d9c2` | `ci/failure-recovery-demo` | 53 tests passed |

These are selected evidence runs, not every workflow execution. Their test-loop durations were 0.115, 0.200, and 0.210 seconds respectively; those are not complete workflow durations.

### What changed during the failure exercise

The accepted `bulk_sql()` helper in `scripts/load_table.py` contains:

```python
filename = str(path).replace("'", "''")
```

On the demonstration branch, this temporarily became:

```python
filename = str(path)
```

The existing `test_load_table.LoadingContractsTests.test_bulk_path_quotes_are_escaped` detected that a filename containing an apostrophe was no longer escaped correctly in its SQL literal. GitHub recorded the test-command exit code 1 and marked the workflow failed. Restoring the original line produced the corrected green run. The test remained unchanged throughout.

This proves the workflow detects the tested regression and returns to passing after correction. It does not establish protection against every possible defect or automatic blocking of merges.

## 5. Demonstration branch and main

GitHub's comparison of `main` at `c863046` with the recovered demonstration commit showed two commits ahead, zero behind, and **no net changed files**. The correction restored the same file tree. A code merge is therefore unnecessary for this exercise at the compared checkpoint.

Keep the branch/run links available as evidence. Return to `main` for the documentation checkpoint. Branch deletion is optional and is not required by this milestone. A later main-branch change would require a fresh comparison before reusing the no-difference conclusion.

## 6. Evidence and completion boundaries

The selected summary is saved in [ci_pass_fail_recovery.json](validation_evidence/ci_pass_fail_recovery.json). It records full commit IDs, run/job IDs, test counts, the failing test, links, and the branch comparison. Source data came from GitHub run metadata, decoded job logs, and the commit comparison. It is a curated verification summary rather than a fabricated pipeline log.

| Capability | State |
| --- | --- |
| Hosted push-triggered test execution | Verified |
| Expected regression detected | Verified |
| Corrected source passes unchanged tests | Verified |
| Pull-request/manual triggers | Configured; not separately exercised in this record |
| Required merge checks / branch policy | Not established |
| Live SQL integration on hosted runners | Outside this first CI job |
| Release artifact delivery / deployment | Later roadmap milestones |

If CI fails, open the failing step, identify whether setup or tests failed, reproduce the relevant check locally when useful, fix the source/configuration, and push a new commit. Wait for the failed run to finish before pushing the correction when collecting this exercise's evidence; concurrency cancellation can otherwise leave a canceled run instead of a completed failure.

The **core CI milestone is complete**. Commit the accepted evidence/runbook and updated scope/roadmap on `main` to close its documentation checkpoint.
