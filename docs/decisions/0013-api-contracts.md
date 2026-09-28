# 0013. API contracts: OpenAPI, AsyncAPI, generated clients

- Status: Accepted
- Date: 2026-09-28

## Context

The console, tests, the ROS bridge and future integrations (for example incident-management
software) consume the fleet service's REST and WebSocket APIs. Hand-maintained specs drift
from code, and hand-written client types drift from both.

## Decision

### REST

- Base path `/api/v1`, resource-oriented JSON.
- Errors are **RFC 9457 `application/problem+json`**, with a stable `type` URI per error kind
  (for example `.../problems/confirmation-required`).
- Cursor pagination. Timestamps are RFC 3339 UTC, and IDs are UUIDv7 (ADR 0007).
- Every model forbids unknown fields.

### OpenAPI 3.1

- **Generated** by FastAPI from the Pydantic models, and **committed** to
  `docs/api/openapi.json` by `fleet-service export-openapi`.
- **CI fails if the committed spec differs** from the generated one, so every API change shows
  up in review as a spec diff.

### WebSocket

- One endpoint, `/api/v1/ws`. The first message authenticates (ADR 0009).
- Envelopes have the form `{type, topic, seq, ts, data}`. Clients subscribe and unsubscribe
  to topics such as:
  - `fleet.telemetry`
  - `aircraft.<id>.telemetry`
  - `alerts`
  - `missions`
  - `commands`
  - `control`
  - `operators`
- A **snapshot on subscribe, then deltas**. A per-connection `seq` exposes gaps, and on a gap
  the client resyncs over REST.
- The server **coalesces** telemetry per aircraft to the client's requested rate (ADR 0008).

### AsyncAPI 3.0

- Generated from the WebSocket message registry in code, committed to `docs/api/asyncapi.yaml`,
  with the same drift check as OpenAPI.

### Clients and contract tests

- **TypeScript types** are generated with `openapi-typescript` into
  `fleet-console/src/api/generated/`, and committed for reviewable diffs.
- **Contract tests:**
  - **Schemathesis** runs property-based tests against the in-process app.
  - Every WebSocket message type is validated against its schema.
  - The console's generated types must compile.

### Versioning

Additive changes stay within v1. Breaking changes need `/api/v2` and an ADR.

## Alternatives considered

- **gRPC / gRPC-web:** compact, with codegen, but it needs a browser proxy and is hard to
  inspect in the field.
- **GraphQL subscriptions:** flexible, but authorization per field and caching get more
  complex for little benefit here.
- **Server-Sent Events + REST:** simpler, and one-way push is enough for telemetry.
  WebSocket was chosen for cheap subscription changes and presence, meaning heartbeats that
  drive the lease grace period in ADR 0011. SSE remains an easy fallback.
- **Hand-written specs:** they drift.

## Consequences

- The Pydantic models are the single source of truth, so API design happens in them.
- JSON bandwidth is about 50 aircraft × 5 Hz × 400 B ≈ 100 KB/s per console, which is fine on
  a LAN. Remote observers over cellular get coalescing and field filtering. A binary encoding
  (MessagePack) is a later option behind the same envelope.
