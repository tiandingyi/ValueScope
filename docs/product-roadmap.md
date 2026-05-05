# Product Roadmap

## Product Direction

ValueScope is a local-first value investing research workstation and screener. The first version focuses on reproducing the A-share financial report workflow from `stock-scripts`, but the product identity is global: A shares are the initial market, not the permanent boundary.

## Principles

- Local-first by default: normal use should not require a database, Docker, or network.
- Explain every result: every report section and later screen result should show the metric basis, units, warnings, and missing-data states.
- Reproduce proven financial logic: stock-scripts is the first reference for A-share report structure, metrics, and valuation language, but ValueScope owns its implementation.
- Ship workflow increments: each sprint should produce a runnable investor workflow, not only infrastructure.
- Keep AI as a research amplifier: do not make opaque buy/sell recommendations.

## Phases

### Phase 1: A-Share Financial Report MVP

Goal: Generate a local single-stock financial report snapshot and render the stock-scripts-style report in React.

Deliverables:

- `company_report_snapshot.json` v0 schema.
- ValueScope-owned Python report snapshot generator.
- Sample A-share company report snapshot.
- Local report snapshot loader.
- React report page with valuation, quality, cash flow, capital safety, shareholder return, and metric explanation sections.

### Phase 2: A-Share Data Loop Hardening

Goal: Make report snapshot generation and refresh reliable enough for daily single-stock research.

Deliverables:

- Broader report metric coverage until stock-scripts report capability is fully reproduced.
- Refresh metadata and freshness display.
- Source warnings and missing-data diagnostics.
- Reproducible local cache inputs.

### Phase 3: A-Share Screener MVP

Goal: Use the report-grade metric pipeline to generate a stock universe snapshot, compose factor filters, show sortable results, and explain pass/fail reasons.

Deliverables:

- `screen_snapshot.json` v0 schema.
- Small A-share universe snapshot.
- Dynamic filter UI.
- Result table with explanations.
- Missing-data diagnostics.

### Phase 4: Strategy Recipes

Goal: Turn repeated filters into named investing methods.

Deliverables:

- Saved recipes.
- Recipe run history.
- Recipe comparison.
- Guardrails against overfitting and false certainty.

### Phase 5: AI Research Packet Workflow

Goal: Connect report and screening results to deeper company analysis.

Deliverables:

- AI research packet export.
- Financial evidence summary.
- Risk and uncertainty checklist.

### Phase 6: Global Market Expansion

Goal: Extend the same local-first model beyond A shares.

Deliverables:

- Market abstraction layer.
- HK and US snapshot support.
- Currency and accounting-unit normalization.
- Global company metadata schema.

## Deferred

- Brokerage integration.
- Real-time quote streaming.
- Cloud sync.
- User accounts.
- Paid distribution.
