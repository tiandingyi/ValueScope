# GitHub Copilot Instructions

ValueScope is a local-first value investing research workstation and screener. The MVP first reproduces the A-share financial report workflow from `stock-scripts` with ValueScope-owned Python data generation and a React report UI. Dynamic factor screening comes later.

## Core Rules

- Do not introduce a database dependency for MVP functionality.
- Use local JSON snapshots as the primary data contracts.
- Preserve the difference between `null` and `0` in financial metrics.
- Explain report metrics with basis, units, warnings, and missing/not-applicable states.
- Avoid investment-advice language such as "you should buy" or "you should sell".
- Keep global expansion in mind when naming market, currency, and accounting fields.

## Current MVP

Build toward Sprint 001:

- Generate `company_report_snapshot.json`.
- Load the report snapshot locally.
- Show metadata: generated time, company identity, market, coverage years, schema version.
- Render stock-scripts-style report sections in React.
- Show missing, warning, and not-applicable states near affected metrics.

## Relevant Docs

- `docs/agent-handoff.md`
- `docs/progress.md`
- `docs/working-log.md`
- `docs/sprints/sprint-001.md`
- `docs/report-snapshot-schema.md`
- `docs/snapshot-schema.md`
- `docs/backlog.md`
- `docs/decisions/ADR-001-local-json-no-db.md`
- `docs/decisions/ADR-002-python-snapshot-exporter-typescript-ui.md`

## Coding Preferences

- Prefer clear typed data models for snapshot rows and metric definitions.
- Keep report generation and rendering logic pure and testable where possible.
- Keep UI state explicit.
- Do not hide missing data by coercing it to zero, empty string, or false.
- Use sample data that looks realistic enough to test the workflow.

## Session Memory

When making meaningful changes:

- Update `docs/progress.md` with what changed, how it was verified, and what is next.
- Update `docs/agent-handoff.md` if the next coding session needs new context.
- Add a short `docs/working-log.md` entry for non-trivial implementation or debugging.
