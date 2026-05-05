# ValueScope

ValueScope is a local-first value investing research workstation and screener.

The first version focuses on reproducing the A-share financial report workflow from `stock-scripts` as a ValueScope-owned Python data pipeline plus a React report UI. Dynamic factor screening comes after the report capability exists. The long-term product should support global equities without requiring a database for normal offline use.

## First Version

- Market: A shares first.
- Storage: local JSON snapshots.
- Snapshot generation: ValueScope-owned Python pipeline that reproduces the needed stock financial report capabilities.
- App stack: Vite, React, TypeScript, Zod, Vitest, and Playwright.
- Core workflow: generate a single-stock financial report snapshot, load it locally, and render the report in React.
- Data source direction: study `stock-scripts` for proven A-share metric language and workflows, but do not depend on it at runtime.
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
2. Define `company_report_snapshot.json`.
3. Build the ValueScope-owned Python report snapshot generator.
4. Build the local report snapshot loader.
5. Render the financial report in React.
