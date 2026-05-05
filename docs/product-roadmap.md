# Product Roadmap

## Product Direction

ValueScope is a local-first value investing screener and research workstation. The first version focuses on A shares, but the product identity is global: A shares are the initial market, not the permanent boundary.

## Principles

- Local-first by default: normal use should not require a database, Docker, or network.
- Explain every result: every stock should show why it passed or failed a screen.
- Reuse proven financial logic: stock-scripts is the first reference for A-share metrics and valuation language.
- Ship workflow increments: each sprint should produce a runnable investor workflow, not only infrastructure.
- Keep AI as a research amplifier: do not make opaque buy/sell recommendations.

## Phases

### Phase 1: A-Share Screener MVP

Goal: Load a local snapshot, compose basic factor filters, show sortable results, and explain pass/fail reasons.

Deliverables:

- `screen_snapshot.json` v0 schema.
- Sample A-share snapshot.
- Local snapshot loader.
- Dynamic filter UI.
- Result table with explanations.

### Phase 2: Better A-Share Data Loop

Goal: Make snapshot generation and refresh reliable enough for daily use.

Deliverables:

- Snapshot exporter that adapts stock-scripts metrics.
- Refresh metadata and freshness display.
- Watchlist universe support.
- Missing-data diagnostics.

### Phase 3: Strategy Recipes

Goal: Turn repeated filters into named investing methods.

Deliverables:

- Saved recipes.
- Recipe run history.
- Recipe comparison.
- Guardrails against overfitting and false certainty.

### Phase 4: Single-Stock Research Workflow

Goal: Connect screening results to deeper company analysis.

Deliverables:

- Single-stock decision card.
- AI research packet export.
- Financial evidence summary.
- Risk and uncertainty checklist.

### Phase 5: Global Market Expansion

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
