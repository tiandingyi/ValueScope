# GitHub Copilot Guide

GitHub Copilot should use `.github/copilot-instructions.md` as its primary instruction file.

## Product Summary

ValueScope is a local-first financial screener. MVP data comes from local JSON snapshots. First market is A shares, future markets include HK, US, and global equities.

## Important Behaviors

- Missing metric values are `null`, not `0`.
- Filter results need pass, fail, and missing explanations.
- Snapshot schema changes must be reflected in `docs/snapshot-schema.md`.
- No database should be required for normal MVP use.
- Meaningful changes should update `docs/progress.md`.
- Changes that affect the next session should update `docs/agent-handoff.md`.
- Non-trivial sessions should append to `docs/working-log.md`.
