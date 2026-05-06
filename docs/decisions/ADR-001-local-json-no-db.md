# ADR-001: Local JSON Instead of Database for Normal Use

## Status

Accepted

## Date

2026-05-05

## Context

ValueScope should run on a personal machine and eventually support phone-friendly offline workflows. The first user explicitly wants to avoid a database because the static and snapshot data can fit in local JSON files, and normal use should not require network access.

The first market is A shares, but the long-term product should support global equities. This means the storage model must avoid A-share-only assumptions while staying simple enough for the MVP.

## Decision

Use local JSON snapshots as the normal-use persistence layer.

The first contract is `company_report_snapshot.json`. The later screening contract is `screen_snapshot.json`. Later versions may split data into company metadata, financial snapshots, factor snapshots, refresh manifests, and screen-run history.

## Consequences

Positive:

- The app can run without PostgreSQL, Supabase, Docker, or a required remote backend service.
- Snapshots can be copied, archived, inspected, and versioned.
- The data contract is easy for coding agents and humans to review.
- Mobile and desktop workflows remain possible without server orchestration.

Negative:

- Querying and indexing must be handled by the app or precomputed files.
- Large global universes may require sharding or lightweight indexes.
- Concurrent writes and sync conflict handling are not solved by the storage layer.
- Schema compatibility needs explicit versioning discipline.

## Revisit Triggers

Reconsider this decision if:

- Snapshot load time becomes unacceptable on normal hardware.
- Global market data no longer fits comfortably in local files.
- Multi-device sync becomes a core product requirement.
- Multiple users need collaborative shared state.

## Non-Decision

This does not prohibit optional import/export tools, generated indexes, a local API bridge for Python generation, SQLite for advanced local search, or a future cloud product. It only says the first normal workflow must not require a database.
