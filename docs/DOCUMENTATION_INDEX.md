# Project Documentation Guide

**Owner:** Saurabh Lalit Zambare  
**Updated:** 31 October 2026

## Read in this order

| Document | Purpose | Status |
| --- | --- | --- |
| [Project scope](PROJECT_SCOPE.md) / [PDF](PROJECT_SCOPE.pdf) | Objectives, dataset boundaries, completed work, exclusions, acceptance policy | Created for review |
| [Project roadmap v2](PROJECT_ROADMAP.md) / [PDF](PROJECT_ROADMAP.pdf) | Milestone order, technologies, dependencies, backlog and completion checks | Created for review |
| [SQL technical report](SQL_PROJECT_REPORT.md) | Per-script analytical findings, model and DAX | Existing project document |
| [Python automation report](PYTHON_AUTOMATION_REPORT.md) / [PDF](PYTHON_AUTOMATION_REPORT.pdf) | Full setup-to-pipeline learning and implementation record | Created in the preceding documentation step; remote addition unverified |
| [Reporting validation runbook](VALIDATION_RUNBOOK.md) | Operate the separate 18-check reporting workflow | Existing milestone runbook |
| [Input runbook](INPUT_RUNBOOK.md) | Inspect inputs and enforce recorded fingerprints | Existing milestone runbook; its next-step wording predates loading completion |
| [Selected validation evidence](validation_evidence/) | Nine retained pass/failure/recovery reports | Committed at bfc1763 |

## Diagram files

Planning documents reference SVGs under `assets/project_planning/`. Matching `.mmd` files are editable Mermaid sources describing the same relationships. Keep these assets beside the Markdown files. The earlier Python report uses its own `assets/python_automation/` folder.

## Saving this package

Extract the documentation ZIP into the existing repository root. It supplies the scope, updated roadmap, this guide, and planning diagram files under `docs`. Keep the separately delivered Python report and existing SQL/runbook/evidence files in place. Review changes in GitHub Desktop before committing and pushing. This package contains documentation only.

## Maintenance

After an accepted milestone, update status and evidence links in the scope/roadmap, then regenerate reading copies. Historical evidence stays tied to its original run/commit. Creating documentation does not mean its future implementation is complete. The next implementation milestone after review/publication is CI-01 and CI-02 in the roadmap. LinkedIn work remains a separate discussion.
