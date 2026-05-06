# Agent Handoff

Read this file first in every new AI coding session. It summarizes the current state, what was just done, and the safest next step.

## Current State

ValueScope is a new greenfield project at `/Users/dingyitian/Desktop/ValueScope`.

Sprint 001 is complete under the current conservative annual-report provenance rule. The project has a runnable Python/FastAPI backend, Vite/React frontend, copied `stock-scripts` engine under a legacy namespace, a ValueScope report snapshot facade, tests, and a generated sample snapshot.

## Product Direction

ValueScope is a local-first value investing research workstation and screener. The first version reproduces the A-share financial report workflow from `stock-scripts` as ValueScope-owned Python data generation plus a React report UI. Dynamic factor screening comes later.

## Current Sprint

Sprint 001: Reproduce Single-Stock Financial Report.

Sprint goal: create the first runnable workflow that generates a local single-stock financial report snapshot and renders the report in React.

Status: Done on 2026-05-06. See `docs/sprints/sprint-001.md` and `docs/progress.md` for completion evidence.

## Last Completed

- Created the project directory.
- Added README and design brief.
- Added Scrum docs:
  - `docs/product-roadmap.md`
  - `docs/backlog.md`
  - `docs/sprints/sprint-001.md`
  - `docs/snapshot-schema.md`
  - `docs/report-snapshot-schema.md`
  - `docs/decisions/ADR-001-local-json-no-db.md`
  - `docs/decisions/ADR-002-python-snapshot-exporter-typescript-ui.md`
- Added agent docs:
  - `AGENTS.md`
  - `CLAUDE.md`
  - `.github/copilot-instructions.md`
  - `docs/agents/`
- Added persistent memory docs:
  - `docs/progress.md`
  - `docs/agent-handoff.md`
  - `docs/working-log.md`
- Audited `/Users/dingyitian/Desktop/stock-scripts` and created `docs/reference/stock-scripts-capability-map.md`.
- Copied the report engine under `python/valuescope/legacy_stock_scripts/`.
- Added `python/valuescope/report_snapshot.py` as the ValueScope-owned JSON facade.
- Added `python/valuescope/api.py` with `/api/generate-report`.
- Added the React report workspace and sample snapshot at `public/samples/company_report_snapshot.json`.
- Ran live `000858` generation and replaced the toy sample with a richer generated A-share snapshot.
- Converted the report UI to Chinese-first display and added curated Chinese table/section mapping.
- Added explicit Sprint 001 MVP sections for cash flow, capital safety, and shareholder returns.
- Tightened annual history so unverified 2025 data is excluded; the current sample covers 1995 through 2024 and shows a warning for the excluded 2025 row.
- Filtered shareholder-return/retained-earnings windows to the same confirmed annual coverage set.
- Expanded `docs/backlog.md` with report reproduction stories:
  - annual report rows
  - metric definitions and rating rules
  - valuation overview
  - owner earnings analysis
  - pricing power and operating quality
  - financial safety
  - cash flow and EPS quality
  - shareholder returns
  - share capital diagnostics
  - data quality warnings
  - bank branch
  - technical/market context
  - as-of report mode

## Next Best Step

Plan Sprint 002 from the completed Sprint 001 baseline. The React report UI renders a generated `000858` A-share snapshot in Chinese, with core sections, warnings, full annual history, and no database dependency. The next best product/engineering step is to replace the conservative annual cutoff with explicit provider-level `REPORT_TYPE=年报` provenance when the data adapter exposes it, then add a dedicated share-capital/diagnostics table.

Recommended next planning questions:

- Which capability-map stories belong in Sprint 002 now that Sprint 001 is closed?
- Should `/api/generate-report` become a background job/status flow if live generation is slow?
- Which copied legacy modules should remain visible in Sprint 001 versus hidden behind the facade?
- Which fields need richer labels, units, and Chinese metric language so the React report feels as informative as the original HTML?
- How should ValueScope store annual-report provenance so quarterly/interim data can never be mistaken for annual history?

## Guardrails

- No database for normal MVP use.
- UI-triggered generation uses a local FastAPI bridge. This is a local process boundary, not a database or cloud backend.
- A shares are the first market, not the permanent product boundary.
- Missing financial values must remain distinct from zero.
- Every report metric needs basis, unit, warning, missing, or not-applicable context.
- Future screen results need pass, fail, or missing-data explanation.
- Avoid buy/sell language that sounds like investment advice.
- Keep changes tied to the current sprint unless the user explicitly changes scope.
- Use gstack skill routing from `AGENTS.md` and `CLAUDE.md` when available.

## Reference Projects

- `/Users/dingyitian/Desktop/stock-scripts`: financial report capability and metric reference only; do not import or wrap it at runtime.
- ValueScope now contains a copied, namespaced version of `stock-scripts` in `python/valuescope/legacy_stock_scripts`; new code should use `valuescope.report_snapshot`, not import legacy modules directly.
- `/Users/dingyitian/Desktop/QuantumValue-Terminal`: product experience reference only.

## Session Closeout Requirement

Before ending a coding session:

- Update `docs/progress.md` if a task or story advanced.
- Update this file if the next AI session needs different context.
- Append a short entry to `docs/working-log.md` for non-trivial sessions.
