# Sprint 001: Reproduce Single-Stock Financial Report

## Sprint Goal

Create the first runnable ValueScope workflow: generate a local single-stock financial report snapshot and render the report in React.

## Timebox

One week.

## Scope

- Initialize the app skeleton.
- Define `company_report_snapshot.json` schema v0.
- Add a minimal ValueScope-owned Python report snapshot generator.
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

### US-003: Generate Company Report Snapshot

As a value investor,
I want ValueScope to generate a local company report snapshot,
so that the new app can reproduce stock-scripts report analysis without depending on stock-scripts.

Acceptance Criteria:

- Given the report generator runs for a supported sample company, it writes `company_report_snapshot.json`.
- Given generated sections, they include valuation, quality, cash flow, capital safety, shareholder return, and metric explanations where data is available.
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
- Given a metric has a unit or direction, the UI displays it explicitly.
- Given a metric is missing or not applicable, the UI labels that state rather than hiding it.
- Given a warning exists, the UI shows it near the affected section.

## Definition of Done

- The app runs with one documented command.
- The report snapshot generator runs with one documented command.
- The workflow works without database access.
- The workflow works with generated or committed report snapshot JSON.
- Each completed story has visible UI behavior or terminal output evidence.
- Docs are updated when data shape, commands, or workflow changes.
- No buy/sell or position-size recommendation is presented as investment advice.

## Sprint Review Demo

Demo script:

1. Run the company report snapshot generator.
2. Start the app.
3. Load the generated or committed report snapshot.
4. Review valuation, quality, cash flow, capital safety, shareholder return, and metric explanation sections.
5. Confirm missing and warning states are visible.

## Risks

- Under-reproducing the old report will make ValueScope feel weaker than stock-scripts.
- Missing data must be visible, not silently treated as zero.
- A sample dataset that is too fake will make the report feel untrustworthy.
- If Sprint 001 also attempts universe screening, the report parity work may stall before the first demo.
