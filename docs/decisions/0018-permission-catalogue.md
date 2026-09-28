# 0018. Permission catalogue v1

- Status: Accepted
- Date: 2026-09-28
- Refines: [0009](0009-auth-and-rbac.md)

## Context

ADR 0009 fixed four hierarchical roles and a coarse capability table. M1a needs the exact
permission names that code checks and that clients can read. It also needs owners for
resources that ADR 0009 didn't cover: the aircraft registry, groups and video stream
configuration.

## Decision

Handlers check **permissions**, never role names. Each permission has a minimum role, and a
higher role has every permission of the roles below it.

| Permission | Minimum role | Covers |
|---|---|---|
| `fleet.view` | observer | Reading everything operational: aircraft, groups, incidents, search areas, geofences, missions, waypoints, tasks, video stream metadata |
| `missions.plan` | operator | Creating and changing search areas, missions, waypoints and tasks |
| `fleet.manage` | supervisor | The aircraft registry, groups, video stream configuration |
| `incidents.manage` | supervisor | Opening, changing, closing and deleting incidents |
| `geofences.manage` | supervisor | Geofences |
| `users.view` | supervisor | Listing accounts, for example to assign aircraft in M1b |
| `audit.read` | supervisor | The audit trail |
| `users.manage` | admin | Creating accounts, changing roles, deactivating, resetting passwords |

Some operations need a valid session and no particular permission: logout, `me`, and
changing one's own password. They are marked `authenticated`. Health, version and login are
public.

- **Published and enforced from one place.** `api.deps.requires(permission)` adds both the
  check and the OpenAPI extension `x-permission`. Clients can read the requirement from the
  document, and the authorization-matrix test checks behaviour against it for every
  operation and role.
- **The registry is supervisor-owned.** Registering aircraft, changing their links and
  configuring video sources are equipment decisions made by the person accountable for the
  fleet, not by an individual operator. Operators still plan and task.
- **Search areas are operator-planned; geofences are supervisor-owned.** A search area only
  shapes where aircraft look. A geofence changes where aircraft may fly, which is a safety
  boundary.
- The M1b command permissions (`aircraft.hold`, `aircraft.command`, `control.override`,
  `alerts.ack`) will be added the same way.

## Alternatives considered

- **Role checks in handlers:** the mapping would be scattered and untestable as a whole.
- **Operators manage the registry:** convenient for very small teams, but it loses
  accountability for the equipment list. Such a team can give its members the supervisor role.

## Consequences

- A permission-to-role change is one line in `auth/permissions.py`, plus an update to this
  table through a superseding ADR.
- The console can grey out actions from `GET /auth/me` → `permissions`, while the server stays
  authoritative.
