# Agent Handoff

Read this file first in every new AI coding session. It summarizes the current state, what was just done, and the safest next step.

## Current State

ValueScope is a new greenfield project at `/Users/dingyitian/Desktop/ValueScope`.

The project is currently documentation-only. The app stack has been chosen, but no application code exists yet.

## Product Direction

ValueScope is a local-first value investing research workstation and screener. The first version reproduces the A-share financial report workflow from `stock-scripts` as ValueScope-owned Python data generation plus a React report UI. Dynamic factor screening comes later.

## Current Sprint

Sprint 001: Reproduce Single-Stock Financial Report.

Sprint goal: create the first runnable workflow that generates a local single-stock financial report snapshot and renders the report in React.

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

Run `/plan-ceo-review` and `/plan-eng-review` against the stock-scripts capability map and expanded backlog, then initialize the app and Python generator skeleton for Sprint 001.

Recommended next planning questions:

- Which capability-map stories are truly Sprint 001 versus later?
- What is the exact `company_report_snapshot.json` v0 sample?
- Which sample company should prove the first report workflow?
- What Python command generates the report snapshot?
- What frontend command renders the report snapshot?

## Guardrails

- No database for normal MVP use.
- A shares are the first market, not the permanent product boundary.
- Missing financial values must remain distinct from zero.
- Every report metric needs basis, unit, warning, missing, or not-applicable context.
- Future screen results need pass, fail, or missing-data explanation.
- Avoid buy/sell language that sounds like investment advice.
- Keep changes tied to the current sprint unless the user explicitly changes scope.
- Use gstack skill routing from `AGENTS.md` and `CLAUDE.md` when available.

## Reference Projects

- `/Users/dingyitian/Desktop/stock-scripts`: financial report capability and metric reference only; do not import or wrap it.
- `/Users/dingyitian/Desktop/QuantumValue-Terminal`: product experience reference only.

## Session Closeout Requirement

Before ending a coding session:

- Update `docs/progress.md` if a task or story advanced.
- Update this file if the next AI session needs different context.
- Append a short entry to `docs/working-log.md` for non-trivial sessions.
