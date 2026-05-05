# Working Log

This file captures session-level details that may save future agents time. It is more granular than `docs/progress.md`.

## Entry Format

```md
## YYYY-MM-DD HH:MM

Task:
- What the session tried to do.

Files Changed:
- Paths changed.

Commands:
- Commands run and important results.

Decisions:
- Small decisions not worth a full ADR.

Problems:
- Errors, failed attempts, or things to avoid next time.

Next:
- Next concrete action.
```

## 2026-05-05 21:45

Task:

- Created persistent project memory docs so new AI sessions can understand current state and continue safely.

Files Changed:

- `docs/progress.md`
- `docs/agent-handoff.md`
- `docs/working-log.md`
- `AGENTS.md`
- `CLAUDE.md`
- `.github/copilot-instructions.md`
- `docs/agents/codex.md`
- `docs/agents/claude-code.md`
- `docs/agents/github-copilot.md`

Commands:

- `rg --files` to verify the project file list.

Decisions:

- Use `docs/agent-handoff.md` as the first-read file for new AI coding sessions.
- Use `docs/progress.md` for user-story and milestone progress.
- Use `docs/working-log.md` for session-level implementation notes.

Problems:

- No app stack exists yet, so validation is limited to file existence and document consistency.

Next:

- Run engineering planning for Sprint 001 and initialize the app skeleton.

## 2026-05-05 21:55

Task:

- Added gstack skill routing to the project docs.

Files Changed:

- `AGENTS.md`
- `CLAUDE.md`
- `docs/agent-handoff.md`
- `docs/progress.md`
- `docs/working-log.md`

Commands:

- Used text search to verify routing phrases were present.

Decisions:

- Routing belongs in project docs, not runtime code.
- `AGENTS.md` and `CLAUDE.md` carry the primary routing rules.

Problems:

- None.

Next:

- Run `/plan-eng-review` before implementation.

## 2026-05-05 22:00

Task:

- Reoriented Sprint 001 based on user direction: report parity before stock screening.

Files Changed:

- `README.md`
- `AGENTS.md`
- `CLAUDE.md`
- `.github/copilot-instructions.md`
- `docs/design-brief.md`
- `docs/product-roadmap.md`
- `docs/backlog.md`
- `docs/sprints/sprint-001.md`
- `docs/snapshot-schema.md`
- `docs/report-snapshot-schema.md`
- `docs/decisions/ADR-002-python-snapshot-exporter-typescript-ui.md`
- `docs/progress.md`
- `docs/agent-handoff.md`
- `docs/working-log.md`

Commands:

- `rg -n "first version|Sprint 001|screen_snapshot|screener|筛选|stock-scripts|company_report|report snapshot|A-Share Screener|Load and Screen" README.md docs AGENTS.md CLAUDE.md .github/copilot-instructions.md`
- `nl -ba` on roadmap, sprint, backlog, schema, and agent files to verify wording.

Decisions:

- Sprint 001 is now `Reproduce Single-Stock Financial Report`.
- First JSON contract is `company_report_snapshot.json`.
- `screen_snapshot.json` is deferred to the later screener phase.
- `stock-scripts` is a reference only; ValueScope owns the Python pipeline.

Problems:

- Several agent docs still had old screener-first wording; updated them so future sessions do not follow stale instructions.

Next:

- Inspect stock-scripts report generation and choose the first report parity slice.
- Scaffold the Python report generator and React report UI after planning is accepted.

## 2026-05-05 22:30

Task:

- Audited `stock-scripts` enough to produce a ValueScope reproduction map and backlog cards before running plan reviews.

Files Changed:

- `docs/reference/stock-scripts-capability-map.md`
- `docs/backlog.md`
- `docs/sprints/sprint-001.md`
- `docs/progress.md`
- `docs/agent-handoff.md`
- `docs/working-log.md`

Commands:

- `rg --files /Users/dingyitian/Desktop/stock-scripts`
- `wc -l` over stock-scripts files
- `rg -n` for functions and report assembly paths in `core/assessment.py`, `core/valuation.py`, `core/render.py`, `core/orchestrator.py`, `core/data_a.py`, `core/data_hk_us.py`, `core/technicals.py`
- `sed` reads of stock-scripts docs and render/orchestrator signatures
- `rg -n "screener workspace|first screen is the screener|Sprint 001.*screen|screening first|import or wrap|stock-scripts.*dependency" README.md AGENTS.md CLAUDE.md .github docs`

Decisions:

- Treat the `render_html(...)` input boundary as the best reference for ValueScope's first `company_report_snapshot.json` shape.
- Split full report reproduction into explicit backlog stories instead of keeping one vague "full report" card.
- Keep screening cards later and make them reuse report-grade metrics.

Problems:

- `stock-scripts` is large and contains both report generation and multiple screeners; the first implementation must avoid drifting into universe screening too early.
- Share-basis handling is subtle and already has a reference regression test in `stock-scripts`; ValueScope should copy the behavior contract, not the implementation.

Next:

- Run `/plan-ceo-review` and `/plan-eng-review` on `docs/reference/stock-scripts-capability-map.md` and `docs/backlog.md`.
- After review, implement Sprint 001 starting with the JSON schema/sample and generator skeleton.
