# Company Report Snapshot Schema

## File

`company_report_snapshot.json`

## Version

`schema_version: "0.1.0"`

## Purpose

The company report snapshot is the first local data contract between ValueScope's Python report generator and the React report UI. It replaces the old static HTML report output with inspectable JSON that can be rendered locally without a database or network.

## Top-Level Shape

```json
{
  "schema_version": "0.1.0",
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
      "basis": "Price divided by annualized earnings per share.",
      "warning": null
    }
  ]
}
```

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

## Required MVP Sections

- `overview`
- `valuation`
- `quality`
- `cash_flow`
- `capital_safety`
- `shareholder_returns`
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
