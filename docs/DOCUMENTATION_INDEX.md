# Project Documentation Guide

**Owner:** Saurabh Lalit Zambare  
**Updated:** 11 November 2026

## Start with the milestone you need

| Milestone | Entry point | Evidence |
|---|---|---|
| Local SQL Server and Power BI | [SQL technical report](SQL_PROJECT_REPORT.md) and [reporting specification](PRODUCTS_REORDERING_SPEC.md) | Full historical prior cohort, KPI definitions, dashboard filters, and reconciliation |
| BigQuery and dbt | [Cloud subset](CLOUD_SUBSET_RUNBOOK.md), [BigQuery](BIGQUERY_RUNBOOK.md), and [dbt](DBT_RUNBOOK.md) runbooks | Deterministic subset, published models, reference checks, and recorded build |
| Reorder prediction | [ML results](ML_REORDER_RESULTS.md) | Customer-disjoint evaluation and recorded model export |

## Supporting documents

| Document | Purpose | Status |
|---|---|---|
| [Project scope](PROJECT_SCOPE.md) / [PDF](PROJECT_SCOPE.pdf) | Dataset boundaries, accepted deliverables, exclusions and evidence policy | v1.2 cloud-baseline planning snapshot; current dbt implementation is documented in the dbt runbook |
| [Project roadmap](PROJECT_ROADMAP.md) / [PDF](PROJECT_ROADMAP.pdf) | Sequence, dependencies, technologies and completion checks | v2.2 planning snapshot; BigQuery and dbt live build now verified; see current dbt runbook |
| [SQL technical report](SQL_PROJECT_REPORT.md) | Original full-data SQL, model and DAX findings | Historical analytical checkpoint |
| [Python automation report](PYTHON_AUTOMATION_REPORT.md) / [PDF](PYTHON_AUTOMATION_REPORT.pdf) | Original setup-to-pipeline learning record | Published at dcb145d; retains its original 53-test checkpoint |
| [Reporting validation runbook](VALIDATION_RUNBOOK.md) | Separate reporting-view quality runner | Established 18-check workflow |
| [Input runbook](INPUT_RUNBOOK.md) | Source manifest and fingerprint baseline | Earlier next-step wording predates loader completion |
| [CI runbook](CI_RUNBOOK.md) | Hosted Python checks and controlled regression/recovery | Core CI verified; 71 Python tests also passed for f800de2 |
| [Cloud subset runbook](CLOUD_SUBSET_RUNBOOK.md) | Deterministic export, safe publication and file fingerprints | Exporter/evidence published at c90c4f0 |
| [BigQuery runbook](BIGQUERY_RUNBOOK.md) | Schemas, manual loading, quality checks and analytical reconciliation | Five tables and 55 comparison rows verified; published at 2ee57cc |
| [dbt staging and marts runbook](DBT_RUNBOOK.md) | Setup, every dbt file and test, analytical models, evidence, operation and troubleshooting | Live complete build: eight views and 56 tests passed; PASS=64; see the retained build report and catalog |
| [ML label loading runbook](ML_LABEL_LOADING_RUNBOOK.md) | Permanent ML labels, unchanged reruns and rollback recovery | Verified locally; 118 Python tests passed |
| [Selected validation evidence](validation_evidence/) | Retained pass/failure/recovery reports, manifest and dbt catalogs | Earlier snapshots remain historical; archive the complete dbt report/catalog using the runbook |
| [Cloud screenshot review](cloud_evidence/reconciliation_review.json) / [screenshots](cloud_evidence/screenshots/) | Recorded aggregate results and original screenshot provenance | Historical manual review; fixed values now also support three passing dbt regression tests |

## Query and model sources

| Location | Contents |
|---|---|
| `cloud/bigquery/01_...05_*.sql` | Raw BigQuery table validations |
| `cloud/bigquery/06_...08_*.sql` | Original hourly, department and top-product analysis queries |
| `cloud/bigquery/09_...12_*.sql` | dbt staging verification queries |
| `cloud/bigquery/13_...15_*.sql` | dbt mart verification queries |
| `sql/cloud_subset_orders_by_hour.sql` | SQL Server hourly reference |
| `sql/cloud_subset_department_analysis.sql` | SQL Server department reference |
| `sql/cloud_subset_top_products.sql` | SQL Server top-product reference |
| `dbt_instacart/models/staging/` | Five staging view definitions and model properties |
| `dbt_instacart/models/marts/` | Three analytical view definitions and model properties |
| `dbt_instacart/tests/` | Nine singular SQL tests, including three fixed aggregate-reference comparisons |
| `tests/` | Separate Python unit-test suite |

The 56 dbt tests comprise 47 generic tests declared in model YAML and nine singular SQL tests. The three mart reference tests cover 24 hourly, 21 department and ten ranked-product rows. These compare BigQuery results against the previously recorded reference; they do not execute a new live cross-warehouse comparison.

## Diagram files

Scope/roadmap SVGs and editable Mermaid sources are under `assets/project_planning/`. The earlier Python report retains `assets/python_automation/`. The dbt runbook contains editable Mermaid diagrams for staging relationships and analytical SQL dependencies. Keep existing assets beside their documents.

## Current checkpoints and publication

| Checkpoint | Verified outcome |
|---|---|
| c90c4f0 | Cloud subset exporter and recovery evidence published |
| 2ee57cc | BigQuery loading and SQL reconciliation published |
| b6d7a5e | Initial dbt departments model, tests and connection proof published |
| f800de2 | Five staging views and 33 tests published; hosted Python CI run #9 passed all 71 tests |
| Recorded analytical extension | Eight views and 56 tests passed in one complete build, exit code 0; all three supplied mart query results match the reference |

The recorded [dbt build](validation_evidence/dbt_project_build_pass.json) and [catalog](validation_evidence/dbt_project_catalog.json) are committed evidence. For a new run, follow the dbt runbook.

## Maintenance and next work

Markdown remains the editable source. Scope/roadmap PDFs retain their versioned planning context; this update does not regenerate those PDFs or relabel their historical plans as current execution evidence. The dbt runbook is the current implementation record for this milestone.

The current BigQuery/dbt implementation is complete at the live-build level. Evidence/catalog capture and publication close the checkpoint. Scheduling, hosted dbt execution, ML and deployment remain later roadmap choices. Older README/input-runbook wording and the independent PBIX delivery smoke check remain separate follow-ups. LinkedIn remains a separate discussion.
