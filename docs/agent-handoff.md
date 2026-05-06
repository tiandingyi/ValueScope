# Agent Handoff

Read this file first in every new AI coding session. It summarizes the current state, what was just done, and the safest next step.

## Current State

ValueScope is a new greenfield project at `/Users/dingyitian/Desktop/ValueScope`.

Sprint 002 is complete. The project has a runnable Python/FastAPI backend, Vite/React frontend, copied `stock-scripts` engine under a legacy namespace, a ValueScope report snapshot facade, tests, and a generated v0.3 sample snapshot.

## Product Direction

ValueScope is a local-first value investing research workstation and screener. The first version reproduces the A-share financial report workflow from `stock-scripts` as ValueScope-owned Python data generation plus a React report UI. Dynamic factor screening comes later.

## Current Sprint

Sprint 002: Full Report Parity with stock-scripts.

Sprint goal: reproduce the complete visual and informational richness of the stock-scripts pricing-power HTML report inside ValueScope's React UI.

Status: Sprint 002 goal-mode HTML parity and user-feedback UX correction closure completed on 2026-05-06.

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
- Frontend design polish completed:
  - Sprint 002 Goal-Mode story cards US-006 through US-017 were added to `docs/sprints/sprint-002.md`.
  - Report cover now separates company identity from inspectable metadata and shows currency/accounting unit.
  - A generated sticky report reading index helps navigate dense report sections.
  - Side rail now shows report mode, schema, source, currency, accounting unit, and coverage period.
  - Tables have bounded vertical scrolling, sticky headers, and the first column remains visible.
  - Valuation badge color mapping now translates snapshot `green`/`yellow`/`red` into UI tone classes.
- Data-quality fix completed:
  - A-share `ocf` is now extracted from annual cash-flow statement fields in `fetch_cashflow_extras()`.
  - Old raw cache missing `ocf` triggers cash-flow extras rebuild and `year_data` rebuild.
  - Valuation history no longer mislabels `reported_shares` as `legacy_shares`.
  - Share-basis diagnostics now distinguish verified share-change rows from profit/EPS-derived implied share counts.
  - Regenerated `public/samples/company_report_snapshot.json`; sample OCF coverage is now 27/30 annual rows.
- HTML parity gap story cards were created in `docs/backlog.md`:
  - US-025 share-basis diagnostics first-class section
  - US-026 structured data-quality/confidence panel
  - US-027 Williams %R technical indicator module
  - US-028 valuation scenarios/resonance/formula appendix
  - US-029 detailed operating/safety/shareholder radar modules
  - US-030 machine summary for AI parsing
  - US-031 repeatable HTML parity QA gate
- Goal-mode implementation completed for US-025 through US-031:
  - snapshot schema is now `0.3.0`
  - runtime sections include `data_quality`, `machine_summary`, `share_basis`, `technicals`, `valuation_scenarios`, `valuation_formulas`, and `radar_modules`
  - `npm run test:parity` writes `test-results/html-compare-report.json` and comparison screenshots, checks required parity sections, and fails on ValueScope mobile overflow
  - latest parity run: ValueScope mobile overflow `false`, reference mobile overflow `true`, ValueScope table count `16`
- Goal-mode UX correction implementation completed for US-032 through US-045 after live page critique:
  - top-right ticker/year/generate controls moved into the left rail
  - central jump buttons moved into the left-rail report directory and E2E verifies left-rail `#cash_flow` navigation
  - data quality and machine summary now render as end appendices
  - `巴芒总览` emphasizes `业务纯度` and shows the OE per-share basis behind OE yield comparisons
  - major metric sections render as colored value cards
  - historical EPS/OE/OCF/share and quality cells use trend or threshold coloring
  - PE/EPS charts now show axes and unclipped current/median labels
  - cash-flow source noise is hidden from the visible table and capex/net-income is quality-colored
  - capital safety history includes ROIC and interest coverage
  - shareholder returns use the longest confirmed annual window and include Buffett's one-dollar retained-earnings test
  - global 10-year yields are framed as a separate appendix; unavailable country series are marked missing rather than fabricated
  - latest UX/parity run: ValueScope mobile overflow `false`, reference mobile overflow `true`, ValueScope table count `17`

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
  - upgraded report snapshot schema to v0.3
  - added `current_price`, `market_context`, enhanced valuation badges/explanations, PE/EPS percentile nodes, and normalized yearly arrays
  - added `data_quality`, `machine_summary`, `share_basis`, `technicals`, `valuation_scenarios`, `valuation_formulas`, and `radar_modules`
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

Start Sprint 003 from refinement rather than missing Sprint 002 surfaces.

Immediate next options:

1. Split `radar_modules` into separate first-class UI modules if the product needs the same density as stock-scripts for every radar.
2. Make `巴芒总览` snapshot-native instead of deriving it from section-tone heuristics in React.
3. Generalize the v0.3 sections for non-A-share markets and as-of mode.
4. Keep `npm run test:parity` in the verification loop for any further report UI changes.
5. Add real multi-country 10-year yield data sources before turning the macro-yield appendix into a broader market dashboard.

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
- The committed sample is `public/samples/company_report_snapshot.json` using schema v0.3. It intentionally compresses bond-yield history to month-end points plus the latest point to keep the JSON inspectable.
- `/Users/dingyitian/Desktop/QuantumValue-Terminal`: product experience reference only.

## Session Closeout Requirement

Before ending a coding session:

- Update `docs/progress.md` if a task or story advanced.
- Update this file if the next AI session needs different context.
- Append a short entry to `docs/working-log.md` for non-trivial sessions.
