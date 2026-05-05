# Design Brief: ValueScope MVP

## Product Thesis

Most stock research tools either stop at raw metrics or hide the analysis in one-off scripts. ValueScope starts from the opposite premise: a serious individual investor first needs trusted, reproducible, local financial reports that can later become the basis for screening.

## MVP Wedge

Reproduce the `stock-scripts` A-share financial report capability inside ValueScope: generate a local single-stock report snapshot with Python, then render the report in React instead of static HTML.

## User

The first user is an A-share value investor who currently uses `stock-scripts` to generate HTML financial reports, then manually compares companies and feeds key financial data to AI for broader fundamental research.

## Initial Scope

- Generate one `company_report_snapshot.json` for a single A-share company.
- Reproduce the core stock-scripts report sections as ValueScope-owned Python output.
- Show report freshness, source notes, company identity, and coverage years.
- Render the report in React with sections for valuation, quality, cash flow, capital safety, shareholder returns, and metric explanations.
- Preserve missing, not-applicable, and warning states without coercing them to zero.

## Future Scope

- A-share dynamic factor screener.
- Hong Kong, US, and global equities.
- Local data lake with separate company, financial, factor, and screen-run JSON files.
- Strategy recipes.
- AI research packets.
- Position sizing support.

## Key Constraint

No database for normal use. The app should run from local files on a laptop and eventually support phone-friendly offline workflows.

## Engineering Boundary

ValueScope has two intentionally separate layers:

```text
ValueScope data pipeline / Python
  -> reproduce stock-scripts-style report calculations
  -> compute and persist single-stock report data
  -> export company_report_snapshot.json

ValueScope / Vite + React + TypeScript
  -> validate local snapshots with Zod
  -> render the financial report in React
  -> preserve missing, warning, and not-applicable states
```

`stock-scripts` is a reference for report capability and metric language, not a dependency to import or wrap. Sprint 001 should reproduce the single-stock report path first. Screening comes after the report data model and React presentation are trustworthy.
