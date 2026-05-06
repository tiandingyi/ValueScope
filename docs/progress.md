# Progress Log

This file is the human-readable project memory. Update it whenever a story, task, or meaningful planning step is completed.

## Entry Format

```md
## YYYY-MM-DD

### US-000 or Task Name

Status: Done | In Progress | Blocked | Superseded

Changed:
- What changed.

Verified:
- Command, screenshot, or document check.

Next:
- The next concrete step.

Notes:
- Decisions, tradeoffs, or risks future agents should know.
```

## 2026-05-06

### Sprint 002 Parity Closure Implementation Pass

Status: In Progress

Changed:

- Implemented major parity-gap UI additions in `src/App.tsx` and `src/styles.css`:
  - report header now includes generated time
  - sticky report identity bar now appears after scroll threshold (`>=100px`)
  - added a dedicated `巴芒总览` summary block
  - added valuation overview context paragraph before valuation audit details
  - added machine-readable valuation summary table for valuation cards
  - expanded market trend meaning table with low-rate sideways scenario row
  - unified line-chart insufficient-data rule to `<3 points -> 数据不足，无法绘图`
  - added OE yearly yield table threshold coloring (`>=8` green, `4-8` yellow, `<4` red)
- Generated fresh 600285 snapshot for parity baseline comparison.

Verified:

- `PYTHONPATH=python python3 -m valuescope.cli 600285 --years 20`
- `PYTHONPATH=python python3 -m pytest tests/python -q`
- `npm run build`
- `npm test -- --run`
- `npm run test:e2e`

Next:

- Re-run side-by-side visual comparison with the 600285 stock-scripts HTML report and list any remaining structural gaps.
- Decide whether `巴芒总览` should remain heuristic or become a snapshot-native section.

Notes:

- This pass focuses on parity closure and AC alignment; no database or cloud dependency was introduced.

### Sprint 002 Story Coverage Audit

Status: Done

Changed:

- Audited Sprint 002 user-story completeness against the stock-scripts capability map and current implementation behavior.
- Updated `docs/sprints/sprint-002.md` with a post-review addendum that:
  - tightens acceptance criteria for US-006 through US-012
  - adds missing parity stories US-013 through US-017 (share-capital diagnostics, data-quality consistency, as-of mode, bank branch, multi-market readiness)
  - defines a revised sprint completion gate for strict closure.

Verified:

- Document cross-check:
  - `docs/sprints/sprint-002.md`
  - `docs/reference/stock-scripts-capability-map.md`
  - implementation references in `src/App.tsx`, `src/reportSnapshot.ts`, and `python/valuescope/report_snapshot.py`

Next:

- Implement tightened AC deltas first (sticky trigger threshold, chart insufficient-data rule, OE yield table threshold coloring).
- Then execute US-013 and US-014 as required for strict Sprint 002 closure.

Notes:

- This update improves story-card completeness and testability; it does not change runtime code behavior by itself.

### Sprint 002 Full Report Parity Pass

Status: Done

Changed:

- Upgraded company report snapshot schema to v0.2.
- Added `current_price`, `market_context`, `pe_percentile`, and `eps_percentile` to the Python snapshot facade.
- Normalized market environment data from the copied legacy engine into an inspectable monthly bond-yield chart series plus market/stock risk-premium fields.
- Enhanced valuation items with `badge`, `badge_color`, `what_it_measures`, `meaning`, and `implication`, preserving OE-DCF sensitivity text from the source metric language.
- Added React rendering for the 4-column report header, colored green/yellow/red explanation words, sticky company/code/price bar, market environment cards, risk-premium callout, line charts, PE/EPS percentile panels, and scrollable yearly tables.
- Regenerated the committed `000858` sample snapshot using `--years 10`.
- Updated tests to assert v0.2 fields and new UI sections.
- Updated `README.md`, `docs/report-snapshot-schema.md`, and `docs/sprints/sprint-002.md`.

Verified:

- `PYTHONPATH=python python3 -m valuescope.cli 000858 --years 10`
- `PYTHONPATH=python python3 -m pytest tests/python -q`
- `npm test -- --run`
- `npm run build`
- `npm run test:e2e`
- Captured desktop and mobile Sprint 002 screenshots:
  - `test-results/current-valuescope-sprint2-desktop.png`
  - `test-results/current-valuescope-sprint2-mobile.png`

Next:

- Decide Sprint 003 scope. Good candidates: provider-level annual `REPORT_TYPE=年报` provenance, dedicated share-capital diagnostics table, or background job/status UX for slower live generation.

Notes:

- No database dependency was added.
- No buy/sell guidance language was added.
- The market context section degrades to `数据缺失`; missing `current_price` renders as `—`.
- The committed market-context chart series is compressed to month-end points plus the latest point so the sample remains inspectable.

## 2026-05-05

### Sprint 001 Runnable Skeleton

Status: Done

Changed:

- Added Python package scaffolding under `python/valuescope`.
- Copied the `stock-scripts` report engine under `valuescope.legacy_stock_scripts`.
- Added `valuescope.report_snapshot.generate_report_snapshot()` as the JSON facade.
- Added FastAPI local bridge with `/api/health` and `/api/generate-report`.
- Added Vite/React report workspace with Zod validation and a committed sample snapshot.
- Added Python, Vitest, and Playwright tests.
- Added ADR-003 for the local FastAPI generation bridge.

Verified:

- `PYTHONPATH=python python3 -m py_compile python/valuescope/report_snapshot.py python/valuescope/api.py python/valuescope/cli.py python/valuescope/legacy_stock_scripts/run.py python/valuescope/legacy_stock_scripts/core/*.py`
- `PYTHONPATH=python python3 -m pytest tests/python -q`
- `npm test -- --run`
- `npm run build`
- `npm run test:e2e`

Next:

- Decide whether generation needs async job/status handling.

Notes:

- No git commit was made.
- The copied engine is intentionally isolated. New ValueScope code should call the facade.
- The ported share-basis regression test caught and fixed a copied-engine historical share-basis issue.

### Report UI Quality Pass

Status: Done

Changed:

- Compared the current React report workspace against the generated `stock-scripts` HTML report for `000858`.
- Reworked the React report view from a sparse snapshot preview into a report-like page with sticky navigation, report cover, KPI strip, warning band, trend panel, side facts, denser section cards, and formatted annual rows.
- Fixed metric row layout so long values and missing-state text do not overlap or split awkwardly.
- Updated unit and e2e assertions to match the new report UI.

Verified:

- `npm test -- --run`
- `npm run build`
- `npm run test:e2e`
- Captured visual QA screenshots under `test-results/`, including `current-valuescope-after-value-fix.png`.

Next:

- Run live `000858` generation and inspect `data/report_snapshots/company_report_snapshot.json`.
- Promote more of the original `stock-scripts` report structure into first-class JSON sections so the React view has comparable information density.

Notes:

- The UI is now presentable, but still not at original report parity because the committed sample snapshot is intentionally small.
- No git commit was made.

### A-Share Chinese Report Parity Pass

Status: Done

Changed:

- Ran live `000858` report generation and replaced the committed sample snapshot with the richer generated A-share report snapshot.
- Converted the React report display to Chinese-first copy for the A-share MVP: navigation, form labels, states, section titles, side rail, table headers, metric labels, and common finance text.
- Promoted real generated sections into the UI: investment image overview, quality, pricing power, valuation anchors, annual financial rows, valuation history, diagnostics, owner earnings yield history, retained earnings check, and metric explanations.
- Added curated Chinese table columns and value formatting for money, percentages, days, and share-basis text.
- Fixed desktop and mobile layout issues found by screenshot review, including long metric values, nested diagnostics data, and mobile card wrapping.
- Ignored generated `data/raw/` cache artifacts.

Verified:

- `PYTHONPATH=python python3 -m valuescope.cli 000858 --years 8`
- `PYTHONPATH=python python3 -m pytest tests/python -q`
- `npm test -- --run`
- `npm run build`
- `npm run test:e2e`
- Captured desktop and mobile screenshots:
  - `test-results/current-valuescope-chinese-report-desktop.png`
  - `test-results/current-valuescope-chinese-report-mobile.png`

Next:

- Continue reducing remaining mixed finance abbreviations where useful, especially PEG/PEGY/OE terminology in formulas.
- Add a dedicated diagnostic/share-capital table instead of hiding nested diagnostic details.

Notes:

- No git commit was made.
- The generated sample is larger than the toy sample, but it now reflects the real A-share report workflow and makes visual parity testable.

### Annual History Acceptance Tightening

Status: Done

Changed:

- Strengthened Sprint 001 and backlog AC so annual history must include all available annual-report years, not only the latest five rows.
- Added schema rules that quarterly/interim periods must not appear in annual report history.
- Updated the report snapshot facade to request full available annual history from the legacy engine and filter table rows to annual-report periods.
- Updated the React report table renderer to show every row present in the snapshot instead of `slice(-5)`.
- Regenerated the `000858` sample snapshot. A later provenance pass superseded this sample so unverified 2025 data is excluded from annual history.

Verified:

- `PYTHONPATH=python python3 -m valuescope.cli 000858 --years 8`
- `PYTHONPATH=python python3 -m pytest tests/python -q`
- `npm test -- --run`
- `npm run build`
- `npm run test:e2e`
- Captured `test-results/current-valuescope-all-annual-history.png`.

Next:

- Add explicit provenance fields for annual rows so the UI can distinguish confirmed annual reports from any provider row that merely uses a `YYYY1231` key.

Notes:

- Superseded by the confirmed annual provenance rule below.

### Confirmed Annual Provenance Rule

Status: Done

Changed:

- Updated Sprint 001, backlog, and report snapshot schema so annual rows must carry report type, source, and provenance.
- Added schema rules for `confirmed_annual`, `confirmed_annual_by_conservative_cutoff`, and `unverified` provenance.
- Changed the snapshot facade so unverified previous-fiscal-year rows are excluded from annual history. For the current 2026 run, the unverified `2025` row is excluded and `2024` remains the latest annual year.
- Regenerated the `000858` sample snapshot. `coverage.years` now runs from 1995 through 2024.
- Added a Python regression test covering exclusion of an unverified previous-fiscal-year `YYYY1231` row.

Verified:

- `PYTHONPATH=python python3 -m valuescope.cli 000858 --years 8`
- `PYTHONPATH=python python3 -m pytest tests/python -q`
- `npm test -- --run`
- `npm run build`
- `npm run test:e2e`
- Captured `test-results/current-valuescope-confirmed-annual-history.png`.

Next:

- Replace the conservative cutoff with provider-level `REPORT_TYPE=年报` when the data adapter exposes that field.

Notes:

- The current conservative rule is intentional: without explicit provider annual-report metadata, the previous fiscal year is not trusted.
- The generated warning explicitly says 2025 was excluded for lacking verifiable annual-report provenance.

### Sprint 001 Completion Closeout

Status: Done

Changed:

- Added explicit MVP report sections for cash flow, capital safety, and shareholder returns in the snapshot facade.
- Filtered retained-earnings/shareholder-return rows to the confirmed annual coverage years and recomputed the summary window, so the `000858` sample ends at 2024 instead of using unverified 2025 data.
- Regenerated the committed sample snapshot with 30 confirmed annual rows from 1995 through 2024 and visible warning text for the excluded 2025 row.
- Updated React section copy, table columns, and tests so the report renders the full Sprint 001 section set in Chinese.
- Updated README with one-command generator, app, FastAPI, and validation instructions.

Verified:

- `PYTHONPATH=python python3 -m valuescope.cli 000858 --years 8`
- `PYTHONPATH=python python3 -m pytest tests/python -q`
- `npm test -- --run`
- `npm run build`
- `npm run test:e2e`
- Captured desktop and mobile Sprint 001 screenshots:
  - `test-results/current-valuescope-sprint1-desktop.png`
  - `test-results/current-valuescope-sprint1-mobile.png`

Next:

- Start Sprint 002 planning from provider-level annual-report provenance and dedicated share-capital diagnostics.

Notes:

- No git commit was made.
- Sprint 001 is functionally complete under the current conservative annual-report rule.

### Add GStack Skill Routing

Status: Done

Changed:

- Added gstack skill routing rules to `AGENTS.md`.
- Expanded the skill routing section in `CLAUDE.md`.
- Updated `docs/agent-handoff.md` so future sessions know routing is available.

Verified:

- Searched for `GStack Skill Routing` and `/plan-eng-review` in the updated docs.

Next:

- Use `/plan-eng-review` before Sprint 001 implementation.

Notes:

- Routing is documentation for AI agents, not runtime code or a business dependency.

### Project Setup and Planning Docs

Status: Done

Changed:

- Created the `ValueScope` project directory.
- Added the initial README and design brief.
- Added lightweight Scrum docs: roadmap, backlog, Sprint 001, snapshot schema, and ADR-001.
- Added agent instructions for Codex, Claude Code, and GitHub Copilot.
- Added this progress log, agent handoff, and working log protocol.

Verified:

- Listed project files with `rg --files`.
- Confirmed `.github/copilot-instructions.md` exists.

Next:

- Review stock-scripts report sections and choose the first report parity slice.
- Initialize the runnable app skeleton.
- Initialize the ValueScope-owned Python report generator skeleton.
- Create a sample `company_report_snapshot.json`.

Notes:

- The project is documentation-only right now. No app framework has been installed.
- MVP market is A shares, but the product name and architecture must support future global equities.
- Normal MVP use must not require a database.

### Sprint 001 Reorientation

Status: Done

Changed:

- Reoriented Sprint 001 from dynamic factor screening to single-stock financial report reproduction.
- Added `docs/report-snapshot-schema.md` for `company_report_snapshot.json`.
- Updated roadmap, backlog, sprint, README, ADR-002, and agent instructions so report parity comes before screening.

Verified:

- Ran `rg` checks for stale Sprint 001 and `screen_snapshot.json` references.
- Confirmed `docs/sprints/sprint-001.md` now targets report snapshot generation and React report rendering.

Next:

- Inspect stock-scripts report output and implementation structure.
- Define the first report parity slice in implementation terms.
- Scaffold the Python generator and React app.

Notes:

- `stock-scripts` is a reference only. ValueScope must own its Python report pipeline and React renderer.
- Screening is Phase 3 after report data quality and presentation are trustworthy.

### stock-scripts Capability Audit

Status: Done

Changed:

- Read the `stock-scripts` project structure, report pipeline, data providers, valuation logic, assessment logic, renderer, screening scripts, docs, and share-basis test.
- Added `docs/reference/stock-scripts-capability-map.md`.
- Expanded `docs/backlog.md` with report reproduction stories US-012 through US-024.
- Fixed stale Sprint 001 wording so the first screen is the report workspace, not the screener workspace.

Verified:

- Ran `rg --files`, `wc -l`, `rg -n`, and targeted `sed` reads across `/Users/dingyitian/Desktop/stock-scripts`.
- Checked ValueScope docs for stale `screener workspace` wording.
- Reviewed the new capability map and backlog sections.

Next:

- Run `/plan-ceo-review` and `/plan-eng-review` on the capability map and backlog.
- After reviews, scaffold the ValueScope-owned Python report snapshot generator and React report workspace.

Notes:

- The first implementation boundary should be `company_report_snapshot.json`, roughly replacing the argument payload currently passed into `stock-scripts/core/render.py:render_html`.
- Share-basis semantics are a high-risk contract and need early regression tests.
- Screening work should wait until report-grade metrics and missing-state semantics are trustworthy.
