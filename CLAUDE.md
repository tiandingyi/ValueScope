# CLAUDE.md

Guidance for Claude Code when working on ValueScope.

## Product Context

ValueScope is a new project, not a feature branch of QuantumValue-Terminal. Build it as a local-first screener that starts with A shares and can later expand globally.

The first milestone is Sprint 001: load a local JSON snapshot, combine basic factor filters, show sortable candidates, and explain pass/fail reasons.

## Read First

Before coding, read:

1. `README.md`
2. `docs/design-brief.md`
3. `docs/sprints/sprint-001.md`
4. `docs/snapshot-schema.md`
5. `docs/decisions/ADR-001-local-json-no-db.md`

If the task mentions backlog, roadmap, schema, or sprint scope, read the matching file in `docs/`.

## Scrum Workflow

Use user stories as the unit of work. For each story:

1. Restate the story and acceptance criteria.
2. Implement the smallest slice that satisfies the story.
3. Verify with sample data or a runnable command.
4. Update docs when behavior or data shape changes.

Do not start unrelated stories just because adjacent files are open.

## Architecture Guardrails

- No database for normal MVP use.
- No server requirement for client-side screening unless explicitly approved.
- `screen_snapshot.json` is the first data contract.
- Missing metric values must remain distinguishable from numeric zero.
- Every filter result needs explainability metadata.
- Design market abstractions so `CN-A` is the first market, not the only market forever.

## UI Guardrails

- Build the actual screener workspace first, not a landing page.
- Keep the interface dense, calm, and work-focused.
- Show snapshot freshness, universe, row count, and schema version.
- Make filter controls obvious and reversible.
- Do not use decorative finance dashboards that hide the core workflow.

## Reference Repos

Use these as references only:

- `/Users/dingyitian/Desktop/stock-scripts`
- `/Users/dingyitian/Desktop/QuantumValue-Terminal`

When borrowing ideas from stock-scripts, preserve metric meaning and document any simplification.

## Skill Routing

If gstack skills are available:

- Product ideas or scope changes: `/office-hours`
- Strategy and product review: `/plan-ceo-review`
- Engineering plan: `/plan-eng-review`
- Design review: `/plan-design-review`
- QA web behavior: `/qa` or `/qa-only`
- Code review before landing: `/review`
- Ship or PR flow: `/ship`
