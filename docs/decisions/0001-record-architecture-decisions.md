# 0001. Record architecture decisions

- Status: Accepted
- Date: 2026-09-28

## Context

The ground control system is built over several sessions, by more than one person or agent,
and it is safety-relevant. Six months from now, "why is it like this?" must have a written answer.

## Decision

Every significant decision gets an Architecture Decision Record in `docs/decisions/`:
a short Markdown file named `NNNN-kebab-title.md` with **Status, Date, Context, Decision,
Alternatives considered, Consequences**. Examples of what counts as significant: a stack choice,
a safety rule, a protocol or convention, or an assumption made in place of an answer from the user.

- ADRs are immutable once accepted. A change of mind is a new ADR that says
  `Supersedes 000N`, and the old one is marked `Superseded by 000M`.
- Assumptions made to keep moving (instead of blocking on a question) are recorded in
  [0002](0002-scope-safety-and-assumptions.md) or in a new ADR, and listed in the milestone report.
- `docs/architecture.md` is the living overview; ADRs are the reasons behind it.

## Consequences

- Reviewers and future sessions can check a change against recorded intent.
- Small cost per decision. Trivial choices (a helper library for one function) don't need an ADR.

## Index

| ADR | Title |
|---|---|
| [0002](0002-scope-safety-and-assumptions.md) | Scope, safety boundaries and assumptions |
| [0003](0003-onboard-swarm-relationship.md) | Relationship to the onboard swarm_sar software |
| [0004](0004-backend.md) | Backend: Python, FastAPI, asyncio |
| [0005](0005-frontend.md) | Frontend: React, TypeScript, Vite |
| [0006](0006-map-and-offline-tiles.md) | Map: MapLibre GL JS with offline PMTiles |
| [0007](0007-persistence.md) | Persistence: SQLite (WAL), separate telemetry store |
| [0008](0008-messaging.md) | Messaging: event bus interface, NATS for out-of-process adapters |
| [0009](0009-auth-and-rbac.md) | Authentication and role-based access |
| [0010](0010-vehicle-drivers.md) | Vehicle integration: driver interface, MAVSDK, ROS 2 bridge, mock |
| [0011](0011-command-authority.md) | Command authority, arbitration and confirmation |
| [0012](0012-video.md) | Video transport: MediaMTX and WebRTC |
| [0013](0013-api-contracts.md) | API contracts: OpenAPI, AsyncAPI, generated clients |
| [0014](0014-geospatial-conventions.md) | Geospatial, altitude and unit conventions |
| [0015](0015-testing-strategy.md) | Testing strategy |
| [0016](0016-deployment.md) | Deployment: single-host Docker Compose, offline |
| [0017](0017-simulation.md) | Simulation: mock fleet, PX4 SITL with Gazebo and SIH |
| [0018](0018-permission-catalogue.md) | Permission catalogue v1 |
| [0019](0019-database-access.md) | Database access, migrations at startup, audit in the same transaction |
| [0020](0020-live-core-commands-control-websocket.md) | Live core: command pipeline, control leases, WebSocket protocol |
| [0021](0021-simulation-mode.md) | Simulation mode and the mock driver |
| [0022](0022-mavlink-driver-mavsdk-v4.md) | MAVLink driver: MAVSDK v4 in-process, shared links, aircraft by system id |
| [0023](0023-sitl-in-ci.md) | PX4 SITL in CI: pinned SIH image, integration tests, link emulator |
| [0024](0024-swarm-bridge-and-nats.md) | The swarm bridge over NATS: contract, sequencing, acknowledgement |
| [0025](0025-aircraft-with-two-links.md) | Aircraft with two links: merged telemetry, routed commands |
| [0026](0026-scale-runs-and-swarm-simulation.md) | Scale runs on the CI runner, and the simulated swarm for the bridge |
| [0027](0027-console-architecture.md) | Console architecture: session, live data, map symbology, confirmation |
| [0028](0028-mission-planning-and-gcs-missions.md) | Mission planning and GCS-planned missions |
| [0029](0029-area-split-deconfliction-bulk-goto.md) | Area split, deconfliction and bulk goto |
| [0030](0030-offline-region-data.md) | Offline region data: basemaps, terrain and imagery |
| [0031](0031-m4-alerts-and-points-of-interest.md) | M4 alerts, points of interest and survivor sightings |
| [0032](0032-console-planning-and-tasking.md) | Console: incidents, planning, tasking and points of interest |
| [0033](0033-no-gazebo-tier.md) | No Gazebo simulation tier |
| [0034](0034-video-multi-operator-audit-retention.md) | Video, multi-operator control, audit viewer and retention |
| [0035](0035-preflight-checks-and-degraded-links.md) | Preflight failsafe checks and degraded links |
| [0036](0036-relay-access-and-container-hardening.md) | Relay access control and container hardening |
| [0037](0037-windows-package.md) | The Windows single-machine package |
