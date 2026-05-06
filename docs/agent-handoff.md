# Agent Handoff

Read this file first in every new AI coding session. It summarizes the current state, what was just done, and the safest next step.

## Current State

ValueScope is a new greenfield project at `/Users/dingyitian/Desktop/ValueScope`.

Sprint 002 is complete. The project has a runnable Python/FastAPI backend, Vite/React frontend, copied `stock-scripts` engine under a legacy namespace, a ValueScope report snapshot facade, tests, and a generated v0.2 sample snapshot.

## Product Direction

ValueScope is a local-first value investing research workstation and screener. The first version reproduces the A-share financial report workflow from `stock-scripts` as ValueScope-owned Python data generation plus a React report UI. Dynamic factor screening comes later.

## Current Sprint

Sprint 002: Full Report Parity with stock-scripts.

Sprint goal: reproduce the complete visual and informational richness of the stock-scripts pricing-power HTML report inside ValueScope's React UI.

Status: In progress after parity-closure implementation pass on 2026-05-06.

- A coverage audit addendum was added to `docs/sprints/sprint-002.md`.
- Existing stories US-006 through US-012 now have stricter, machine-checkable AC.
- Missing parity stories US-013 through US-017 were added (share-capital diagnostics, data-quality consistency, as-of mode, bank branch, multi-market readiness).
- UI implementation pass completed for major closure items in `src/App.tsx` and `src/styles.css`:
  - generated time in header
  - sticky bar threshold behavior
  - `巴芒总览` summary block
  - valuation overview context paragraph
  - valuation machine-readable summary table
  - market trend table third scenario row
  - chart insufficient-data rule and OE yield threshold coloring

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
- Completed Sprint 002 report parity:
  - upgraded report snapshot schema to v0.2
  - added `current_price`, `market_context`, enhanced valuation badges/explanations, PE/EPS percentile nodes, and normalized yearly arrays
  - rendered market environment cards and bond-yield line chart
  - rendered valuation badges, "衡量什么/背后含义" explanations, PE/EPS charts, percentile panels, and scrollable yearly tables
  - regenerated the committed `000858` sample snapshot with `--years 10`
  - captured Sprint 002 desktop/mobile screenshots in `test-results/`
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

Execute the tightened Sprint 002 delta items before starting Sprint 003.

Immediate implementation order:

1. Re-run side-by-side visual QA against the 600285 reference HTML and record remaining gaps with screenshots.
2. Decide whether `巴芒总览` should become snapshot-native (currently rendered from section-tone heuristics).
3. Implement US-013 (share-capital diagnostics section).
4. Implement US-014 (data-quality consistency contract + fixture coverage).
5. Move US-015 through US-017 to Sprint 003 only with explicit rationale if not implemented now.

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
- The committed sample is `public/samples/company_report_snapshot.json` using schema v0.2. It intentionally compresses bond-yield history to month-end points plus the latest point to keep the JSON inspectable.
- `/Users/dingyitian/Desktop/QuantumValue-Terminal`: product experience reference only.

## Session Closeout Requirement

Before ending a coding session:

- Update `docs/progress.md` if a task or story advanced.
- Update this file if the next AI session needs different context.
- Append a short entry to `docs/working-log.md` for non-trivial sessions.
