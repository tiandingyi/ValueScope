# Design Brief: ValueScope MVP

## Product Thesis

Most stock screeners assume users want more realtime cloud data. ValueScope starts from the opposite premise: a serious individual investor first needs trusted, reproducible, local financial snapshots that can be screened offline and explained clearly.

## MVP Wedge

Build an A-share dynamic factor screener that reads a local JSON snapshot and lets the user compose financial conditions without editing scripts.

## User

The first user is an A-share value investor who currently uses `stock-scripts` to generate HTML financial reports, then manually compares companies and feeds key financial data to AI for broader fundamental research.

## Initial Scope

- Import or generate one `screen_snapshot.json`.
- Show data freshness and snapshot metadata.
- Support 5-10 core filters across quality, valuation, cash flow, leverage, and size/liquidity.
- Display sortable candidate results.
- Explain pass/fail conditions for every row.

## Future Scope

- Hong Kong, US, and global equities.
- Local data lake with separate company, financial, factor, and screen-run JSON files.
- Strategy recipes.
- Single-stock decision cards.
- AI research packets.
- Position sizing support.

## Key Constraint

No database for normal use. The app should run from local files on a laptop and eventually support phone-friendly offline workflows.
