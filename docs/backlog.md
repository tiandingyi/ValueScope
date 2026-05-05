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
so that future screening work has a stable place to land.

Acceptance Criteria:

- Given a fresh checkout, the README shows the setup and run commands.
- Given the app starts, the first screen is the screener workspace, not a marketing page.
- Given no snapshot is loaded, the app shows an empty import state.

Notes:

- Choose the app stack during engineering planning.
- Keep the UI local-first and offline-friendly.

## US-002: Define Snapshot Schema v0

As a developer,
I want a documented `screen_snapshot.json` schema,
so that data generation and UI filtering can evolve without guessing.

Acceptance Criteria:

- Given the schema doc, an agent can create a valid sample snapshot.
- Given a snapshot, it includes metadata, metric definitions, and rows.
- Given missing values, they are represented explicitly and safely.

Notes:

- See `docs/snapshot-schema.md`.

## US-003: Load Local Snapshot

As a value investor,
I want to load a local `screen_snapshot.json`,
so that I can screen stocks without a database or network.

Acceptance Criteria:

- Given a valid snapshot, the app shows generated time, universe, and row count.
- Given an invalid snapshot, the app shows a clear error.
- Given no snapshot, the app shows an empty import state.

Notes:

- MVP can start with bundled sample data before file import is polished.

## US-004: Apply Basic Factor Filters

As a value investor,
I want to combine financial factor conditions,
so that I can find candidate stocks without editing scripts.

Acceptance Criteria:

- Given a loaded snapshot, the user can add at least 5 filter conditions.
- Given multiple conditions, the app applies them with AND logic.
- Given a condition changes, results update without a server round trip.

Notes:

- First filter families: valuation, quality, cash flow, leverage, size/liquidity.

## US-005: Explain Pass and Fail Reasons

As a value investor,
I want to see why a stock passed or failed,
so that I do not trust a black-box screener.

Acceptance Criteria:

- Given a passing row, the app shows which conditions it passed.
- Given a failing row, the app can show the first failed condition.
- Given missing data, the app labels the result as missing rather than failed.

Notes:

- Explanation is a product feature, not debug output.

## Later Backlog

## US-006: Generate Snapshot from stock-scripts

As a value investor,
I want to export a ValueScope snapshot from stock-scripts-derived metrics,
so that existing financial logic feeds the new UI.

Acceptance Criteria:

- Given a list of A-share tickers, an exporter creates `screen_snapshot.json`.
- Given stale cached data, the exporter marks freshness in metadata.
- Given failed ticker processing, the exporter records the error without aborting the whole run.

## US-007: Save Strategy Recipes

As a value investor,
I want to save a named filter recipe,
so that I can rerun my investing method consistently.

Acceptance Criteria:

- Given a filter set, the user can save it with a name.
- Given a saved recipe, the user can rerun it on a new snapshot.
- Given changed metric definitions, the app warns about schema mismatch.

## US-008: Export AI Research Packet

As a value investor,
I want to export a candidate's financial facts as Markdown or JSON,
so that AI can research the company's business fundamentals with clean context.

Acceptance Criteria:

- Given a selected stock, the app exports key financial evidence.
- Given missing data, the packet includes uncertainty notes.
- Given exported content, it avoids pretending to be final investment advice.
