# ADR-003: Local FastAPI Bridge for UI-Triggered Report Generation

## Status

Accepted

## Date

2026-05-05

## Context

Sprint 001 needs the React report workspace to trigger ValueScope-owned Python report generation. A browser-only Vite app cannot safely start a local Python process directly.

The project still has a hard no-database constraint for normal MVP use, and the generated `company_report_snapshot.json` remains the contract between Python generation and React rendering.

## Decision

Add a local FastAPI backend as a generation bridge.

```text
React report workspace
  -> POST /api/generate-report
  -> FastAPI local backend
  -> valuescope.report_snapshot.generate_report_snapshot()
  -> valuescope.legacy_stock_scripts copied engine
  -> data/report_snapshots/company_report_snapshot.json
  -> React validates with Zod and renders
```

The backend is local process orchestration, not a database layer and not a cloud service. The React app can still render committed or imported snapshots without generation.

## Consequences

Positive:

- The user can generate a report from the UI.
- Python remains the owner of financial data generation.
- React stays behind the JSON snapshot contract.
- Provider and computation failures can be surfaced as API errors or snapshot warnings.

Negative:

- Normal interactive generation now requires running a local API process.
- The project has one more dev command and one more failure boundary.
- Long-running provider calls can make `/api/generate-report` slow until a job/status model is added.

## Revisit Triggers

Revisit if:

- Report generation routinely takes long enough that a blocking HTTP request feels bad.
- Packaging becomes a priority and a desktop shell is needed.
- Multiple concurrent report generations are required.
- A future cloud product needs a different API boundary.
