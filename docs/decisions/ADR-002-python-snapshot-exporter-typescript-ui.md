# ADR-002: ValueScope-Owned Python Data Pipeline and TypeScript UI Boundary

## Status

Accepted

## Date

2026-05-05

## Context

ValueScope needs a local-first financial report UI first, then a screening UI later. It also needs to own the data generation path. `/Users/dingyitian/Desktop/stock-scripts` is a reference project with proven A-share report structure, metric language, and workflows, not a dependency that ValueScope should import, wrap, or require at runtime.

The UI should not directly perform financial data collection. It should consume inspectable local JSON snapshots that can be generated, archived, validated, and shared. The data pipeline that creates those snapshots should live in ValueScope.

## Decision

Use a two-layer architecture:

```text
ValueScope data pipeline / Python
  -> reproduce stock-scripts-style report calculations first
  -> compute and persist report-grade stock metrics
  -> generate company_report_snapshot.json
  -> later generate screen_snapshot.json from report-grade metrics
  -> preserve metric semantics, source notes, and freshness metadata

ValueScope / Vite + React + TypeScript
  -> validate local JSON snapshots with Zod
  -> render the financial report in React first
  -> call a local FastAPI bridge when the user triggers Python generation from the UI
  -> later run client-side factor screening
```

The ValueScope app stack is Vite, React, TypeScript, Zod, Vitest, Playwright, FastAPI, and ValueScope-owned Python.

Sprint 001 should reproduce the single-stock financial report path first. It does not include universe screening. Screening comes after report generation and React report rendering are trustworthy.

## Consequences

Positive:

- The UI stays local-first. Rendering a committed or imported snapshot does not require Python, while UI-triggered generation uses the local FastAPI bridge.
- Python remains the right place for ValueScope-owned financial data generation.
- JSON contracts become the stable boundary between data generation, report rendering, and later screening.
- Tests can split cleanly: Python pipeline tests for report generation, TypeScript tests for validation and report rendering, later tests for filtering, sorting, and explanations.
- ValueScope can replace stock-scripts over time without coupling to its internals.

Negative:

- The schema must be explicit enough for both Python producers and TypeScript consumers.
- Reproducing stock-scripts-style report capability is more work than wrapping it.
- Any metric semantic intentionally borrowed from stock-scripts must be documented in ValueScope's own schema and tests.
- Screening is deferred until report parity has a credible foundation.

## Non-Decision

This does not require implementing every stock-scripts capability in Sprint 001. It fixes the ownership boundary and product order: ValueScope owns the generator, treats stock-scripts as a reference only, reproduces report capability first, and adds screening later.
