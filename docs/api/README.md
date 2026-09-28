# Fleet service API (v1)

The machine-readable contract is [`openapi.json`](openapi.json). It is generated from the
code by `fleet-service export-openapi`, committed, and CI fails when it is stale. Interactive
docs are at `/api/v1/docs` on a running service. This page explains the conventions the schema
can't express. The decisions behind them are in ADRs 0009, 0013, 0014, 0018 and 0019.

The WebSocket API and its AsyncAPI document arrive in M1b.

## Authentication

```http
POST /api/v1/auth/login
Content-Type: application/json

{"username": "chief", "password": "…"}
```

- The response carries a `token`, shown only once. Send it as
  `Authorization: Bearer <token>` on every other call.
- Sessions end after **4 hours unused** or **12 hours after login**, whichever comes first.
  Both are configurable with `SARGCS_SESSION_IDLE_TIMEOUT_S` and `SARGCS_SESSION_MAX_LIFETIME_S`.
- A 401 means log in again.
- `POST /auth/logout` ends the current session. Changing your own password
  (`POST /auth/password`) ends your *other* sessions.
- Failed logins get one generic message. Five failures for a username, or twenty from one
  address, within 5 minutes return **429** with `Retry-After`.
- The first admin is created on the ground-station host, never through the API:

  ```bash
  fleet-service create-admin --username chief          # prompts for the password
  ```

## Permissions

Every operation declares `x-permission` in the OpenAPI document. The value is a permission
below, `authenticated` (any valid session) or absent (public: health, version, login).
`GET /auth/me` returns the current user's permissions.

| Permission | Roles |
|---|---|
| `fleet.view` | observer, operator, supervisor, admin |
| `missions.plan` | operator, supervisor, admin |
| `fleet.manage`, `incidents.manage`, `geofences.manage`, `users.view`, `audit.read` | supervisor, admin |
| `users.manage` | admin |

A 403 problem names the permission it lacked in `required_permission`.

## Errors

Every error is an RFC 9457 problem document with media type `application/problem+json`:

```json
{
  "type": "urn:sar-gcs:problem:outside-operating-area",
  "title": "Invalid request",
  "status": 422,
  "detail": "4 vertices outside the incident's operating area (indices 0, 1, 2, 3). Check that latitude and longitude are not swapped: GeoJSON order is [longitude, latitude].",
  "instance": "/api/v1/search-areas",
  "outside_indices": [0, 1, 2, 3]
}
```

Branch on `type`, not on `detail`. Types in v1:

| Status | `type` suffix | Meaning |
|---|---|---|
| 400 | `about:blank` | The body is not parseable JSON or UTF-8 |
| 401 | `unauthenticated`, `invalid-credentials` | No or expired session; wrong login |
| 403 | `forbidden`, `invalid-credentials` | Missing permission; wrong current password |
| 404 | `not-found` | The addressed resource does not exist |
| 409 | `incident-closed`, `invalid-transition`, `mission-not-editable`, `mission-not-deletable`, `aircraft-in-use`, `area-in-use`, `incident-not-empty`, `children-outside-operating-area`, `aircraft-incompatible`, `aircraft-identity-taken`, `task-exists`, `username-taken`, `group-name-taken`, `relay-path-taken`, `last-admin` | The request conflicts with current state |
| 422 | `validation-error` (with `errors[]`), `unknown-reference`, `reference-mismatch`, `outside-operating-area`, `search-area-required`, `too-many-waypoints` | The input is invalid |
| 429 | `rate-limited` | Too many failed logins; see `Retry-After` |

Validation errors list `errors: [{loc, msg, type}]`. Submitted values are never echoed,
because they may be passwords.

## Conventions

- **IDs** are UUIDv7 strings, so they sort by creation time.
- **Timestamps** are RFC 3339 UTC (`2026-09-28T08:00:00Z`).
- **Units** are SI: metres, metres per second, seconds. Every altitude field names its
  reference: `_amsl_m`, `_relative_m` (above each aircraft's home) or `_agl_m`.
- **Positions** are explicit objects, `{"latitude": 47.3977, "longitude": 8.5456}`. Never a
  bare pair.
- **Areas** (search areas, geofences) are GeoJSON Polygons (RFC 7946, `[longitude, latitude]`).
  - One ring with 3–256 vertices, not self-intersecting, and not crossing the antimeridian.
  - Stored counter-clockwise.
  - Every vertex must lie within the incident's `operating_radius_m` of its `base`. This is
    what catches swapped coordinates.
- **Strict types:** `"5"` is not a number and `1` is not `true`. Unknown fields are rejected.
- **Lists** return `{items, next_cursor}`. Pass `cursor=<next_cursor>` for the next page,
  `limit` is 1–500 (default 100), and `next_cursor: null` means the last page. The audit
  trail lists newest first; everything else lists in creation order.
- **PATCH** changes only the fields sent. `null` clears a nullable field, and `null` on a
  non-nullable field is a 422.
- **Every change is audited** in the same transaction, with actor, request id (echo your
  own with `X-Request-ID`), source address and a field-level diff. Credentials are never
  recorded; video source passwords are returned and audited as `***`.

## Resources and rules

| Resource | Notes |
|---|---|
| `users` | Never deleted; deactivate instead (revokes sessions). The last active admin cannot be demoted or deactivated. |
| `aircraft` | Callsign (stored upper-case), MAVLink system ID (1–254) and swarm `drone_id` are each unique. A waypoint or area-search task needs `mavlink_system_id`; a swarm task needs `swarm_drone_id` (ADR 0003). |
| `groups` | `aircraft_ids` is a set; PATCH replaces it. |
| `incidents` | `active` ↔ `suspended` → `closed` (terminal; the incident and its children become read-only). The base can't move, nor the radius shrink, while any geometry would fall outside. Delete only when empty. |
| `search-areas` | `status` can be set by hand (ground teams' results). The geometry is frozen while a non-draft mission uses the area. |
| `geofences` | Inclusion or exclusion, with an optional `max_altitude_relative_m`. Supervisor-managed. |
| `missions` | `draft` ↔ `planned` → `aborted` through the API; `active`, `paused` and `completed` belong to execution (M1b/M4). The plan (area, defaults, waypoints, tasks) only changes in draft or planned. Delete only drafts. |
| `missions/{id}/waypoints` | `PUT` replaces the whole ordered route: at most 1000 waypoints, or 64 for swarm missions (onboard limit). |
| `tasks` | One per (mission, aircraft). `pending` → `cancelled` through the API. |
| `video-streams` | `relay_path` is unique. A PATCH that sends back a redacted (`***`) URL returns 422. |
| `audit` | Filter by `actor_user_id`, `action` prefix (`auth.`, `mission.update`), `entity_type`, `entity_id`, `since`, `until`. |

Integrity of the audit trail is checked on the host with `fleet-service audit-verify`. It
prints the chain head (`seq`, `hash`); record that value elsewhere so truncation of the end
of the trail can be detected too.
