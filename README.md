# ValueScope

ValueScope is a local-first value investing screener and research workstation.

The first version focuses on A-share dynamic factor screening. The long-term product should support global equities without requiring a database for normal offline use.

## First Version

- Market: A shares first.
- Storage: local JSON snapshots.
- Core workflow: load a stock universe, combine financial factor conditions, rank candidates, and explain why each stock passed or failed.
- Data source direction: reuse or adapt proven metric logic from `stock-scripts`.
- Product reference: terminal-style workflow inspired by `QuantumValue-Terminal`, but this is a new project.

## Non-Goals for MVP

- No database dependency.
- No full global market coverage yet.
- No live trading or brokerage integration.
- No automatic buy/sell or position-size decision as the first feature.
- No opaque AI recommendation engine.

## Next Step

Define the MVP engineering plan:

1. Choose the app stack.
2. Define `screen_snapshot.json`.
3. Build the local snapshot loader.
4. Build the dynamic factor filter UI.
5. Add explainable pass/fail reasons.
