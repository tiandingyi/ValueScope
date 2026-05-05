# Snapshot Schema

## File

`screen_snapshot.json`

## Version

`schema_version: "0.1.0"`

## Purpose

The screen snapshot is the later local data contract for universe screening. It is not the first Sprint 001 contract; the first workflow uses `company_report_snapshot.json`, documented in `docs/report-snapshot-schema.md`.

## Top-Level Shape

```json
{
  "schema_version": "0.1.0",
  "generated_at": "2026-05-05T00:00:00Z",
  "source": {
    "name": "stock-scripts",
    "version": "manual-or-commit-hash",
    "notes": "optional"
  },
  "universe": {
    "market": "CN-A",
    "name": "sample-a-share",
    "row_count": 2
  },
  "metric_definitions": {},
  "rows": []
}
```

## Required Metadata

- `schema_version`: semantic version for compatibility checks.
- `generated_at`: ISO 8601 timestamp.
- `source.name`: data generator or adapter name.
- `universe.market`: market identifier, initially `CN-A`.
- `universe.name`: human-readable universe label.
- `universe.row_count`: number of rows expected.
- `metric_definitions`: dictionary describing each metric.
- `rows`: stock-level records.

## Row Shape

```json
{
  "ticker": "000858",
  "name": "五粮液",
  "market": "CN-A",
  "as_of": "2026-05-05",
  "metrics": {
    "pe": 18.2,
    "roe": 23.4,
    "roic": 18.1,
    "ocf_positive_years": 5,
    "debt_to_assets": 0.31,
    "market_cap_cny_bn": 620.5
  },
  "data_quality": {
    "missing_metrics": [],
    "warnings": []
  }
}
```

## Metric Definition Shape

```json
{
  "pe": {
    "label": "PE",
    "unit": "multiple",
    "direction": "lower_is_better",
    "description": "Price divided by earnings per share.",
    "source": "stock-scripts"
  }
}
```

## Missing Data Rules

- Use `null` for known missing values.
- Do not use `0` to mean missing.
- Record missing metric names in `data_quality.missing_metrics`.
- Filters should return `missing` when required input is `null`.

## MVP Metric Candidates

- `pe`
- `pb`
- `roe`
- `roic`
- `gross_margin`
- `ocf_positive_years`
- `owner_earnings_yield`
- `debt_to_assets`
- `interest_coverage`
- `market_cap_cny_bn`

## Compatibility Rules

- Patch versions may add optional fields.
- Minor versions may add metrics or metadata sections.
- Major versions may change row or metric semantics.
- The UI must reject unsupported major versions with a clear error.
