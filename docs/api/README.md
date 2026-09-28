# Fleet service API (v1)

The machine-readable contracts are [`openapi.json`](openapi.json) (REST) and
[`asyncapi.json`](asyncapi.json) (WebSocket). Both are generated from the code
(`fleet-service export-openapi`, `fleet-service export-asyncapi`) and committed, and the tests
fail when either is stale. Interactive docs are at `/api/v1/docs` on a running service. This
page explains what the schemas can't express. The decisions behind it are in ADRs 0009, 0011,
0013, 0014 and 0018–0021.

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
| `missions.plan`, `aircraft.hold`, `aircraft.command`, `alerts.ack` | operator, supervisor, admin |
| `control.override`, `fleet.manage`, `incidents.manage`, `geofences.manage`, `users.view`, `audit.read` | supervisor, admin |
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
| 409 | `command-id-reused`, `control-held`, `not-controller`, `no-controller`, `already-controller`, `handover-pending`, `no-handover-request`, `alert-not-active`, `simulation-disabled` | Commands, control, alerts, simulation (see below) |
| 422 | `validation-error` (with `errors[]`), `unknown-reference`, `reference-mismatch`, `outside-operating-area`, `search-area-required`, `too-many-waypoints`, `system-id-required` | The input is invalid |
| 428 | `confirmation-required` | Re-send the identical command with `confirmation_token` |
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
| `aircraft` | Callsign (stored upper-case), MAVLink system ID (1–254) and swarm `drone_id` are each unique. A waypoint or area-search task needs `mavlink_system_id`; a swarm task needs `swarm_drone_id` (ADR 0003). `mavlink_connection` (e.g. `udpin://0.0.0.0:14550`, or `serial:///dev/ttyUSB0:57600`) needs `mavlink_system_id` (422 `system-id-required`): many aircraft share one connection and are told apart by system id (ADR 0022). Changing either re-links the aircraft; it is `offline` until heard on the new link. An aircraft with command history cannot be deleted (409): its record is kept. |
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

## Live state

- `GET /fleet/state` returns `{simulation, server_time, aircraft: [...]}`. Each aircraft has:
  - `link`: `live`; `stale` after 3 s without telemetry; `lost` after 15 s; `offline` means
    never heard from, or no driver.
  - The latest `telemetry`. Unknown values are `null`: without a GNSS fix, `position` is
    `null`, never a stale guess. `source` is the driver (`mock`, `mavlink`).
    `flight_mode` includes `offboard` (an onboard computer steers the aircraft); for PX4, a
    reposition in progress shows as `goto` (ADR 0022).
  - Its `controller` (lease).
- `GET /aircraft/{id}/telemetry?since&until&limit` returns the recorded history (1 sample
  per second by default), oldest first, with `truncated` when `limit` cut it short.
- `simulation: true` means every aircraft is simulated (ADR 0021). Consoles must show it.
  `POST /simulation/aircraft/{id}/faults` with `{link, gps, battery_pct}` injects faults in
  that mode; outside it the response is 409 `simulation-disabled`.

## Commands

```http
POST /api/v1/commands
{"command_id": "<uuid you generate>", "kind": "takeoff",
 "aircraft_ids": ["…", "…"], "altitude_relative_m": 40}
```

**Kinds and parameters:**

| Kind | Parameters |
|---|---|
| `arm`, `disarm`, `hold`, `resume`, `return_to_launch`, `land` | None |
| `takeoff` | `altitude_relative_m` (required) |
| `goto` | `target: {latitude, longitude}`, optional `altitude_relative_m` |

**Who may send what** (ADR 0011):

- `hold` needs `aircraft.hold`, and every operator may hold every aircraft.
- Everything else needs the aircraft's control lease, or `control.override` (supervisors),
  which counts as an **override**.

**Confirmation.** These commands are answered with **428** `confirmation-required`:

- `arm` and `takeoff`;
- anything sent to more than one aircraft;
- a `goto` farther than 1 km;
- any override.

The response carries a `summary` the operator must see:

- `reasons`;
- per-aircraft `warnings` (stale link, low battery, no 3D fix);
- the aircraft that will be `rejected`, with `code` and `message`;
- the `override` flag.

It also carries a `confirmation_token`, valid for 30 s. Re-send the **identical** body plus
`confirmation_token` to execute. Any change to the request needs a new confirmation. An
expired or invalid token gets a fresh 428 and nothing is sent. Authorization and
preconditions are checked again when the confirmed command is sent.

**Outcome.** The response is always the command, with one target per aircraft:

- `state` is one of `dispatched`, `acked`, `nacked`, `timeout`, `rejected`, and later
  `verified` or `unverified` once telemetry shows, or fails to show, the effect within 10 s.
- `reason_code` and `reason` explain it.

Rejections, where nothing was sent to that aircraft:

| `reason_code` | Meaning |
|---|---|
| `forbidden`, `no-control` | Role, or control lease |
| `no-link`, `link-degraded` | No telemetry; stale/lost link, where only hold, return and land are tried |
| `not-in-air`, `in-air`, `already-armed`, `not-armed`, `not-holding` | Vehicle state; unknown is never assumed favourable |
| `no-gps-fix`, `battery-unknown`, `battery-low` | Flight readiness (minimum 40 % to arm or take off) |
| `altitude-limit`, `distance-limit`, `geofence` | 120 m above home, 10 km goto, geofences of active incidents |
| `rate-limited`, `unsupported` | One command per aircraft per 0.25 s; the link can't carry it |

After dispatch the codes are `refused` (the aircraft said no; `reason` has its answer),
`timeout` (no answer within 5 s, which also raises an alert), `driver-error` and `no-effect`
(unverified).

**Replay:** re-sending a `command_id` returns its outcome without sending it again. Reusing
a `command_id` for a different request returns 409 `command-id-reused`.
`GET /commands?limit` lists recent commands, newest first; `GET /commands/{id}` returns one.

## Control

| Call | Who | Effect |
|---|---|---|
| `POST /aircraft/{id}/control` | `aircraft.command` | Take control of an aircraft nobody controls (409 `control-held` otherwise) |
| `DELETE /aircraft/{id}/control` | Holder | Release |
| `POST /aircraft/{id}/control/handover` | Another operator | Ask for it; expires after 30 s unanswered, and control stays |
| `POST …/handover/accept` or `…/decline` | Holder | Hand over, or keep it |
| `PUT /aircraft/{id}/control` with `user_id` (or `null`) and `reason` | `control.override` | Assign, force or release, with a reason (audited) |
| `GET /control-leases` | `fleet.view` | Every lease, with `state` `held` or `orphaned` and any pending request |

A holder unseen for 60 s (no request and no WebSocket message) makes the lease `orphaned`.
Supervisors get an alert, and **the aircraft keeps doing what it was doing**: nothing is ever
commanded because someone went away. The lease is `held` again when the holder returns.

## Alerts

`GET /alerts?state&aircraft_id` lists alerts newest first. `POST /alerts/{id}/acknowledge`
needs `alerts.ack`.

- **Condition alerts** open and close with their condition:
  - `link_stale` and `link_lost`;
  - `battery_low` (< 30 %) and `battery_critical` (< 15 %);
  - `gps_lost` (in flight);
  - `control_orphaned`.

  Acknowledging only marks them seen.
- **Event alerts** close when acknowledged: `command_timeout` and `command_unverified`.

Raising, acknowledging and clearing are all audited.

## WebSocket (`/api/v1/ws`)

Contract: [`asyncapi.json`](asyncapi.json). A session:

```text
-> {"type": "auth", "token": "sgcs_…"}                 first message, within 5 s
<- {"type": "welcome", "seq": 1, "user": …, "permissions": […], "simulation": true, …}
-> {"type": "subscribe", "topics": ["fleet.telemetry", "alerts", "commands", "control"],
    "telemetry_hz": 4}
<- {"type": "snapshot", "topic": "fleet.telemetry", "seq": 2, "data": {"aircraft": […]}}
<- … one snapshot per topic, then {"type": "event", "topic": …, "seq": n, "data": …}
-> {"type": "ping"}   (at least every 30 s)   <- {"type": "pong", …}
```

- **Never put the token in the URL.** It goes in the first message only.
- **Topics:**
  - `fleet.telemetry` sends the aircraft whose state changed, at most `telemetry_hz` times
    per second (0.5–10), newest state only.
  - `alerts`, `commands` and `control` deliver every change, in order.
- `seq` increases by one per message. A client that reconnects should resubscribe; the
  snapshots resync it.
- **Close codes:**

  | Code | Meaning |
  |---|---|
  | 4400 | Malformed first message |
  | 4401 | Invalid session, or the session was revoked (logout, deactivation, password reset); a `session_ended` message comes first |
  | 4403 | Not permitted |
  | 4408 | No `auth` within 5 s, or no client message for 30 s |
  | 4429 | The client fell behind on reliable events: reconnect and resync. Events are never silently skipped |
