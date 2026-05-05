# Codex Guide

## Role

Codex should act as the implementation partner for ValueScope. Respect the Scrum docs and keep changes tied to the active sprint.

## Before Coding

Read:

- `AGENTS.md`
- `docs/agent-handoff.md`
- `docs/sprints/sprint-001.md`
- `docs/snapshot-schema.md`
- `docs/decisions/ADR-001-local-json-no-db.md`

## Work Rules

- Use the current sprint as the source of scope.
- Keep edits small and story-centered.
- Update docs when commands, schema, or workflow changes.
- Add sample data and verification steps when code begins.
- Do not silently pull logic from reference repos without documenting the metric meaning.
- Before finishing, update progress and handoff docs when state changed.

## Review Checklist

- Does it run offline?
- Does it avoid database assumptions?
- Does it preserve missing-vs-zero?
- Does it explain pass/fail/missing screen outcomes?
- Does it keep A shares as the first market rather than the whole product identity?
- Did this session leave `docs/agent-handoff.md` accurate for the next AI conversation?
