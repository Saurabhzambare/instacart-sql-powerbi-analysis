# Project Documentation Guide

**Owner:** Saurabh Lalit Zambare  
**Updated:** 1 November 2026

## Read in this order

| Document | Purpose | Status |
| --- | --- | --- |
| [Project scope](PROJECT_SCOPE.md) / [PDF](PROJECT_SCOPE.pdf) | Dataset boundaries, accepted deliverables, exclusions and evidence policy | v1.2; current cloud update ready for commit |
| [Project roadmap](PROJECT_ROADMAP.md) / [PDF](PROJECT_ROADMAP.pdf) | Sequence, dependencies, technologies and completion checks | v2.2; CI and cloud checks verified; dbt compatibility next |
| [SQL technical report](SQL_PROJECT_REPORT.md) | Original full-data SQL, model and DAX findings | Historical analytical checkpoint |
| [Python automation report](PYTHON_AUTOMATION_REPORT.md) / [PDF](PYTHON_AUTOMATION_REPORT.pdf) | Complete original setup-to-pipeline learning record | Published at dcb145d; retains its original 53-test checkpoint |
| [Reporting validation runbook](VALIDATION_RUNBOOK.md) | Separate reporting-view quality runner | Established 18-check workflow |
| [Input runbook](INPUT_RUNBOOK.md) | Source manifest and fingerprint baseline | Existing runbook; earlier next-step wording predates loader completion |
| [CI runbook](CI_RUNBOOK.md) | Hosted code checks and controlled regression/recovery | Core CI verified; expanded 71-test pass at c90c4f0 |
| [Cloud subset runbook](CLOUD_SUBSET_RUNBOOK.md) | Deterministic export, safe publication and file fingerprints | Exporter/evidence published at c90c4f0 |
| [BigQuery runbook](BIGQUERY_RUNBOOK.md) | Schemas, manual loading, quality checks and analytical reconciliation | Five tables and 55 comparison rows verified; current publication pending |
| [DBT staging runbook](DBT_RUNBOOK.md) | Setup, staging views, data tests and troubleshooting | Five views and 33 tests passed; PASS=38 |
| [Selected validation evidence](validation_evidence/) | Retained local pass/failure/recovery reports and subset manifest | Original and later accepted checkpoints |
| [Cloud screenshot review](cloud_evidence/reconciliation_review.json) / [screenshots](cloud_evidence/screenshots/) | Normalized observed results and original screenshot provenance | Manual review, not a database API export or automated parity job |

## Query sources

BigQuery SQL is under `cloud/bigquery/01_...08_*.sql`. SQL Server references are `sql/cloud_subset_orders_by_hour.sql`, `sql/cloud_subset_department_analysis.sql`, and `sql/cloud_subset_top_products.sql`. Keep the eight cloud files and three reference files already created locally; this documentation package does not replace them.

## Diagram files

Scope/roadmap use SVGs under `assets/project_planning/` with matching editable Mermaid `.mmd` sources. The earlier Python report retains its own `assets/python_automation/` folder. Keep relative assets beside the documents.

## Saving the current update

Extract the package into the repository root, preserving the `docs` hierarchy and replacing matching documentation/diagram files. It contains the updated scope/roadmap Markdown and PDFs, documentation index, subset runbook update, new BigQuery runbook, review JSON, twelve original screenshots and planning assets. Review in GitHub Desktop, then commit/push with the eleven SQL files already staged for the cloud milestone.

## Maintenance and next step

Maintain Markdown as the editable source and regenerate reading copies when their content changes. Historical reports retain their named commit and test counts. The current exporter baseline is c90c4f0; the source/docs/evidence from the guided BigQuery phase need the next commit/push verification. After that checkpoint and a passing hosted test run, begin DBT-01 compatibility proof. Older README/input-runbook wording and the independent PBIX delivery smoke check remain narrow follow-ups. LinkedIn remains a separate discussion.
