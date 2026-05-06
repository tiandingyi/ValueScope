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
