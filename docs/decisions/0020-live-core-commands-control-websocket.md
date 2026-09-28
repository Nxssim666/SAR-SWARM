# 0020. Live core: command pipeline, control leases, WebSocket protocol

- Status: Accepted
- Date: 2026-09-28
- Refines: [0008](0008-messaging.md), [0011](0011-command-authority.md),
  [0013](0013-api-contracts.md)

## Context

ADR 0011 set the rules for command authority and confirmation, ADR 0008 the delivery classes
of the event bus, and ADR 0013 the WebSocket contract. Implementing them in M1b needed
concrete answers to five questions:

- How a command request travels from HTTP to the aircraft and back.
- What a confirmation token is.
- How a "gone" operator is detected.
- What the WebSocket protocol looks like on the wire.
- How the periodic work (link ageing, alerts, verification) runs without making tests
  depend on time.

## Decision

### Command pipeline (`services/commands.py`, rules in `domain/commands.py`)

1. **One synchronous request.** `POST /commands` runs the whole pipeline and answers with
   the outcome for every aircraft. Dispatch is concurrent, and each aircraft is bounded by
   the command timeout (default 5 s). The transaction is committed before waiting for
   aircraft, so no database connection is held while radios answer (ADR 0019 rule 3).

2. **Status codes:**

   | Situation | Response |
   |---|---|
   | Executed, or rejected per aircraft | 200 with the per-aircraft outcome |
   | Confirmation needed | 428 |
   | Unknown aircraft ids | 422 |
   | `command_id` reused with a different body or by another user | 409 |
   | Identical replay | The first outcome |
   | The role lacks `aircraft.hold` | 403 (route level) |

3. **Per-aircraft rules** are pure functions, tested row by row:
   - authority (HOLD for every operator; everything else needs the lease, or
     `control.override`, which always counts as an override);
   - capability of the driver;
   - link state (only HOLD, RETURN and LAND on a stale or lost link);
   - vehicle state, where **unknown is never assumed favourable**;
   - limits: altitude, goto distance, geofences of active incidents;
   - a 0.25 s per-aircraft rate limit.

   Rejections carry a stable `reason_code`.

4. **Confirmation** is required for:
   - arm and takeoff;
   - more than one accepted aircraft;
   - goto beyond 1 km;
   - any override.

   The server answers **428** with a summary it computed itself: the aircraft, each one's
   warnings (stale link, low battery, no 3D fix), and the aircraft that will be rejected.

5. **The confirmation token** is `expiry.HMAC-SHA256(secret, user | command_id |
   request hash | expiry)`.
   - The secret is random per process, so tokens don't survive a restart, by design.
   - The request hash covers the whole body except the token, so any change to the request
     needs a new confirmation.
   - An invalid or expired token simply gets a fresh 428; nothing is sent.
   - The command row waits in `awaiting_confirmation` and is marked `expired` after the TTL
     (30 s).

6. **Re-check at dispatch.** Authorization and preconditions run again when a confirmed
   command is sent. A change during the confirmation window can only reject more aircraft.

7. **Effect verification.** Every acked command has an expected effect on telemetry, such as
   the mode becoming `return` or `armed` turning true. A sample *newer than the ack* must show
   it within 10 s. Otherwise the target becomes `unverified` and an alert is raised.

8. **Target states:** `pending → dispatched → acked | nacked | timeout`, or `rejected`, then
   `acked → verified | unverified`. **Command states:** `awaiting_confirmation`,
   `in_progress`, `completed`, `rejected`, `expired`.

### Control leases and presence (`services/leases.py`)

- Leases live in memory, mirrored to `control_leases`.
- **Handover:**
  - The requester asks and the holder accepts or declines.
  - An unanswered request expires after 30 s, and control does not move.
- Supervisors assign or release with a mandatory reason. An assignee must hold
  `aircraft.command`.
- **Presence** is an in-memory map of when each user was last seen, updated by every
  authenticated request and every WebSocket message.
  - A holder unseen for 60 s makes the lease `orphaned`, and supervisors are alerted.
  - The lease is `held` again as soon as the holder is seen.
  - **Nothing is ever commanded because an operator went away.**
- After a restart every holder gets a full grace period to reconnect.

### Alerts (`services/alerts.py`)

- **Condition alerts** are raised and cleared by evaluation:
  - link stale or lost;
  - battery low (< 30 %) or critical (< 15 %);
  - GNSS lost in flight;
  - control orphaned.
- **Event alerts** are closed by acknowledgement: command timeout, command unverified.
- One open alert per dedupe key. Raise, acknowledge and clear are all audited.

### Periodic work (`services/runtime.py`)

- The simulation steps at 10 Hz.
- Evaluation (links, leases, alerts, confirmations, verification) runs at 2 Hz.
- The telemetry recorder runs at 1 Hz.
- These are asyncio loops that survive errors in a single iteration.
- Tests build the app with `start_loops=False` and drive the same methods with a fake clock,
  so no test depends on real time except one smoke test of the loops themselves.

### WebSocket protocol (`/api/v1/ws`, models in `api/ws_messages.py`)

- **The first message is `{"type":"auth","token":…}`, within 5 s.** Tokens are never put in
  the URL or a cookie: they stay out of access logs, and a malicious page cannot ride on a
  browser's credentials (cross-site WebSocket hijacking).
- **Client messages:** `subscribe {topics, telemetry_hz}`, `unsubscribe`, `ping`.
- **Server messages:** `welcome`, `snapshot` (one per new topic), `event`, `pong`, `error`,
  `session_ended`.
  - Each carries a per-connection `seq` (starting at 1, no gaps) and a `ts`.
  - The server subscribes before it snapshots, so an event may arrive twice but never zero
    times.
- **Topics:**
  - `fleet.telemetry` is latest-value-wins, coalesced per client to 0.5–10 Hz.
  - `alerts`, `commands` and `control` are reliable: a bounded queue that, on overflow,
    closes the socket with **4429** instead of dropping events.
- **Sessions:** logout, deactivation and password resets close the affected sockets
  immediately (4401). Sessions are also re-checked every 10 s, and a client silent for 30 s
  is closed (4408).
- The connection **never holds a database session**. It opens short ones to authenticate,
  re-check and read snapshots, because there is one connection per database file
  (ADR 0019).
- **AsyncAPI 3.0** is generated from the message models into `docs/api/asyncapi.json`,
  with a drift test. **JSON rather than YAML** avoids a runtime YAML dependency. This
  deviates from the file name planned in ADR 0013; JSON is valid YAML for tools that insist.

## Alternatives considered

- **Asynchronous commands** (202, then results over the WebSocket only): scales to slow
  links, but every client, including scripts, would need a WebSocket to learn outcomes. With
  a 5 s bound, synchronous is simpler and still honest. Revisit if real links need longer
  timeouts (M2).
- **Stateless confirmation tokens without a stored command:** simpler, but there would be no
  audit record of what was put to the operator, and nothing to expire.
- **Heartbeat-only presence (WebSocket):** misses REST-only clients and scripts. Every
  authenticated request counts.
- **Dropping events for slow clients:** a console that silently misses an alert or a control
  change is worse than one that reconnects.

## Consequences

- A command's HTTP request can take up to the command timeout. Consoles show progress
  meanwhile, and bulk commands to 50 aircraft still take one timeout, not 50.
- Confirmation tokens are invalidated by a restart; operators confirm again.
- In-memory presence and verification state are lost on restart. Leases get a new grace
  period, and pending verifications are dropped: their commands stay `acked`. M6 adds resync.
