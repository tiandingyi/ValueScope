# GitHub Copilot Instructions

ValueScope is a local-first value investing screener. The MVP focuses on A-share dynamic factor screening, but code should not hard-code the product to A shares forever.

## Core Rules

- Do not introduce a database dependency for MVP functionality.
- Use local JSON snapshots as the primary data contract.
- Preserve the difference between `null` and `0` in financial metrics.
- Explain screen results with pass, fail, and missing-data reasons.
- Avoid investment-advice language such as "you should buy" or "you should sell".
- Keep global expansion in mind when naming market, currency, and accounting fields.

## Current MVP

Build toward Sprint 001:

- Load `screen_snapshot.json`.
- Show metadata: generated time, universe, row count, schema version.
- Add basic factor filters.
- Show sortable results.
- Explain why each result passed or failed.

## Relevant Docs

- `docs/sprints/sprint-001.md`
- `docs/snapshot-schema.md`
- `docs/backlog.md`
- `docs/decisions/ADR-001-local-json-no-db.md`

## Coding Preferences

- Prefer clear typed data models for snapshot rows and metric definitions.
- Keep filtering logic pure and testable.
- Keep UI state explicit.
- Do not hide missing data by coercing it to zero, empty string, or false.
- Use sample data that looks realistic enough to test the workflow.
