# Product Backlog

## Card Format

```md
## US-000: Story Title

As a [user],
I want [capability],
so that [outcome].

Acceptance Criteria:
- Given [state], when [action], then [observable result].

Notes:
- Implementation or product notes.
```

## Sprint 1 Candidates

## US-001: Initialize ValueScope App

As a value investor,
I want a runnable local app shell,
so that future report and screening work has a stable place to land.

Acceptance Criteria:

- Given a fresh checkout, the README shows the setup and run commands.
- Given the app starts, the first screen is the report workspace, not a marketing page.
- Given no snapshot is loaded, the app shows an empty import state.

Notes:

- App stack decision: Vite, React, TypeScript, Zod, Vitest, and Playwright.
- Keep the UI local-first and offline-friendly.

## US-002: Define Company Report Snapshot Schema v0

As a developer,
I want a documented `company_report_snapshot.json` schema,
so that report generation and React rendering can evolve without guessing.

Acceptance Criteria:

- Given the schema doc, an agent can create a valid sample company report snapshot.
- Given a snapshot, it includes metadata, company identity, coverage years, report sections, metrics, and warnings.
- Given missing values, they are represented explicitly and safely.

Notes:

- See `docs/report-snapshot-schema.md`.
- Design the contract for ValueScope's own Python-generated report output.

## US-003: Generate Company Report Snapshot

As a value investor,
I want ValueScope to generate a single-stock financial report snapshot,
so that the old stock-scripts HTML report capability is reproduced inside the new product.

Acceptance Criteria:

- Given the generator runs for a supported sample company, it writes `company_report_snapshot.json`.
- Given the output, it includes metadata, company identity, report sections, metrics, and warnings.
- Given missing values, it records `null` plus missing metric names rather than zero.
- Given source or computation failures, it keeps the snapshot inspectable and reports warnings.

Notes:

- Implement this as ValueScope-owned Python code.
- Use `stock-scripts` as a reference for report capability and metric language only.
- Keep the first generated report small enough to inspect in git.

## US-004: Load Local Report Snapshot

As a value investor,
I want to load a local `company_report_snapshot.json`,
so that I can inspect a financial report without a database or network.

Acceptance Criteria:

- Given a valid snapshot, the app shows generated time, company identity, market, schema version, and coverage years.
- Given an invalid snapshot, the app shows a clear error.
- Given no snapshot, the app shows an empty import state.

Notes:

- MVP can start with a committed generated report snapshot before file import is polished.

## US-005: Render Financial Report

As a value investor,
I want to read the generated financial report in React,
so that the old static HTML report workflow becomes an interactive local workstation.

Acceptance Criteria:

- Given a loaded report snapshot, the app renders core report sections.
- Given a metric has a unit or direction, the UI displays it explicitly.
- Given a metric is missing or not applicable, the UI labels that state rather than hiding it.
- Given a warning exists, the UI shows it near the affected section.

Notes:

- First report sections: valuation, quality, cash flow, capital safety, shareholder return, and metric explanations.

## Report Reproduction Backlog

## US-012: Build Annual Report Rows

As a developer,
I want ValueScope to build normalized annual financial rows,
so that React report sections can reuse one stable yearly data contract.

Acceptance Criteria:

- Given normalized sample financial inputs, the generator creates yearly rows with revenue, gross margin, expense ratios, cash cycle, OCF, Capex, net income, ROE, ROIC, and per-share fields where available.
- Given a value is unavailable, the row stores `null` and a status instead of `0`.
- Given fewer than the requested years are available, the snapshot records the actual coverage and a warning.

Notes:

- Reference: `stock-scripts/core/orchestrator.py:build_year_rows`.
- This is the core bridge from raw financial data to report sections.

## US-013: Encode Metric Definitions and Rating Rules

As a value investor,
I want each metric to disclose formula, direction, unit, threshold, and meaning,
so that report conclusions are auditable.

Acceptance Criteria:

- Given a rendered metric card, it shows the metric value, unit, status, direction, formula, and plain-language meaning.
- Given a threshold-based rating, the snapshot includes the rule used to assign the tone.
- Given the metric is not applicable, the card explains why it is not applicable.

Notes:

- Reference: `INDICATOR_GUIDE.md`, `core/assessment.py`, and `core/config.py` dataclasses.
- Keep metric semantics shared between reports and future screening.

## US-014: Reproduce Valuation Overview

As a value investor,
I want the report to show the main valuation lenses,
so that I can compare price against several transparent anchors.

Acceptance Criteria:

- Given a report snapshot, it includes valuation cards for OE-DCF, Munger PE anchors, PEG or PEGY, earnings yield versus bonds, and market PE context where data exists.
- Given a valuation model cannot run, the section marks it as missing or not applicable with a reason.
- Given valuation details exist, the UI renders a valuation overview and annual anchor table.

Notes:

- Reference: `core/valuation.py:build_valuation_assessments`, `build_valuation_history`, and `core/render.py`.

## US-015: Reproduce Owner Earnings Analysis

As a value investor,
I want conservative, base, and lenient owner earnings views,
so that I can understand how maintenance Capex and normalization affect valuation.

Acceptance Criteria:

- Given annual data, the generator computes or records owner earnings in three calibers.
- Given OE yield history is available, the snapshot includes yearly OE yield rows.
- Given OE cannot be computed, the snapshot records which source field or formula input is missing.

Notes:

- Reference: `core/valuation.py:_owner_earnings_three_caliber` and `docs/OWNER_EARNINGS_EXPLAINED.md`.

## US-016: Reproduce Pricing Power and Operating Quality

As a value investor,
I want the report to show pricing power and operating efficiency,
so that I can judge whether growth is backed by durable business quality.

Acceptance Criteria:

- Given annual rows, the report shows gross margin, gross margin trend, business purity, DSO, DPO, CCC, ROIIC, and Capex / net income where available.
- Given trend windows are too short, the affected metric is labeled as insufficient history.
- Given the UI renders these sections, warnings appear near the affected table or card.

Notes:

- Reference: `core/assessment.py:build_summary_metrics`, `build_ses_metrics`, and related `assess_*` functions.

## US-017: Reproduce Financial Safety Section

As a value investor,
I want a financial safety section,
so that leverage, capital quality, and solvency risks are visible.

Acceptance Criteria:

- Given annual rows, the report shows ROA, ROE, ROIC, ROE-ROIC, interest coverage, net cash, interest-bearing debt, goodwill ratio, and tax evidence where available.
- Given a company has no meaningful interest expense, interest coverage is marked with the correct basis instead of being forced to zero.
- Given a safety metric is missing, the UI does not hide the row.

Notes:

- Reference: `core/assessment.py:build_quality_cards` and `build_quality_module_notes`.

## US-018: Reproduce Cash Flow and EPS Quality

As a value investor,
I want cash flow and EPS quality checks,
so that paper earnings are distinguished from cash-backed earnings.

Acceptance Criteria:

- Given annual rows, the report shows OCF, net income, OCF / net income, real EPS, basic EPS, diluted EPS, and OCF per share where available.
- Given real EPS uses a fallback source, the snapshot records the source basis.
- Given cash flow quality is weak or missing, the report shows a visible status.

Notes:

- Reference: `core/utils.py:get_real_eps`, `core/assessment.py`, and `core/data_a.py` cashflow extras.

## US-019: Reproduce Shareholder Return Section

As a value investor,
I want dividends, buybacks, dilution, and shareholder yield visible together,
so that capital return is not reduced to dividend yield alone.

Acceptance Criteria:

- Given annual rows, the report shows cash dividends, payout ratio, net buyback cash, equity financing, dividend yield, net buyback yield, and total shareholder yield where available.
- Given buybacks are offset by equity financing, the report labels the net effect.
- Given no data exists for a market-specific field, the status is `not_applicable` or `missing` with reason.

Notes:

- Reference: `core/assessment.py:_build_shareholder_note` and shareholder return rows in `core/render.py`.

## US-020: Reproduce Share Capital Diagnostics

As a value investor,
I want share count basis and dilution risk to be explicit,
so that historical per-share valuation is not misleading.

Acceptance Criteria:

- Given annual data, the snapshot records total shares, float shares, valuation shares, reported shares, as-of shares, and share-basis fallback where available.
- Given historical share basis falls back to a secondary source, the report lowers confidence and labels the affected years.
- Given share basis behavior changes, regression tests cover current-basis and as-of-basis logic.

Notes:

- Reference: `core/assessment.py:build_share_capital_analysis`, `analyze_share_basis_coverage`, and `tests/test_historical_share_basis.py`.
- This is a high-risk contract.

## US-021: Reproduce Data Quality and Warning Model

As a value investor,
I want the report to explain data confidence and warning states,
so that I can distinguish reliable facts from incomplete analysis.

Acceptance Criteria:

- Given a generated snapshot, it includes report-level confidence, section warnings, missing metric names, and model availability.
- Given a provider or formula fails, the snapshot records the failure without replacing it with a plausible-looking value.
- Given warnings exist, the UI renders them near the affected section and in a report-level summary.

Notes:

- Reference: `core/assessment.py:build_data_quality_report`.

## US-022: Reproduce Bank Report Branch

As a value investor,
I want banks to use bank-specific metrics and valuation,
so that banks are not judged by industrial-company formulas.

Acceptance Criteria:

- Given a bank sample, the generator uses bank-specific sections instead of SES / industrial pricing-power sections.
- Given bank data exists, the report shows NIM, cost-income ratio, provision-to-loan, loan-deposit ratio, leverage, ROA, ROE, credit quality, franchise quality, and stress test where available.
- Given bank valuation runs, it uses bank-appropriate PB / Gordon-style context rather than OE-DCF as the primary lens.

Notes:

- Reference: `docs/BANK_WORKFLOW.md`, `core/assessment.py:build_bank_summary_metrics`, and `core/valuation.py` bank helpers.
- This can follow the first industrial-company parity slice.

## US-023: Reproduce Technical and Market Context Modules

As a value investor,
I want optional technical and market context,
so that the report keeps the Williams %R and broad valuation backdrop from stock-scripts.

Acceptance Criteria:

- Given price history exists, the snapshot includes Williams %R metrics and crossings.
- Given market data exists, the snapshot includes market PE, risk-free yield, and equity risk premium context.
- Given the report is generated in as-of mode, unavailable forward-looking modules are marked accordingly.

Notes:

- Reference: `core/technicals.py`.
- This is optional after core financial report parity.

## US-024: Reproduce As-Of Backtest Report Mode

As a value investor,
I want to generate reports as of a historical year,
so that I can review what the analysis would have known at that time.

Acceptance Criteria:

- Given an `asof_year`, the generator excludes future annual data.
- Given historical price is available, the valuation uses the as-of price unless explicitly overridden.
- Given as-of share basis is used, the report labels the mode and does not silently apply future share changes to the past.

Notes:

- Reference: `core/backtest.py`, `core/data_a.py:_filter_data_as_of_year`, and share-basis tests.

## US-006: Define Screen Snapshot Schema v0

As a developer,
I want a documented `screen_snapshot.json` schema,
so that later universe screening can reuse report-grade metrics without guessing.

Acceptance Criteria:

- Given the schema doc, an agent can create a valid sample screen snapshot.
- Given a snapshot, it includes metadata, metric definitions, and rows.
- Given missing values, they are represented explicitly and safely.

Notes:

- This is not the first Sprint 001 implementation target.
- See `docs/snapshot-schema.md`.

## Later Backlog

## US-007: Reproduce Full Report Capability

As a value investor,
I want ValueScope's report generator to cover the broader stock-scripts-style report workflow,
so that the new app can replace the old scripts over time.

Acceptance Criteria:

- Given a supported A-share ticker, the generator creates a full `company_report_snapshot.json`.
- Given stale cached data, the generator marks freshness in metadata.
- Given failed source processing, the generator records the error without pretending the report is complete.

Notes:

- Implement this in ValueScope's Python pipeline, not by importing stock-scripts internals.
- Keep the generator behind the `company_report_snapshot.json` contract so the UI does not depend on pipeline internals.

## US-008: Apply Basic Factor Filters

As a value investor,
I want to combine financial factor conditions,
so that I can find candidate stocks without editing scripts.

Acceptance Criteria:

- Given a loaded screen snapshot, the user can add at least 5 filter conditions.
- Given multiple conditions, the app applies them with AND logic.
- Given a condition changes, results update without a server round trip.

Notes:

- First filter families: valuation, quality, cash flow, leverage, size/liquidity.

## US-009: Explain Pass and Fail Reasons

As a value investor,
I want to see why a stock passed or failed,
so that I do not trust a black-box screener.

Acceptance Criteria:

- Given a passing row, the app shows which conditions it passed.
- Given a failing row, the app can show the first failed condition.
- Given missing data, the app labels the result as missing rather than failed.

Notes:

- Explanation is a product feature, not debug output.

## US-010: Save Strategy Recipes

As a value investor,
I want to save a named filter recipe,
so that I can rerun my investing method consistently.

Acceptance Criteria:

- Given a filter set, the user can save it with a name.
- Given a saved recipe, the user can rerun it on a new snapshot.
- Given changed metric definitions, the app warns about schema mismatch.

## US-011: Export AI Research Packet

As a value investor,
I want to export a candidate's financial facts as Markdown or JSON,
so that AI can research the company's business fundamentals with clean context.

Acceptance Criteria:

- Given a selected stock, the app exports key financial evidence.
- Given missing data, the packet includes uncertainty notes.
- Given exported content, it avoids pretending to be final investment advice.
