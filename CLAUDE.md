# CLAUDE.md

Guidance for Claude Code when working on ValueScope.

## Product Context

ValueScope is a new project, not a feature branch of QuantumValue-Terminal. Build it as a local-first research workstation that first reproduces the A-share financial report workflow from `stock-scripts`, then adds screening later.

The first milestone is Sprint 001: generate a local single-stock financial report snapshot and render the stock-scripts-style report in React.

## Read First

Before coding, read:

1. `README.md`
2. `docs/agent-handoff.md`
3. `docs/design-brief.md`
4. `docs/sprints/sprint-001.md`
5. `docs/report-snapshot-schema.md`
6. `docs/snapshot-schema.md`
7. `docs/decisions/ADR-001-local-json-no-db.md`
8. `docs/decisions/ADR-002-python-snapshot-exporter-typescript-ui.md`

If the task mentions backlog, roadmap, schema, or sprint scope, read the matching file in `docs/`.

## Scrum Workflow

Use user stories as the unit of work. For each story:

1. Restate the story and acceptance criteria.
2. Implement the smallest slice that satisfies the story.
3. Verify with sample data or a runnable command.
4. Update docs when behavior or data shape changes.
5. Update `docs/progress.md`, `docs/agent-handoff.md`, and `docs/working-log.md` as needed before ending the session.

Do not start unrelated stories just because adjacent files are open.

## Architecture Guardrails

- No database for normal MVP use.
- No server requirement for normal report rendering unless explicitly approved.
- `company_report_snapshot.json` is the first data contract.
- `screen_snapshot.json` is a later screening contract, not the Sprint 001 target.
- Missing metric values must remain distinguishable from numeric zero.
- Every report metric needs basis, unit, warning, missing, or not-applicable metadata where relevant.
- Design market abstractions so `CN-A` is the first market, not the only market forever.

## UI Guardrails

- Build the actual financial report workspace first, not a landing page.
- Keep the interface dense, calm, and work-focused.
- Show report freshness, company identity, coverage years, and schema version.
- Make report sections scannable and warnings easy to find.
- Do not use decorative finance dashboards that hide the core workflow.

## Reference Repos

Use these as references only:

- `/Users/dingyitian/Desktop/stock-scripts`
- `/Users/dingyitian/Desktop/QuantumValue-Terminal`

When reproducing ideas from stock-scripts, preserve metric meaning, document any simplification, and keep the implementation owned by ValueScope.

## Session Memory

New conversations lose prior chat context. Treat repository docs as durable memory.

- Start by reading `docs/agent-handoff.md`.
- Record completed work in `docs/progress.md`.
- Record session details, failed attempts, and useful command results in `docs/working-log.md`.
- Keep `docs/agent-handoff.md` short and current so the next session knows the next best step.

## Skill Routing

If gstack skills are available:

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

If a request clearly matches one of these skills, prefer the skill. If the match is ambiguous or the user seems to want a direct answer, ask briefly before invoking.
