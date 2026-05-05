# Claude Code Guide

Claude Code should follow `CLAUDE.md` at the repo root. This file exists as a short handoff for agents browsing `docs/agents/`.

## Focus

Build the current sprint, not the whole long-term terminal.

## Do

- Read the sprint and schema before implementation.
- Read `docs/agent-handoff.md` at session start.
- Keep JSON boundaries explicit.
- Preserve explainability in filtering.
- Update docs as part of the same story.
- Update progress, handoff, and working-log docs before ending meaningful sessions.

## Do Not

- Add database persistence for MVP.
- Add brokerage or trading automation.
- Present generated output as financial advice.
- Overfit the codebase to A shares only.
