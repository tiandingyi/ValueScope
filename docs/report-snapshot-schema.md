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
    "years": ["2021", "2022", "2023", "2024", "2025"]
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
- `company.ticker`: market-local ticker.
- `company.name`: company display name.
- `company.market`: market identifier, initially `CN-A`.
- `company.currency`: market currency for price and valuation fields.
- `company.accounting_unit`: accounting currency/unit used by financial statements.
- `coverage.period_type`: report period basis, initially `annual`.
- `coverage.years`: years included in the report snapshot.
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

## Compatibility Rules

- Patch versions may add optional fields.
- Minor versions may add sections, metrics, or metadata.
- Major versions may change section or metric semantics.
- The UI must reject unsupported major versions with a clear error.
