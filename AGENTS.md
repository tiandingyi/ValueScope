# AGENTS.md

Instructions for coding agents working in this repository.

## Project Mission

ValueScope is a local-first value investing screener and research workstation. The MVP focuses on A-share dynamic factor screening, but the project should be designed for future global equity coverage.

## Hard Constraints

- Do not add a database dependency for normal MVP use.
- Do not build brokerage, trading, or automatic investment advice features.
- Do not treat AI output as final buy/sell guidance.
- Do not make A shares a permanent architectural assumption.
- Keep sample data small and inspectable.

## Working Model

This project uses a lightweight Scrum workflow:

- Product roadmap: `docs/product-roadmap.md`
- Backlog: `docs/backlog.md`
- Current sprint: `docs/sprints/sprint-001.md`
- Snapshot schema: `docs/snapshot-schema.md`
- Architecture decisions: `docs/decisions/`

Before implementing a story, read the current sprint file and the relevant backlog card. If the implementation changes data shape, update `docs/snapshot-schema.md`. If it changes a durable architectural choice, add or update an ADR.

## Definition of Done

A story is not done until:

- The app or command is runnable with documented steps.
- Behavior can be verified with sample data.
- Offline and no-database assumptions still hold.
- Pass/fail/missing-data states are visible where relevant.
- Documentation is updated for changed commands, data shape, or workflows.

## Code Style

- Prefer small modules with clear data contracts.
- Keep financial metric semantics explicit.
- Use typed schemas or runtime validation for JSON boundaries.
- Prefer client-side filtering for MVP unless data size proves it insufficient.
- Avoid clever abstractions before the first screener workflow works end to end.

## Financial Domain Rules

- Missing values must be represented as missing, not as zero.
- A screen result must explain why a stock passed or failed.
- Factor filters should disclose metric direction and unit.
- Do not silently mix markets, currencies, or accounting units.
- Any future position sizing output must be framed as research support, not advice.

## Reference Projects

- `/Users/dingyitian/Desktop/stock-scripts`: source of proven A-share financial analysis ideas and metric language.
- `/Users/dingyitian/Desktop/QuantumValue-Terminal`: product experience reference only. Do not assume ValueScope should inherit its database-centered architecture.

## Validation

Until the app stack is chosen, validation is documentation-only. Once code exists, add precise setup and test commands to `README.md` and this file.
