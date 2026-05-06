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
- Given historical annual data exists, the snapshot preserves every available annual-report year rather than truncating to the most recent five years.
- Given an annual row exists, it includes report type, source, and provenance fields.
- Given a provider row cannot prove annual-report provenance, it is excluded from annual history and surfaced through a warning if it affects the latest year.

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
- Given the latest fiscal year does not have a confirmed annual report row, the generator ignores quarterly, interim, or unverified `YYYY1231` rows and uses the latest confirmed annual report year instead.
- Given the provider lacks explicit report-type metadata, the generator applies a conservative cutoff and excludes the previous fiscal year unless annual provenance is explicit.
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
- Given an annual data table is shown, it displays all available annual-report rows from the snapshot, not just the latest five rows.
- Given a year is absent because no confirmed annual report exists, the UI does not infer or synthesize that year from quarterly data.
- Given the stock-scripts reference report for the same company, the React report matches its information hierarchy closely enough that the first screen shows company identity, report context, key metrics, warning states, and the start of the analytical sections.
- Given a desktop and mobile screenshot, report text, metric values, cards, tables, and navigation do not overlap, clip, or wrap one character per line.
- Given the committed sample snapshot, the rendered report demonstrates realistic section density rather than looking like a schema preview.
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
- Given source data includes quarterly periods, interim periods, or unverified `YYYY1231` rows, the generator excludes those rows from annual report history and keeps only confirmed annual-report periods.
- Given annual rows are generated, each row records `report_type`, `report_source`, and `report_provenance`.
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

## HTML Parity Gap Backlog

These cards were created from the 2026-05-06 Playwright comparison between:

- ValueScope: `http://127.0.0.1:5173/#overview`
- Reference HTML: `/Users/dingyitian/Desktop/stock-scripts/reports/pricing_power/2025_五 粮 液_000858_pricing_power.html`

Comparison artifacts:

- `test-results/html-compare-report.json`
- `test-results/html-compare-valuescope-desktop.png`
- `test-results/html-compare-reference-desktop.png`
- `test-results/html-compare-valuescope-mobile.png`
- `test-results/html-compare-reference-mobile.png`

Important note:

- Do not copy reference HTML bugs back into ValueScope. The reference page still has stale `经营现金流 0/20` and `legacy shares` warnings; ValueScope has intentionally fixed those data-quality issues.

Implementation update, 2026-05-06:

- US-025 through US-031 were implemented for Sprint 002 goal-mode closure.
- Runtime sections added: `data_quality`, `machine_summary`, `share_basis`, `technicals`, `valuation_scenarios`, `valuation_formulas`, and `radar_modules`.
- `npm run test:parity` now verifies required parity sections and mobile overflow against the reference HTML.
- Remaining future work is refinement depth, not absence of these parity surfaces: more granular submodules can be split from `radar_modules` in Sprint 003 if needed.

## Goal-Mode UX Correction Backlog

These cards were created from the 2026-05-06 live UI critique of `http://127.0.0.1:5173/#overview`.

## US-032: Move and Restyle Report Controls

As a report user,
I want ticker/year controls placed in a calm workspace panel,
so that the top navigation is not cluttered and the report header looks intentional.

Acceptance Criteria:

- Given the page loads, then ticker/year/generate controls are not squeezed into the top-right navbar.
- Given desktop width, controls appear near the report context where they belong.
- Given mobile width, controls wrap without horizontal overflow.
- Given generation is loading, the button state remains visually clear.

## US-033: Move Jump Directory into the Left Sidebar

As a report reader,
I want the section directory in the left sidebar,
so that the central page is reserved for analysis content.

Acceptance Criteria:

- Given the report renders, then the middle jump-button strip is removed.
- Given desktop width, the left rail includes clickable section links.
- Given mobile width, the directory remains usable without page-level overflow.
- Given Playwright clicks a sidebar link, then the target section becomes addressable by hash.

## US-034: Reprioritize Single-Stock Report Sections

As a value investor,
I want company-specific valuation scenarios and operating quality before appendices,
so that the report reads from business/valuation decisions to supporting diagnostics.

Acceptance Criteria:

- Given the report renders, then `valuation_scenarios` appears near valuation rather than near the end.
- Given `data_quality` and `machine_summary` render, then they appear at the bottom as audit/appendix material.
- Given macro yield context exists, it is not presented as the main single-stock valuation anchor.

## US-035: Add Global 10-Year Yield Curve Context

As a macro-aware investor,
I want country 10-year yield curves in a separate context section,
so that risk-free-rate context is visible without hijacking the single-stock report.

Acceptance Criteria:

- Given only China 10Y data is available, the section labels it explicitly and does not invent other countries.
- Given the curve renders, then axes, min/max/current labels, and visible line contrast make high/low readable.
- Given more countries become available later, the UI can show multiple country chips/series.

## US-036: Make Metric Sections Scan as Colored Cards

As a report reader,
I want every major metric to be boxed with numeric value and status color,
so that good/warning/bad/missing states are visible at a glance.

Acceptance Criteria:

- Applies to经营质量、提价权与运营效率、估值锚点、资本安全、股本口径、股东回报、数据质量等非-overview metric sections.
- Green/yellow/red/gray backgrounds map to ok/warning/error/missing/not-applicable states.
- Long metric explanations remain readable without overflowing.
- PE/EPS percentile cards visibly change color according to percentile thresholds.

## US-037: Make Buffett Overview Focus on Business Purity and OE

As a Buffett/Munger-style reader,
I want the overview to emphasize business purity and owner earnings,
so that the first summary focuses on the right economic signal rather than gross margin alone.

Acceptance Criteria:

- Given quality metrics include业务纯度, the Buffett overview shows业务纯度 as a first-class card.
- Given valuation metrics include `OE收益率 vs 国债`, the UI discloses the OE per share or OE amount used.
- Given 毛利率 is present, it remains supporting context, not the main overview emphasis.

## US-038: Replace Ambiguous Historical Trend Block

As a report reader,
I want historical trend visuals to explain what they measure,
so that a tiny unlabeled line does not create confusion.

Acceptance Criteria:

- The old unclear left revenue mini-chart is removed or replaced by labeled multi-metric trend cards.
- Any chart shown has explicit title, axis labels, and readable value labels.

## US-039: Fix PE/EPS Chart Readability

As a valuation reader,
I want PE/EPS charts to show axes and reference values clearly,
so that current and median lines are not clipped or unreadable.

Acceptance Criteria:

- Charts include x-axis and y-axis labels.
- Current and median labels stay inside the chart viewport.
- PE and EPS percentile panels visibly reflect warning/hot states.
- Mobile viewport does not create page-level overflow.

## US-040: Color Historical Tables by Trend and Quality

As a report reader,
I want historical rows and cells colored by business meaning,
so that improving EPS/OE/OCF and deteriorating years stand out immediately.

Acceptance Criteria:

- EPS and OE per share decreases versus prior year are red; increases are green.
- OCF/股 and OE/股 in share-basis history use green/red trend coloring.
- Annual financial quality rows apply status color to key quality metrics.
- Tables show the full available annual history by default, with internal scrolling only when needed.

## US-041: Clarify Cash Flow Meaning and Remove Source Noise

As a business-quality reader,
I want cash-flow metrics explained in business terms,
so that OCF, net income, capex, and capex/net income tell me what they imply.

Acceptance Criteria:

- Cash-flow cards explain what each metric means to the business.
- `资本开支/净利` is colored by good/medium/bad thresholds.
- The cash-flow table no longer displays `report_provenance`.

## US-042: Improve Number Units Across the Report

As a reader,
I want large numbers converted into readable units,
so that values like `3881608005.00` are not shown raw.

Acceptance Criteria:

- Share counts display as 亿股 where appropriate.
- Money values display as 亿 or 万亿 where appropriate.
- Repeated large-number formatting works in cards, details, and tables.

## US-043: Add Capital Safety History and Missing Safety Signals

As a financial-safety reader,
I want capital safety to include historical ROIC and interest coverage,
so that I can see leverage and capital efficiency rather than a static point-in-time card.

Acceptance Criteria:

- Capital safety shows historical rows where available.
- ROIC and interest coverage appear when the generator can compute them.
- Missing values are shown as missing, not zero.
- Large share/mcap values use readable units.

## US-044: Expand Shareholder Returns and Buffett One-Dollar Test

As a Buffett-style reader,
I want shareholder returns to explain one-dollar retained earnings,
so that I can judge whether retained earnings created more than one dollar of market value.

Acceptance Criteria:

- Shareholder return rows use the longest confirmed annual window available.
- The section includes one-dollar theory copy and ratio interpretation.
- Good/bad retained-return states are color coded.

## US-045: Verify UI Corrections with Browser QA

As a developer,
I want browser checks for the corrected report UX,
so that layout regressions and sidebar navigation issues are caught.

Acceptance Criteria:

- Playwright verifies no mobile page-level overflow.
- Playwright verifies sidebar navigation link behavior.
- Playwright captures screenshots after the correction pass.

## US-025: Render Share-Basis Diagnostics as a First-Class Report Section

As a value investor,
I want share-count basis, fallback source, and dilution risk shown in a dedicated section,
so that per-share valuation history is not trusted blindly.

Goal:

- Close the reference gap for “股本口径来源与置信度”, “股本质量雷达”, and future unlock-pressure tables while preserving ValueScope's corrected share-basis semantics.

Acceptance Criteria:

- Given a snapshot has `diagnostics.share_capital`, when the report renders, then it shows a dedicated section titled `股本口径来源与置信度` or `股本诊断`.
- Given yearly rows include `valuation_shares`, `asof_shares`, `reported_shares`, or `reported_shares_source`, when the section renders, then each source is labeled distinctly.
- Given `reported_shares_source = "profit_over_eps_derived"`, when the section renders, then the UI labels it as implied share count, not `legacy_shares`.
- Given future unlock data is missing, when the section renders, then it shows a stable “暂无可用解禁压力” state rather than hiding the area.
- Given share-basis confidence is low or mixed, when the section renders, then the section tone is warning/fail and explains why.
- Given the committed `000858` sample loads, then no text says early 1998-2008 rows are `legacy shares`.

Notes:

- Reference modules: `股本口径来源与置信度`, `股本质量雷达`, unlock-pressure table.
- Related existing backlog: US-020.
- Implementation source: `diagnostics.share_capital`, `analyze_share_basis_coverage`, valuation-history `share_basis_used`.

## US-026: Render Structured Data Quality and Confidence Panel

As a value investor,
I want report confidence explained with coverage bars and model-availability status,
so that I can distinguish reliable facts from incomplete analysis.

Goal:

- Close the reference gap for `数据质量与置信度` without reintroducing stale OCF or share-basis warnings.

Acceptance Criteria:

- Given `data_quality` exists, when the report renders, then it shows annual coverage, realtime data status, field completeness, industry adaptation, valuation model availability, and warning summary.
- Given field completeness includes OCF, when the committed `000858` sample renders, then OCF coverage reflects the fixed `27/30` annual rows rather than `0/20`.
- Given a warning is tied to a section, when the report renders, then it appears near the affected section and in the report-level data-quality panel.
- Given a field is missing, when the panel renders, then the missing state is visible and stable enough for tests.
- Given mobile viewport width is 390px, when the panel renders, then coverage bars and model chips do not create page-level horizontal overflow.

Notes:

- Reference module: `数据质量与置信度`.
- Related existing backlog: US-021.
- Implementation source: `build_data_quality_report`, snapshot `warnings`, section `warnings`.

## US-027: Reproduce Williams %R Technical Indicator Module

As a value investor,
I want optional Williams %R technical context in the report,
so that the new UI keeps the reference report's short-term price-position module without treating it as buy/sell advice.

Goal:

- Close the reference gap for `技术指标`, including Williams %R periods and crossing records.

Acceptance Criteria:

- Given price history exists, when the generator runs, then the snapshot includes Williams %R values for 14/28/60 day windows, a chart series, and crossing records.
- Given technical data is present, when the UI renders, then it shows the three Williams %R period values, trend chart, and overbought/oversold crossing table.
- Given technical data is unavailable or as-of mode makes it inappropriate, when the UI renders, then it shows a section-specific missing/not-applicable state.
- Given the section renders, then it includes copy stating that Williams %R does not replace fundamental valuation and is not a trading signal.
- Given mobile viewport width is 390px, then the chart and crossing table remain within the page width.

Notes:

- Reference module: `技术指标`.
- Related existing backlog: US-023.
- Implementation source: `core/technicals.py:build_williams_r`.

## US-028: Reproduce Valuation Scenarios, Resonance, and Formula Appendix

As a value investor,
I want valuation scenarios, low-valuation resonance, and formulas visible,
so that the report explains not just the output number but the model structure and sensitivity.

Goal:

- Close the reference gaps for `三档情景分析`, `低估共振结论`, and `估值公式`.

Acceptance Criteria:

- Given valuation details include scenario data, when the report renders, then it shows conservative/base/optimistic scenario rows with assumptions and result values.
- Given multiple valuation models are available, when the report renders, then it shows a low-valuation resonance section explaining which models agree or disagree.
- Given formulas are available, when the report renders, then it shows an appendix for OE-DCF, Munger forward valuation, CAGR/PEG/PEGY, SGR cross-check, and opportunity cost.
- Given an input is missing or not applicable, when the section renders, then the affected formula/scenario is marked missing/not-applicable rather than silently omitted.
- Given mobile viewport width is 390px, then scenario tables use internal scroll without page-level horizontal overflow.

Notes:

- Reference modules: `三档情景分析`, `低估共振结论`, `估值公式`.
- Related existing backlog: US-014 and US-015.

## US-029: Restore Detailed Operating, Safety, and Shareholder Radar Modules

As a value investor,
I want the report's quality and capital-return checks split into focused modules,
so that I can scan why a company passes or fails instead of reading one compressed list.

Goal:

- Close the reference gap where ValueScope compresses many stock-scripts modules into broad sections.

Acceptance Criteria:

- Given annual rows and quality cards exist, when the report renders, then it shows separate modules for profitability, cash cycle, capital allocation, EPS quality, capital safety, net cash, goodwill, tax evidence, pledge, dividend health, shareholder return, and capital configuration where data exists.
- Given a module has fewer than the required data points, when it renders, then it labels insufficient history.
- Given a module is market-specific and not applicable, when it renders, then it labels `not_applicable` with reason.
- Given module rows are table-like, when mobile viewport width is 390px, then tables remain internally scrollable without page-level overflow.
- Given warnings exist for a module, when it renders, then warnings are shown near that module.

Notes:

- Reference modules include `盈利能力：产品的溢价护城河`, `产业链地位：现金效能`, `资本配置：扩张扩展性`, `EPS 透视`, `资本质量与财务安全`, `净现比雷达`, `商誉占比雷达`, `税务测谎雷达`, `股权质押雷达`, `分红健康度`, `股东回报雷达`, and `资本配置画像`.
- Related existing backlog: US-016, US-017, US-018, US-019.

## US-030: Add Machine Summary for AI Parsing

As a research workflow user,
I want a machine-readable report summary exposed in the UI and snapshot,
so that AI or downstream tools can consume the report without scraping visual tables.

Goal:

- Close the reference gap for `机器摘要（AI解析）` while keeping the snapshot contract explicit.

Acceptance Criteria:

- Given a generated report snapshot, when a machine summary is available, then it includes normalized keys for company identity, data confidence, major verdicts, key warnings, valuation outputs, and missing/not-applicable states.
- Given the UI renders the report, then it includes a `机器摘要（AI解析）` section that is readable by humans and stable for tests.
- Given a value comes from AI or heuristic synthesis, when it appears in the summary, then the source/basis is disclosed and does not sound like final buy/sell advice.
- Given the machine summary is missing, when the UI renders, then it shows a section-specific placeholder rather than failing.

Notes:

- Reference module: `机器摘要（AI解析）`.
- This should be generated from snapshot facts, not by asking an LLM at render time.

## US-031: Add HTML Parity QA Gate

As a developer,
I want a repeatable parity audit against the reference HTML,
so that future UI work cannot claim parity while silently dropping sections or breaking mobile layout.

Goal:

- Turn the one-off Playwright comparison into a repeatable quality gate.

Acceptance Criteria:

- Given the ValueScope dev server and a reference HTML path, when the parity script runs, then it outputs JSON with section counts, table counts, chart counts, heading lists, keyword coverage, and mobile overflow measurements.
- Given a reference feature is intentionally not implemented, when the script reports it missing, then the gap is mapped to a backlog story ID.
- Given reference HTML contains a known bug fixed in ValueScope, when the report is generated, then it marks the difference as intentional rather than a parity failure.
- Given mobile viewport width is 390px, then the script records `body.scrollWidth` for both pages and flags ValueScope if it exceeds viewport width.
- Given screenshots are captured, then they are written under `test-results/` and referenced from the progress log.

Notes:

- Initial manual comparison artifacts are in `test-results/html-compare-report.json`.
- This is a QA/developer-experience card, not a product-facing module.

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
