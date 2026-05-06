# Company Report Snapshot Schema

## File

`company_report_snapshot.json`

## Version

`schema_version: "0.3.0"`

## Purpose

The company report snapshot is the first local data contract between ValueScope's Python report generator and the React report UI. It replaces the old static HTML report output with inspectable JSON that can be rendered locally without a database or network.

## Top-Level Shape

```json
{
  "schema_version": "0.3.0",
  "generated_at": "2026-05-05T00:00:00Z",
  "source": {
    "name": "valuescope-python-report",
    "provider": "legacy_stock_scripts",
    "mode": "current",
    "html_debug_path": "reports/pricing_power/2025_sample.html",
    "notes": "stock-scripts used as metric language reference only"
  },
  "company": {
    "ticker": "000858",
    "name": "五粮液",
    "market": "CN-A",
    "currency": "CNY",
    "accounting_unit": "CNY"
  },
  "current_price": 92.26,
  "market_context": {
    "bond_label": "中国十年期国债收益率",
    "bond_latest": 1.74,
    "bond_latest_date": "2026-05-06",
    "bond_percentile": 3.2,
    "csi300_pe_ttm": 13.5,
    "csi300_earnings_yield": 7.41,
    "market_equity_risk_premium": 5.67,
    "stock_equity_risk_premium": 4.2,
    "stock_erp_status": "sufficient",
    "bond_yield_series": [{"date": "2026-05-06", "yield_pct": 1.74}]
  },
  "pe_percentile": {},
  "eps_percentile": {},
  "coverage": {
    "period_type": "annual",
    "years": ["2021", "2022", "2023", "2024"]
  },
  "metric_definitions": {},
  "sections": [],
  "warnings": []
}
```

## Required Metadata

- `schema_version`: semantic version for compatibility checks.
- `generated_at`: ISO 8601 timestamp.
- `source.name`: ValueScope generator name.
- `source.provider`: generator/provider lineage, initially `legacy_stock_scripts` or `sample`.
- `source.mode`: `current`, `as_of`, or `sample`.
- `source.html_debug_path`: optional old HTML output path when the copied engine is used for parity/debugging.
- `company.ticker`: market-local ticker.
- `company.name`: company display name.
- `company.market`: market identifier, initially `CN-A`.
- `company.currency`: market currency for price and valuation fields.
- `company.accounting_unit`: accounting currency/unit used by financial statements.
- `current_price`: current or as-of share price in `company.currency`; may be `null`.
- `market_context`: optional market environment node used by the report UI. Missing data must be represented as `null` or an omitted node, not synthesized.
- `pe_percentile`: optional PE historical percentile node.
- `eps_percentile`: optional EPS/E historical percentile node.
- `coverage.period_type`: report period basis, initially `annual`.
- `coverage.years`: all available annual-report years included in the snapshot. Quarterly periods must not appear here.
- `metric_definitions`: dictionary describing metric semantics.
- `sections`: ordered report sections for React rendering.
- `warnings`: snapshot-level warnings.

## Section Shape

```json
{
  "id": "valuation",
  "title": "Valuation",
  "summary": "Valuation should be cross-checked across multiple anchors.",
  "items": [
    {
      "metric": "pe",
      "label": "PE",
      "value": 18.2,
      "status": "ok",
      "badge": "满足安全边际",
      "badge_color": "green",
      "what_it_measures": "用所有者盈余折现来估算企业长期可提取现金流的现值。",
      "basis": "Price divided by annualized earnings per share.",
      "meaning": "用价格与盈利比较当前估值。",
      "implication": "背后含义和敏感性说明。",
      "warning": null
    }
  ]
}
```

Optional item fields added in v0.2:

- `badge`: short UI status text, such as `满足安全边际`, `25x场景显著高于现价`, or `不适用`.
- `badge_color`: `green`, `yellow`, `red`, or `null`.
- `what_it_measures`: one-sentence plain-language explanation.
- `meaning` and `implication`: source metric language and analytical context. These are report explanations, not investment instructions.

Section nodes added in v0.3:

- `data_quality`: field coverage, model availability, warning summary, and share-basis confidence.
- `machine_summary`: stable machine-readable facts for downstream parsing. This is research support, not buy/sell guidance.
- `share_basis`: first-class share-count source diagnostics, including EPS-derived implied share years and true legacy fallback years.
- `valuation_scenarios`: owner-earnings/growth/exit-PE scenario rows plus low-valuation resonance and DCF sensitivity details.
- `valuation_formulas`: model formulas, direction, meaning, caveats, and not-applicable states.
- `radar_modules`: focused operating, valuation, share-capital, and shareholder-return signals split out for scanning.
- `technicals`: optional Williams %R 14/28/60-day context, latest values, and chart rows. Technicals must be framed as price-position context, not a trading signal.

## Market Context Shape

`market_context` may be `null`. When present, it should include:

- `bond_label`: source label for the risk-free yield series.
- `bond_latest`: latest 10-year government bond yield in percentage points.
- `bond_latest_date`: provider date for `bond_latest`.
- `bond_percentile`: historical percentile for the yield series.
- `bond_min`, `bond_max`, `bond_mean`: historical summary statistics.
- `csi300_pe_ttm`: CSI 300 PE (TTM), when available.
- `csi300_earnings_yield`: `1 / csi300_pe_ttm * 100`, when available.
- `market_equity_risk_premium`: market earnings yield minus bond yield.
- `stock_equity_risk_premium`: current stock earnings yield minus bond yield, when current PE is available.
- `stock_erp_status`: `sufficient`, `thin`, `negative`, or `null`.
- `summary`: provider/generator market environment summary.
- `bond_yield_series`: inspectable chart series. The committed sample stores month-end points plus the latest point to keep JSON small.

## Percentile Shape

`pe_percentile` and `eps_percentile` may be `null`. When present, they use this normalized shape:

```json
{
  "kind": "pe",
  "current": 12.4,
  "percentile": 42.0,
  "hist_min": 8.1,
  "hist_median": 15.2,
  "hist_max": 38.5,
  "hist_mean": 17.4,
  "current_vs_median_pct": -18.4,
  "sample_count": 10,
  "method": "post_may_anchor",
  "note": "历史样本说明。",
  "series": [
    {
      "year": "2024",
      "price": 92.26,
      "eps": 2.27,
      "pe": 40.58,
      "anchor_date": "2025-05-06"
    }
  ]
}
```

For EPS nodes, `series` rows use `eps`, `real_eps`, `basic_eps`, and `basis`.

## Annual Row Shape

Rows in annual history tables must include provenance fields:

```json
{
  "year": "2024",
  "date_key": "20241231",
  "report_type": "annual",
  "report_source": "akshare:sina:利润表",
  "report_provenance": "confirmed_annual",
  "revenue": 89175178322.7
}
```

Required provenance fields:

- `report_type`: normalized report type. For annual history this must be `annual`.
- `report_source`: provider or adapter path used to build the row.
- `report_provenance`: one of:
  - `confirmed_annual`: provider explicitly marks the row as an annual report.
  - `confirmed_annual_by_conservative_cutoff`: provider lacks report-type metadata, but the fiscal year is older than the conservative latest-year cutoff and the row has an annual `YYYY1231` period.
  - `unverified`: provider lacks enough evidence to treat the row as annual history.

Annual report history may include `confirmed_annual` and `confirmed_annual_by_conservative_cutoff` rows. `unverified` rows must be excluded from annual history and surfaced as warnings if they affect the latest available year.

Derived sections that depend on yearly history, including cash flow and shareholder returns, must use the same confirmed annual coverage set. They must not keep a later unverified year in a summary window after that year has been excluded from `annual_rows`.

Cash-flow rows use reported cash-flow statement values where available. `ocf` means operating cash flow from the annual cash-flow statement, preferably `经营活动产生的现金流量净额`; if that exact net field is absent but annual operating cash inflow and outflow subtotals are present, `ocf` may be derived as inflow minus outflow. It must not be replaced by net income or another earnings proxy.

Share-basis diagnostics distinguish verified period-end share counts from derived fallbacks. `valuation_shares` / `asof_shares` from share-change history are preferred. If early years lack verified share-change rows, `reported_shares_source = "profit_over_eps_derived"` means the denominator is inferred from parent net profit divided by EPS and must be disclosed as lower-confidence implied share count, not mislabeled as `legacy_shares`.

## Required MVP Sections

- `overview`
- `data_quality`
- `machine_summary`
- `market_context`
- `valuation`
- `valuation_scenarios`
- `valuation_formulas`
- `pe_percentile`
- `eps_percentile`
- `quality`
- `radar_modules`
- `cash_flow`
- `capital_safety`
- `share_basis`
- `shareholder_returns`
- `technicals`
- `metric_explanations`

## Metric Definition Shape

```json
{
  "pe": {
    "label": "PE",
    "unit": "multiple",
    "value_type": "number",
    "direction": "lower_is_better",
    "description": "Price divided by earnings per share.",
    "source_reference": "stock-scripts metric language"
  }
}
```

## Value Status Rules

- `ok`: metric value is present and meaningful.
- `missing`: source data is unavailable.
- `not_applicable`: metric does not apply to this company or section.
- `warning`: value exists but has caveats.
- `error`: generator could not compute the value safely.

## Missing Data Rules

- Use `null` for known missing values.
- Do not use `0` to mean missing.
- Every missing, warning, not-applicable, or error item must include human-readable context.
- The UI must display the state near the affected metric or section.

## Annual Report History Rules

- Annual report tables must preserve all available annual-report years.
- UI rendering must not truncate annual history to the most recent five years.
- Quarterly or interim rows must not be used as annual report rows, even if the provider labels the date as `YYYY1231`.
- If the latest fiscal year annual report cannot be confirmed, the snapshot must stop at the latest confirmed annual report year.
- `coverage.years` must be derived only from confirmed annual report rows.
- If a provider row has a `YYYY1231` key but no report-type provenance, it must not enter annual history unless it passes the conservative cutoff rule.
- Until a provider exposes explicit report type, the conservative cutoff is `current calendar year - 2`; for example, during 2026 an unverified 2025 row is excluded and 2024 remains the latest annual year.

## Compatibility Rules

- Patch versions may add optional fields.
- Minor versions may add sections, metrics, or metadata.
- Major versions may change section or metric semantics.
- The UI must reject unsupported major versions with a clear error.
