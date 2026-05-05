# Sprint 001: Load and Screen a Local Snapshot

## Sprint Goal

Create the first runnable ValueScope workflow: load a local JSON snapshot, apply basic factor filters, and show explained results.

## Timebox

One week.

## Scope

- Initialize the app skeleton.
- Define snapshot schema v0.
- Add sample snapshot data.
- Load the sample snapshot in the UI.
- Implement 5 basic filter conditions.
- Show a sortable result table.
- Show pass/fail/missing-data explanations.

## User Stories

### US-001: Initialize ValueScope App

As a value investor,
I want a runnable local app shell,
so that future screening work has a stable place to land.

Acceptance Criteria:

- Given a fresh checkout, the README shows the setup and run commands.
- Given the app starts, the first screen is the screener workspace.
- Given no snapshot is loaded, the app shows an empty import state.

### US-002: Define Snapshot Schema v0

As a developer,
I want a documented `screen_snapshot.json` schema,
so that data generation and UI filtering can evolve without guessing.

Acceptance Criteria:

- Given the schema doc, an agent can create a valid sample snapshot.
- Given a snapshot, it includes metadata, metric definitions, and rows.
- Given missing values, they are represented explicitly and safely.

### US-003: Load Local Snapshot

As a value investor,
I want to load a local `screen_snapshot.json`,
so that I can screen stocks without a database or network.

Acceptance Criteria:

- Given a valid snapshot, the app shows generated time, universe, and row count.
- Given an invalid snapshot, the app shows a clear error.
- Given no snapshot, the app shows an empty import state.

### US-004: Apply Basic Factor Filters

As a value investor,
I want to combine financial factor conditions,
so that I can find candidate stocks without editing scripts.

Acceptance Criteria:

- Given a loaded snapshot, the user can add at least 5 filter conditions.
- Given multiple conditions, the app applies them with AND logic.
- Given a condition changes, results update without a server round trip.

### US-005: Explain Pass and Fail Reasons

As a value investor,
I want to see why a stock passed or failed,
so that I do not trust a black-box screener.

Acceptance Criteria:

- Given a passing row, the app shows which conditions it passed.
- Given a failing row, the app can show the first failed condition.
- Given missing data, the app labels the result as missing rather than failed.

## Definition of Done

- The app runs with one documented command.
- The workflow works without database access.
- The workflow works with bundled sample JSON.
- Each completed story has visible UI behavior or terminal output evidence.
- Docs are updated when data shape, commands, or workflow changes.
- No buy/sell or position-size recommendation is presented as investment advice.

## Sprint Review Demo

Demo script:

1. Start the app.
2. Load the sample snapshot.
3. Add a quality filter.
4. Add a valuation filter.
5. Sort the result table.
6. Open pass/fail reasons for one passing stock and one excluded stock.

## Risks

- Starting with too many factors can hide basic UX problems.
- Missing data must be visible, not silently treated as failure.
- A sample dataset that is too fake will make the screener feel untrustworthy.
