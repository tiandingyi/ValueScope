# AGENTS.md

Instructions for coding agents working in this repository.

## Project Mission

ValueScope is a local-first value investing research workstation and screener. The MVP starts by reproducing the A-share financial report workflow from `stock-scripts` as ValueScope-owned Python data generation plus a React report UI. Dynamic factor screening comes after report parity exists.

## Hard Constraints

- Do not add a database dependency for normal MVP use.
- Do not build brokerage, trading, or automatic investment advice features.
- Do not treat AI output as final buy/sell guidance.
- Do not make A shares a permanent architectural assumption.
- Keep sample data small and inspectable.

## Working Model

This project uses a lightweight Scrum workflow:

- Agent handoff: `docs/agent-handoff.md`
- Progress log: `docs/progress.md`
- Working log: `docs/working-log.md`
- Product roadmap: `docs/product-roadmap.md`
- Backlog: `docs/backlog.md`
- Current sprint: `docs/sprints/sprint-001.md`
- Report snapshot schema: `docs/report-snapshot-schema.md`
- Screen snapshot schema: `docs/snapshot-schema.md`
- Architecture decisions: `docs/decisions/`

At the start of every new session, read `docs/agent-handoff.md` first. Before implementing a story, read the current sprint file and the relevant backlog card. If the implementation changes report data shape, update `docs/report-snapshot-schema.md`; if it changes later screening data shape, update `docs/snapshot-schema.md`. If it changes a durable architectural choice, add or update an ADR.

## Definition of Done

A story is not done until:

- The app or command is runnable with documented steps.
- Behavior can be verified with sample data.
- Offline and no-database assumptions still hold.
- Pass/fail/missing-data states are visible where relevant.
- Documentation is updated for changed commands, data shape, or workflows.
- `docs/progress.md` is updated when the story or task advances.
- `docs/agent-handoff.md` is updated when the next session needs new context.
- `docs/working-log.md` is updated for non-trivial coding or planning sessions.

## Code Style

- Prefer small modules with clear data contracts.
- Keep financial metric semantics explicit.
- Use typed schemas or runtime validation for JSON boundaries.
- Keep the Python report generator and React renderer separated by JSON contracts.
- Avoid clever abstractions before the first report workflow works end to end.

## Financial Domain Rules

- Missing values must be represented as missing, not as zero.
- Report metrics must disclose basis, direction, unit, warnings, and missing/not-applicable states.
- A future screen result must explain why a stock passed or failed.
- Future factor filters should disclose metric direction and unit.
- Do not silently mix markets, currencies, or accounting units.
- Any future position sizing output must be framed as research support, not advice.

## Reference Projects

- `/Users/dingyitian/Desktop/stock-scripts`: reference for A-share financial report capability and metric language only; do not import or wrap it.
- `/Users/dingyitian/Desktop/QuantumValue-Terminal`: product experience reference only. Do not assume ValueScope should inherit its database-centered architecture.

## Validation

Until the app stack is chosen, validation is documentation-only. Once code exists, add precise setup and test commands to `README.md` and this file.

## Session Closeout

Before ending a session, leave the next AI agent a clean handoff:

- Update `docs/progress.md` with completed work, verification, and next step.
- Update `docs/agent-handoff.md` if current state, blockers, or next best step changed.
- Append to `docs/working-log.md` if the session involved implementation, debugging, failed attempts, or planning decisions.

## GStack Skill Routing

When gstack skills are available, use the workflow that matches the user's request. If a request clearly matches a skill, prefer the skill. If the match is ambiguous or the user seems to want a direct answer, ask briefly before invoking.

- Product ideas, early scope, or "is this worth building" -> `/office-hours`
- Product ambition, wedge, or founder-level scope review -> `/plan-ceo-review`
- Architecture, sprint implementation plan, data model, or tests -> `/plan-eng-review`
- UX, visual direction, or interaction plan -> `/plan-design-review`
- Full plan review across product, engineering, design, and DX -> `/autoplan`
- Bugs, broken behavior, or unclear failures -> `/investigate`
- Browser or frontend QA -> `/qa` or `/qa-only`
- Code review or diff review before landing -> `/review`
- Visual polish after a UI exists -> `/design-review`
- Shipping, PR creation, changelog, or release prep -> `/ship`
- Deployment follow-through -> `/land-and-deploy`
- Save current context -> `/context-save`
- Resume prior context -> `/context-restore`
