# Working Log

This file captures session-level details that may save future agents time. It is more granular than `docs/progress.md`.

## Entry Format

```md
## YYYY-MM-DD HH:MM

Task:
- What the session tried to do.

Files Changed:
- Paths changed.

Commands:
- Commands run and important results.

Decisions:
- Small decisions not worth a full ADR.

Problems:
- Errors, failed attempts, or things to avoid next time.

Next:
- Next concrete action.
```

## 2026-05-05 21:45

Task:

- Created persistent project memory docs so new AI sessions can understand current state and continue safely.

Files Changed:

- `docs/progress.md`
- `docs/agent-handoff.md`
- `docs/working-log.md`
- `AGENTS.md`
- `CLAUDE.md`
- `.github/copilot-instructions.md`
- `docs/agents/codex.md`
- `docs/agents/claude-code.md`
- `docs/agents/github-copilot.md`

Commands:

- `rg --files` to verify the project file list.

Decisions:

- Use `docs/agent-handoff.md` as the first-read file for new AI coding sessions.
- Use `docs/progress.md` for user-story and milestone progress.
- Use `docs/working-log.md` for session-level implementation notes.

Problems:

- No app stack exists yet, so validation is limited to file existence and document consistency.

Next:

- Run engineering planning for Sprint 001 and initialize the app skeleton.

## 2026-05-05 21:55

Task:

- Added gstack skill routing to the project docs.

Files Changed:

- `AGENTS.md`
- `CLAUDE.md`
- `docs/agent-handoff.md`
- `docs/progress.md`
- `docs/working-log.md`

Commands:

- Used text search to verify routing phrases were present.

Decisions:

- Routing belongs in project docs, not runtime code.
- `AGENTS.md` and `CLAUDE.md` carry the primary routing rules.

Problems:

- None.

Next:

- Run `/plan-eng-review` before implementation.

## 2026-05-05 22:00

Task:

- Reoriented Sprint 001 based on user direction: report parity before stock screening.

Files Changed:

- `README.md`
- `AGENTS.md`
- `CLAUDE.md`
- `.github/copilot-instructions.md`
- `docs/design-brief.md`
- `docs/product-roadmap.md`
- `docs/backlog.md`
- `docs/sprints/sprint-001.md`
- `docs/snapshot-schema.md`
- `docs/report-snapshot-schema.md`
- `docs/decisions/ADR-002-python-snapshot-exporter-typescript-ui.md`
- `docs/progress.md`
- `docs/agent-handoff.md`
- `docs/working-log.md`

Commands:

- `rg -n "first version|Sprint 001|screen_snapshot|screener|筛选|stock-scripts|company_report|report snapshot|A-Share Screener|Load and Screen" README.md docs AGENTS.md CLAUDE.md .github/copilot-instructions.md`
- `nl -ba` on roadmap, sprint, backlog, schema, and agent files to verify wording.

Decisions:

- Sprint 001 is now `Reproduce Single-Stock Financial Report`.
- First JSON contract is `company_report_snapshot.json`.
- `screen_snapshot.json` is deferred to the later screener phase.
- `stock-scripts` is a reference only; ValueScope owns the Python pipeline.

Problems:

- Several agent docs still had old screener-first wording; updated them so future sessions do not follow stale instructions.

Next:

- Inspect stock-scripts report generation and choose the first report parity slice.
- Scaffold the Python report generator and React report UI after planning is accepted.

## 2026-05-05 22:30

Task:

- Audited `stock-scripts` enough to produce a ValueScope reproduction map and backlog cards before running plan reviews.

Files Changed:

- `docs/reference/stock-scripts-capability-map.md`
- `docs/backlog.md`
- `docs/sprints/sprint-001.md`
- `docs/progress.md`
- `docs/agent-handoff.md`
- `docs/working-log.md`

Commands:

- `rg --files /Users/dingyitian/Desktop/stock-scripts`
- `wc -l` over stock-scripts files
- `rg -n` for functions and report assembly paths in `core/assessment.py`, `core/valuation.py`, `core/render.py`, `core/orchestrator.py`, `core/data_a.py`, `core/data_hk_us.py`, `core/technicals.py`
- `sed` reads of stock-scripts docs and render/orchestrator signatures
- `rg -n "screener workspace|first screen is the screener|Sprint 001.*screen|screening first|import or wrap|stock-scripts.*dependency" README.md AGENTS.md CLAUDE.md .github docs`

Decisions:

- Treat the `render_html(...)` input boundary as the best reference for ValueScope's first `company_report_snapshot.json` shape.
- Split full report reproduction into explicit backlog stories instead of keeping one vague "full report" card.
- Keep screening cards later and make them reuse report-grade metrics.

Problems:

- `stock-scripts` is large and contains both report generation and multiple screeners; the first implementation must avoid drifting into universe screening too early.
- Share-basis handling is subtle and already has a reference regression test in `stock-scripts`; ValueScope should copy the behavior contract, not the implementation.

Next:

- Run `/plan-ceo-review` and `/plan-eng-review` on `docs/reference/stock-scripts-capability-map.md` and `docs/backlog.md`.
- After review, implement Sprint 001 starting with the JSON schema/sample and generator skeleton.

## 2026-05-05 22:40

Task:

- Implemented the first Sprint 001 runnable skeleton after `/plan-eng-review`.

Files Changed:

- Added Python/FastAPI package files under `python/valuescope`.
- Copied `stock-scripts` core engine under `python/valuescope/legacy_stock_scripts`.
- Added React/Vite source under `src/`, sample data under `public/samples/`, and tests under `tests/`.
- Added `pyproject.toml`, `package.json`, TypeScript/Vite/Vitest/Playwright configs.
- Updated README, ADRs, sprint docs, schema docs, progress, and handoff.

Commands:

- `PYTHONPATH=python python3 -m py_compile ...`
- `PYTHONPATH=python python3 -m pytest tests/python -q`
- `npm install`
- `npm test -- --run`
- `npm run build`
- `npx playwright install chromium`
- `npm run test:e2e`

Decisions:

- Use whole-copy migration for speed, but isolate copied code under `valuescope.legacy_stock_scripts`.
- Expose new code through `valuescope.report_snapshot.generate_report_snapshot()`.
- Add a local FastAPI bridge because the user wants UI-triggered generation.
- Keep React behind the JSON snapshot contract and Zod validation.

Problems:

- Vitest initially picked up Playwright specs; fixed by excluding `tests/e2e/**`.
- Playwright Chromium was not installed; installed it with `npx playwright install chromium`.
- Ported share-basis regression tests caught a copied-engine historical share-basis issue; fixed by preferring `asof_shares` for valuation history.

Next:

- Run live `000858` generation and inspect whether the generated snapshot is too raw or too large for the first React report view.

## 2026-05-06 09:58

Task:

- Responded to visual quality feedback that the React report display was much worse than the original `stock-scripts` report.

Files Changed:

- `src/App.tsx`
- `src/styles.css`
- `src/App.test.tsx`
- `tests/e2e/report-workspace.spec.ts`
- `docs/progress.md`
- `docs/agent-handoff.md`
- `docs/working-log.md`

Commands:

- Read `gstack-design-review` skill guidance for actual rendered visual QA.
- Compared screenshots of current ValueScope and original stock-scripts report.
- `npm test -- --run`
- `npm run build`
- `npm run test:e2e`
- Playwright screenshot capture to `test-results/current-valuescope-after-value-fix.png`

Decisions:

- No more CEO/Eng planning is needed for this issue; the next work is direct report parity implementation and visual QA.
- Kept the page Notion-light and report-oriented, with navigation, report cover, KPI strip, warnings, trend panel, side facts, section cards, and tables.
- Fixed layout defects found by screenshot review rather than relying only on passing tests.

Problems:

- The first visual pass exposed metric row overlap that automated tests did not catch.
- The committed sample snapshot is too small to match the original report's information density; real snapshot inspection is the next product-quality step.

Next:

- Run live `000858` generation through the local FastAPI/Python path.
- Inspect generated JSON and expand section mapping/labels so ValueScope reproduces the old report's actual content, not just its shell.

## 2026-05-06 17:20

Task:

- Audited Sprint 002 user stories for completeness and tightened story definitions after identifying parity-scope gaps.

Files Changed:

- `docs/sprints/sprint-002.md`
- `docs/progress.md`
- `docs/agent-handoff.md`
- `docs/working-log.md`

Commands:

- Compared sprint doc, capability map, and committed sample snapshot.
- Reviewed implementation evidence in `src/App.tsx`, `src/reportSnapshot.ts`, and `python/valuescope/report_snapshot.py`.

Decisions:

- Keep Sprint 002 as the active scope but add a post-review addendum instead of creating a new sprint doc.
- Add stricter, machine-checkable AC for US-006 through US-012.
- Add missing parity stories US-013 through US-017 to prevent scope blind spots.

Problems:

- Existing sprint status said "Done" while several AC checks were not strict enough for deterministic acceptance.

Next:

- Implement tightened AC behavior deltas (sticky threshold, chart insufficient-data rule, OE yield color thresholds).
- Implement US-013 and US-014 before declaring strict Sprint 002 closure.

## 2026-05-06 17:35

Task:

- Executed the parity-closure implementation pass after the Sprint 002 story audit.

Files Changed:

- `src/App.tsx`
- `src/styles.css`
- `docs/progress.md`
- `docs/agent-handoff.md`
- `docs/working-log.md`

Commands:

- `PYTHONPATH=python python3 -m valuescope.cli 600285 --years 20`
- `PYTHONPATH=python python3 -m pytest tests/python -q`
- `npm run build`
- `npm test -- --run`
- `npm run test:e2e`

Decisions:

- Implemented `巴芒总览` as a UI-level summary block driven by existing section item statuses to close visual/structure parity quickly.
- Added valuation machine-readable table directly in the valuation section to improve auditability without changing snapshot schema first.

Problems:

- Initial build failed once due to missing `snapshot` prop wiring in `ReportSectionCard`; fixed by passing snapshot from `ReportView`.

Next:

- Perform strict side-by-side comparison on 600285 and capture remaining mismatch list.
- Decide whether to promote `巴芒总览` from heuristic UI derivation into a snapshot-native contract.

## 2026-05-06 10:25

Task:

- Continued from the strengthened AC and made the A-share report display Chinese-first with real `000858` report content.

Files Changed:

- `.gitignore`
- `public/samples/company_report_snapshot.json`
- `python/valuescope/report_snapshot.py`
- `src/App.tsx`
- `src/styles.css`
- `src/App.test.tsx`
- `src/reportSnapshot.test.ts`
- `tests/e2e/report-workspace.spec.ts`
- `docs/progress.md`
- `docs/agent-handoff.md`
- `docs/working-log.md`

Commands:

- `PYTHONPATH=python python3 -m valuescope.cli 000858 --years 8`
- `PYTHONPATH=python python3 -m pytest tests/python -q`
- `npm test -- --run`
- `npm run build`
- `npm run test:e2e`
- Playwright screenshot captures for desktop and mobile Chinese report pages.

Decisions:

- Because Sprint 001 is A-share report parity, the report display should be Chinese-first instead of bilingual.
- Replaced the tiny sample with a real generated snapshot so UI quality and section density can be judged honestly.
- Render nested diagnostics cautiously; raw nested JSON should not be dumped into the report UI.

Problems:

- Initial desktop screenshot showed nested diagnostics JSON widening the page; fixed by showing only primitive detail fields.
- Initial mobile screenshot showed metric values squeezing labels; fixed by switching metric cards to single-column layout on mobile.
- Superseded later in the session: unverified 2025 rows are now excluded from annual history and shareholder-return windows.

Next:

- Build a dedicated share-capital diagnostics table for the hidden nested diagnostics.

## 2026-05-06 10:36

Task:

- Tightened AC and implementation for annual-history correctness after user clarified that historical data must include all years and latest fiscal data must use annual reports only.

Files Changed:

- `python/valuescope/report_snapshot.py`
- `src/App.tsx`
- `tests/python/test_report_snapshot.py`
- `public/samples/company_report_snapshot.json`
- `docs/backlog.md`
- `docs/sprints/sprint-001.md`
- `docs/report-snapshot-schema.md`
- `docs/progress.md`
- `docs/agent-handoff.md`
- `docs/working-log.md`

Commands:

- `PYTHONPATH=python python3 -m valuescope.cli 000858 --years 8`
- `PYTHONPATH=python python3 -m pytest tests/python -q`
- `npm test -- --run`
- `npm run build`
- `npm run test:e2e`
- Playwright screenshot capture to `test-results/current-valuescope-all-annual-history.png`

Decisions:

- The React renderer must show every annual row present in the snapshot, not the latest five.
- The snapshot facade now asks the legacy engine for full annual history and filters table rows to annual-report periods.
- Coverage years are recomputed from filtered annual rows.

Problems:

- The legacy render payload does not expose a provider-level `REPORT_TYPE`, so the current filter treats `YYYY1231` rows as annual rows.
- A stronger future fix should store annual row provenance explicitly.

Next:

- Add provenance fields to annual rows and data-quality warnings when the provider cannot confirm an annual report type.

## 2026-05-06 10:55

Task:

- Prioritized docs and implementation for confirmed annual-report provenance after user clarified that unverified 2025 data must not be used as annual report data.

Files Changed:

- `docs/report-snapshot-schema.md`
- `docs/sprints/sprint-001.md`
- `docs/backlog.md`
- `docs/progress.md`
- `docs/agent-handoff.md`
- `docs/working-log.md`
- `python/valuescope/report_snapshot.py`
- `tests/python/test_report_snapshot.py`
- `public/samples/company_report_snapshot.json`

Commands:

- `PYTHONPATH=python python3 -m valuescope.cli 000858 --years 8`
- `PYTHONPATH=python python3 -m pytest tests/python -q`
- `npm test -- --run`
- `npm run build`
- `npm run test:e2e`
- Playwright screenshot capture to `test-results/current-valuescope-confirmed-annual-history.png`

Decisions:

- Annual rows now need `report_type`, `report_source`, and `report_provenance`.
- Until provider-level report type is available, previous-fiscal-year `YYYY1231` rows are treated as unverified and excluded.
- Older `YYYY1231` rows can pass through under `confirmed_annual_by_conservative_cutoff`.

Problems:

- The copied legacy AkShare/Sina payload does not expose `REPORT_TYPE=年报` for the rows already passed into the render boundary.
- The conservative cutoff is safer than trusting 2025, but a future adapter should preserve true provider provenance.

Next:

- Push report-type provenance closer to the provider adapter instead of inferring it in the snapshot facade.

## 2026-05-06 11:18

Task:

- Closed Sprint 001 using a goal-driven pass across AC, code, sample data, UI, tests, screenshots, and docs.

Files Changed:

- `python/valuescope/report_snapshot.py`
- `src/App.tsx`
- `src/App.test.tsx`
- `src/reportSnapshot.test.ts`
- `tests/e2e/report-workspace.spec.ts`
- `tests/python/test_report_snapshot.py`
- `public/samples/company_report_snapshot.json`
- `README.md`
- `docs/report-snapshot-schema.md`
- `docs/sprints/sprint-001.md`
- `docs/progress.md`
- `docs/agent-handoff.md`
- `docs/working-log.md`

Commands:

- `PYTHONPATH=python python3 -m valuescope.cli 000858 --years 8`
- `PYTHONPATH=python python3 -m pytest tests/python -q`
- `npm test -- --run`
- `npm run build`
- `npm run test:e2e`
- Playwright screenshot capture to:
  - `test-results/current-valuescope-sprint1-desktop.png`
  - `test-results/current-valuescope-sprint1-mobile.png`

Decisions:

- Sprint 001 is complete under the conservative annual-report provenance rule.
- Cash flow, capital safety, and shareholder returns are now explicit snapshot/UI sections instead of implied by raw tables.
- Shareholder-return windows must be filtered to the same confirmed annual coverage years as `annual_rows`; the current sample excludes unverified 2025 and ends at 2024.

Problems:

- The copied legacy render payload still lacks explicit provider-level annual-report type, so `confirmed_annual_by_conservative_cutoff` remains a conservative interim rule.

Next:

- Start Sprint 002 planning around provider-level annual provenance and a dedicated share-capital diagnostics table.

## 2026-05-06 16:40

Task:

- Completed Sprint 002 using GOAL-style closeout: snapshot v0.2, UI parity features, sample regeneration, tests, screenshots, and docs.

Files Changed:

- `python/valuescope/report_snapshot.py`
- `src/reportSnapshot.ts`
- `src/App.tsx`
- `src/styles.css`
- `src/App.test.tsx`
- `src/reportSnapshot.test.ts`
- `tests/e2e/report-workspace.spec.ts`
- `tests/python/test_report_snapshot.py`
- `public/samples/company_report_snapshot.json`
- `README.md`
- `docs/report-snapshot-schema.md`
- `docs/sprints/sprint-002.md`
- `docs/progress.md`
- `docs/agent-handoff.md`
- `docs/working-log.md`

Commands:

- `PYTHONPATH=python python3 -m valuescope.cli 000858 --years 10`
- `PYTHONPATH=python python3 -m pytest tests/python -q`
- `npm test -- --run`
- `npm run build`
- `npm run test:e2e`
- Playwright screenshot capture to:
  - `test-results/current-valuescope-sprint2-desktop.png`
  - `test-results/current-valuescope-sprint2-mobile.png`

Decisions:

- Snapshot schema is now v0.2.
- `market_context` is top-level and also rendered as a section; missing context uses an explicit placeholder.
- Bond-yield chart data is compressed to monthly points plus latest point so committed sample data stays inspectable.
- The UI uses local SVG line charts instead of adding Recharts/Chart.js because existing dependencies are enough for the required line charts.
- Valuation badge and explanation copy comes from snapshot item fields, with OE-DCF sensitivity preserved from the legacy metric implication.

Problems:

- Provider-level annual `REPORT_TYPE=年报` still is not exposed at the facade boundary; the conservative cutoff remains.
- Live generation still depends on external/cache-backed data providers and may be slow enough to deserve a background job/status UX.

Next:

- Plan Sprint 003 around provider-level annual provenance, share-capital diagnostics, or generation job UX.

## 2026-05-06 18:06

Task:

- Used the frontend design skill to continue Sprint 002 display architecture and UI polish in GOAL style.

Files Changed:

- `docs/sprints/sprint-002.md`
- `docs/progress.md`
- `docs/agent-handoff.md`
- `docs/working-log.md`
- `src/App.tsx`
- `src/styles.css`
- `src/App.test.tsx`

Commands:

- `npm run test`
- `npm run build`
- `npm run test:e2e`

Decisions:

- Treat the report surface as a dense research workstation: clear report identity, generated reading index, side context, bounded tables, and subdued visual hierarchy.
- Keep the new report index snapshot-driven so it does not imply unavailable sections.
- Preserve the visually split title while adding an `aria-label` for stable accessible heading semantics.

Problems:

- Unit tests initially failed because the new report index intentionally duplicates section labels; assertions were updated to accept multiple visible labels.

Next:

- Use visual QA against the reference HTML before deciding whether `巴芒总览` should become snapshot-native.
- Continue strict Sprint 002 closure with US-013 and US-014.

## 2026-05-06 18:10

Task:

- Responded to user feedback that the UI polish hurt UX and charts exceeded browser width.

Files Changed:

- `src/styles.css`
- `docs/progress.md`
- `docs/working-log.md`

Commands:

- Playwright viewport overflow probe for 1280px, 390px, and 375px.
- `npm run test`
- `npm run build`
- `npm run test:e2e`

Decisions:

- Treat page-level horizontal scrolling as a hard UI failure.
- Keep wide tables internally scrollable, but make charts responsive within their containers.
- Add `minmax(0, 1fr)` / `min-width: 0` constraints around report grids so internal content cannot expand the whole page.

Problems:

- The previous polish pass relied on test/build success and missed real viewport overflow. The desktop report body was widened by grid min-content behavior, and mobile charts were widened by a 520px SVG minimum.

Next:

- Use the captured responsive screenshots and overflow measurement before further visual changes.

## 2026-05-06 18:19

Task:

- Investigated and fixed user-reported data-quality issues around operating cash flow extraction and share-basis fallback labels.

Files Changed:

- `python/valuescope/legacy_stock_scripts/core/data_a.py`
- `python/valuescope/legacy_stock_scripts/core/valuation.py`
- `python/valuescope/legacy_stock_scripts/core/assessment.py`
- `tests/python/test_cashflow_extras.py`
- `tests/python/test_historical_share_basis.py`
- `public/samples/company_report_snapshot.json`
- `docs/report-snapshot-schema.md`
- `docs/progress.md`
- `docs/agent-handoff.md`
- `docs/working-log.md`

Commands:

- `PYTHONPATH=python python3 -m valuescope.cli 000858 --years 10`
- `PYTHONPATH=python python3 -m pytest tests/python -q`
- `npm run test`
- `npm run build`
- `npm run test:e2e`

Decisions:

- OCF is sourced from annual cash-flow statement fields, not synthesized from earnings.
- If net OCF is missing but annual operating inflow/outflow subtotals exist, derive OCF as inflow minus outflow and keep that behavior documented.
- Do not call early-year profit/EPS-derived implied shares `legacy_shares`; disclose them separately as lower-confidence implied share counts.
- Keep excluding 2025 until provider-level annual-report provenance can verify it as an annual report.

Problems:

- The old `fetch_cashflow_extras()` never emitted an `ocf` column, so `build_year_rows()` saw OCF as missing even though the source cash-flow statement had it.
- `build_valuation_history()` overwrote `reported_shares` fallback labels with `legacy_shares` because of an indentation bug.
- Existing raw cache lacked the new `ocf` column, so cache-hit generation needed migration logic.

Next:

- Continue US-013 by rendering the richer share-basis diagnostics directly in the React report.

## 2026-05-06 18:25

Task:

- Compared the running ValueScope React report with the stock-scripts 000858 HTML report.

Commands:

- Playwright DOM extraction and screenshot capture for:
  - `http://127.0.0.1:5173/#overview`
  - `file:///Users/dingyitian/Desktop/stock-scripts/reports/pricing_power/2025_五 粮 液_000858_pricing_power.html`

Artifacts:

- `test-results/html-compare-valuescope-desktop.png`
- `test-results/html-compare-reference-desktop.png`
- `test-results/html-compare-valuescope-mobile.png`
- `test-results/html-compare-reference-mobile.png`
- `test-results/html-compare-report.json`

Findings:

- ValueScope covers the main report spine but is still much less dense: 20 H2 sections / 8 tables versus reference 37 H2 sections / 32 tables.
- Remaining parity gaps include share-basis diagnostics, technical indicators, machine summary, detailed data-quality panel, valuation scenarios/resonance/formulas, and many radar-style quality/safety/shareholder modules.
- Reference mobile page itself has horizontal overflow, while ValueScope does not at 390px.

Next:

- Prioritize US-013 share-basis diagnostics and US-014 structured data-quality consistency before adding technical indicators.

## 2026-05-06 18:33

Task:

- Created Goal-Mode user story cards from the HTML parity comparison.

Files Changed:

- `docs/backlog.md`
- `docs/sprints/sprint-002.md`
- `docs/progress.md`
- `docs/agent-handoff.md`
- `docs/working-log.md`

Decisions:

- Track new parity gaps as backlog US-025 through US-031.
- Prioritize share-basis diagnostics and structured data quality before visual density modules.
- Add a parity QA gate story so future parity claims are measured by script and screenshots.
- Keep fixed ValueScope data semantics even when the old reference HTML contains stale OCF/share-basis warnings.

Next:

- Implement US-025, then US-026.

## 2026-05-06 18:52

Task:

- Implemented the Goal-Mode HTML parity story cards US-025 through US-031 after the user clarified that cards should be completed, not merely written.

Files Changed:

- `python/valuescope/report_snapshot.py`
- `src/App.tsx`
- `src/styles.css`
- `src/reportSnapshot.test.ts`
- `tests/python/test_report_snapshot.py`
- `scripts/html_parity_check.mjs`
- `package.json`
- `public/samples/company_report_snapshot.json`
- `docs/report-snapshot-schema.md`
- `docs/backlog.md`
- `docs/sprints/sprint-002.md`
- `docs/progress.md`
- `docs/agent-handoff.md`
- `docs/working-log.md`

Commands:

- `PYTHONPATH=python python3 -m valuescope.cli 000858 --years 10`
- `PYTHONPATH=python python3 -m pytest tests/python -q`
- `npm run test`
- `npm run build`
- `npm run test:e2e`
- `npm run test:parity`

Decisions:

- Upgrade the report snapshot schema to `0.3.0` for new parity sections.
- Keep corrected OCF and share-basis semantics even when the reference HTML still shows stale warnings.
- Treat Williams %R as price-position context only; do not frame it as a trading signal.
- Use a repeatable parity script as the acceptance gate for required sections and mobile overflow.

Results:

- Added first-class runtime sections for data quality, machine summary, share basis, Williams %R technicals, valuation scenarios, valuation formulas, and focused radar modules.
- Latest parity run reports ValueScope mobile overflow `false`; reference mobile overflow `true`; ValueScope table count `16` versus reference `32`.

Next:

- Sprint 003 should refine density and split radar modules further if needed, rather than treating these sections as missing.

## 2026-05-06 21:50

Task:

- Implemented the user's detailed report-UX critique as goal-mode story cards US-032 through US-045.

Files Changed:

- `docs/backlog.md`
- `docs/sprints/sprint-002.md`
- `docs/progress.md`
- `docs/agent-handoff.md`
- `docs/working-log.md`
- `python/valuescope/report_snapshot.py`
- `python/valuescope/legacy_stock_scripts/core/orchestrator.py`
- `src/App.tsx`
- `src/styles.css`
- `src/App.test.tsx`
- `tests/e2e/report-workspace.spec.ts`
- `public/samples/company_report_snapshot.json`

Commands:

- `PYTHONPATH=python python3 -m valuescope.cli 000858 --years 30`
- `PYTHONPATH=python python3 -m pytest tests/python -q`
- `npm run test`
- `npm run build`
- `npm run test:e2e`
- `npm run test:parity`
- Playwright screenshot/overflow checks for desktop and mobile:
  - `test-results/ux-corrections-desktop.png`
  - `test-results/ux-corrections-mobile.png`

Decisions:

- Treat the left rail as the permanent report control and navigation home.
- Keep macro interest-rate context in a separate appendix rather than blending it into the single-stock thesis flow.
- Show unavailable multi-country yield curves as missing until real series exist.
- Use colored metric cards and colored historical table cells as the default dense-report reading pattern.
- Expand shareholder-return windows to the longest confirmed annual window so Buffett's one-dollar test has enough history.

Problems:

- Multi-country 10-year yield sources are not yet implemented, so only China uses real sample data and other countries are visibly marked unavailable.
- The stock-scripts reference still has mobile overflow, so parity QA compares against it while keeping ValueScope's overflow gate stricter.

Next:

- If Sprint 003 continues macro context, add real country yield providers before adding more market-dashboard visuals.
- If Sprint 003 continues report density, split `radar_modules` into more explicit first-class UI sections.
