# 0007. Persistence: SQLite (WAL) with a separate telemetry store

- Status: Accepted
- Date: 2026-09-28

## Context

The fleet service persists:

- **Operational data:** aircraft registry, users, incidents, missions, tasks, search areas,
  geofences, alerts, video stream metadata and control leases.
- **Audit:** every command, outcome, control change and configuration change.
- **Telemetry history** for replay and incident review.

It runs on one field host (ADR 0002, A1), often without an administrator, and may lose power.
After an incident, the complete record must be easy to hand over.

## Decision

- **SQLite in WAL mode**, accessed through **SQLAlchemy 2 (async, aiosqlite)**, with
  **Alembic** migrations (`render_as_batch` for SQLite's limited `ALTER TABLE`).
- **Two database files** in `SARGCS_DATA_DIR`:
  - `ops.db`: operational data and audit, with `synchronous=FULL`, because a confirmed
    command must survive power loss.
  - `telemetry.db`: telemetry samples, with `synchronous=NORMAL`, where losing the last
    second on power loss is acceptable. Heavy telemetry writes never block operational writes.
- **One writer per database file**: the fleet service process. Writes go through a single
  connection per file, and reads such as replay use separate connections (WAL allows concurrent
  readers).
- **Telemetry is downsampled for storage**: 1 Hz per aircraft by default (configurable), written
  in batches every second. The live stream to consoles stays at full rate from memory.
  - Estimate: 50 aircraft × 1 Hz × about 150 B ≈ 27 MB per hour ≈ 650 MB per day.
- **Tamper-evident audit.** `audit_events` is append-only. Each row stores the SHA-256 of
  (the previous row's hash + its own canonical JSON). A verification command re-walks the
  chain. Deletion happens only through the retention job, which records a checkpoint event
  carrying the hash of the last purged row.
- **Retention** is configured per data class and applied by a scheduled purge (M5/M6).
- **Incident export** uses the SQLite online backup API, producing consistent copies of both
  files plus a manifest with hashes (M6).
- **IDs:** UUIDv7 (time-ordered) for entities. Timestamps are UTC, stored as integer
  microseconds for telemetry and ISO 8601 text elsewhere.

## Alternatives considered

- **PostgreSQL + PostGIS + TimescaleDB:** the strongest choice for multi-node, HA or heavy
  analytics. It adds a server to operate, upgrade and back up in the field, and some
  TimescaleDB features are not Apache-licensed. Kept as the **escape hatch**: SQLAlchemy keeps
  most code portable, and SQLite-specific SQL is confined to `db/`.
- **InfluxDB / QuestDB for telemetry:** another service, with licenses that vary by version.
  Not needed at 50 Hz of aggregate writes.
- **DuckDB:** excellent for offline analysis of exported data, and may be used later for
  incident-review tooling. It is not a transactional store for live operations.

## Consequences

- There is nothing to administer, the files are the evidence, and backup is a copy. The whole
  stack runs natively on Windows for development.
- Single host and single writer: no HA. A host failure falls under S6 in ADR 0002 (the aircraft
  fail safe on their own), plus restart from disk.
- Spatial queries such as "aircraft in polygon" run in the application with shapely, not in
  the database. This is fine at 50 aircraft.
