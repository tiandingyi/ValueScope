# Sprint 001: Reproduce Single-Stock Financial Report

## Sprint Goal

Create the first runnable ValueScope workflow: generate a local single-stock financial report snapshot and render the report in React.

## Timebox

One week.

## Scope

- Initialize the app skeleton.
- Define `company_report_snapshot.json` schema v0.
- Add a minimal ValueScope-owned Python report snapshot generator.
- Add a local FastAPI bridge so the React workspace can trigger report generation.
- Generate and commit one small sample company report snapshot.
- Load the report snapshot in the UI.
- Render stock-scripts-style report sections in React.
- Show missing, warning, and not-applicable states clearly.

## User Stories

### US-001: Initialize ValueScope App

As a value investor,
I want a runnable local app shell,
so that future report and screening work has a stable place to land.

Acceptance Criteria:

- Given a fresh checkout, the README shows the setup and run commands.
- Given the app starts, the first screen is the report workspace.
- Given no snapshot is loaded, the app shows an empty import state.

### US-002: Define Company Report Snapshot Schema v0

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

### US-003: Generate Company Report Snapshot

As a value investor,
I want ValueScope to generate a local company report snapshot,
so that the new app can reproduce stock-scripts report analysis without depending on stock-scripts.

Acceptance Criteria:

- Given the report generator runs for a supported sample company, it writes `company_report_snapshot.json`.
- Given generated sections, they include valuation, quality, cash flow, capital safety, shareholder return, and metric explanations where data is available.
- Given the latest fiscal year does not have a confirmed annual report row, the generator ignores quarterly, interim, or unverified `YYYY1231` rows and uses the latest confirmed annual report year instead.
- Given the provider lacks explicit report-type metadata, the generator applies a conservative cutoff and excludes the previous fiscal year unless annual provenance is explicit.
- Given historical report tables are rendered, they show all annual-report years available in the snapshot rather than only the most recent five years.
- Given missing source values, the generated snapshot records them as missing rather than zero.
- Given the generator cannot fetch or compute a metric, it records a warning without pretending the value is valid.

### US-004: Load Local Report Snapshot

As a value investor,
I want to load a local `company_report_snapshot.json`,
so that I can inspect a financial report without a database or network.

Acceptance Criteria:

- Given a valid snapshot, the app shows generated time, company identity, market, schema version, and coverage years.
- Given an invalid snapshot, the app shows a clear error.
- Given no snapshot is loaded, the app shows an empty report state.

### US-005: Render Financial Report

As a value investor,
I want to read the generated financial report in React,
so that the old static HTML report workflow becomes an interactive local workstation.

Acceptance Criteria:

- Given a loaded report snapshot, the app renders the core report sections.
- Given an annual data table is shown, it displays all available annual-report rows from the snapshot, not just the latest five rows.
- Given a year is absent because no confirmed annual report exists, the UI does not infer or synthesize that year from quarterly data.
- Given the stock-scripts reference report for the same company, the React report matches its information hierarchy closely enough that the first screen shows company identity, report context, key metrics, warning states, and the start of the analytical sections.
- Given a desktop and mobile screenshot, report text, metric values, cards, tables, and navigation do not overlap, clip, or wrap one character per line.
- Given the committed sample snapshot, the rendered report demonstrates realistic section density rather than looking like a schema preview.
- Given a metric has a unit or direction, the UI displays it explicitly.
- Given a metric is missing or not applicable, the UI labels that state rather than hiding it.
- Given a warning exists, the UI shows it near the affected section.

## Definition of Done

- The app runs with one documented command.
- The report snapshot generator runs with one documented command.
- The local FastAPI bridge runs with one documented command.
- The workflow works without database access.
- The workflow works with generated or committed report snapshot JSON.
- Each completed story has visible UI behavior or terminal output evidence.
- Report-rendering stories include screenshot evidence against the stock-scripts reference report.
- Docs are updated when data shape, commands, or workflow changes.
- No buy/sell or position-size recommendation is presented as investment advice.

## Sprint Review Demo

Demo script:

1. Run the company report snapshot generator.
2. Start the app.
3. Load the generated or committed report snapshot.
4. Review valuation, quality, cash flow, capital safety, shareholder return, and metric explanation sections.
5. Confirm missing and warning states are visible.

## Completion Evidence

Status: Done on 2026-05-06.

- Generator command: `PYTHONPATH=python python3 -m valuescope.cli 000858 --years 8`
- App command: `npm run dev`
- FastAPI bridge command: `PYTHONPATH=python uvicorn valuescope.api:app --reload`
- Sample snapshot: `public/samples/company_report_snapshot.json`
- The `000858` sample covers annual years 1995 through 2024 and excludes the unverified 2025 row with a visible warning.
- Core sections present in the snapshot and UI: valuation, quality, cash flow, capital safety, shareholder returns, annual rows, valuation history, owner earnings yield, retained earnings check, diagnostics, and metric explanations.
- Verification passed:
  - `PYTHONPATH=python python3 -m pytest tests/python -q`
  - `npm test -- --run`
  - `npm run build`
  - `npm run test:e2e`
- Screenshot evidence:
  - `test-results/current-valuescope-sprint1-desktop.png`
  - `test-results/current-valuescope-sprint1-mobile.png`

## Risks

- Under-reproducing the old report will make ValueScope feel weaker than stock-scripts.
- Missing data must be visible, not silently treated as zero.
- A sample dataset that is too fake will make the report feel untrustworthy.
- If Sprint 001 also attempts universe screening, the report parity work may stall before the first demo.
