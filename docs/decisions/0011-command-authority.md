# 0011. Command authority, arbitration and confirmation

- Status: Accepted
- Date: 2026-09-28

## Context

Several operators share one fleet. Without rules, two people can command the same aircraft
in contradictory ways, or a mis-click can send 25 aircraft home. Operators work under high
cognitive load, and links drop.

## Decision

### Control leases

- Each aircraft has at most one **controlling operator** at a time.
  - An operator takes control of an unassigned aircraft explicitly.
  - A supervisor can assign aircraft to operators.
- Only the controller, or a supervisor, can issue commands to an aircraft, with one exception:
  **HOLD** can be issued by any operator on any aircraft. It is the universally safe "stop and
  wait": hover for a multicopter, loiter for a fixed-wing aircraft.
- **Handover:** the requester asks the current controller, who accepts or declines within
  30 s. On timeout the request fails, and control never transfers silently.
  - A supervisor can **force** a takeover. A reason is required, and it is audited.
- **Disconnects:** if the controller's session drops, the lease is kept for a grace period
  (default 60 s), then marked *orphaned* and supervisors are alerted.
  - An orphaned aircraft keeps its current task.
  - The GCS never issues a command because an operator went away.

### Command pipeline

Each stage is audited:

1. **Receive:** every request carries a client-generated `command_id` (UUID) that works as
   an idempotency key, so a retried request returns the first outcome.
2. **Authorize:** check the permission (ADR 0009), the lease and the driver's capability
   (ADR 0010).
3. **Check preconditions** against live state. Examples:
   - Takeoff: on the ground, GPS fix, battery above the threshold, home set, inside the geofence.
   - Goto: inside the geofence, within the altitude limits.
   - Mission start: a verified uploaded mission.
   - Nothing except HOLD, RTL or LAND for an aircraft whose link is *lost*.
4. **Confirm:** risky commands need confirmation (see below).
5. **Dispatch** to the driver, with per-aircraft rate limiting.
6. **Outcome:** ack, nack (with reason) or timeout. For commands that change mode, the
   **effect is verified** from telemetry (for example, the mode really changed), and an alert
   is raised if it didn't within the timeout.

**Bulk commands** are authorized and executed per aircraft. The response lists the outcome for
every aircraft, and a partial failure is never reported as success.

### Confirmation

- **Commands that need confirmation:** arm, takeoff, mission start, goto beyond a distance
  threshold, geofence changes, any command sent to more than one aircraft, and any supervisor
  override.
- The server answers the first request with **428 Precondition Required** and a
  server-computed summary: the aircraft affected, the action, and warnings such as low battery
  or a stale link. The summary comes with a short-lived **confirmation token** bound to a hash
  of the exact request.
- The client re-sends with the token. A changed request needs a new confirmation.
- The UI shows the server's summary verbatim. Confirmation is a deliberate second action and
  can't be done with the same key or click as the first.

### Emergency actions

- **Hold all**, **Return all** and **Land now** apply to the operator's own aircraft, or to all
  aircraft for a supervisor. They use a single confirmation dialog that lists the count.
- **Flight termination / motor kill is not offered by the GCS** (ADR 0002). It stays with the
  safety pilot.

## Alternatives considered

- **Last writer wins, no leases:** conflicting commands, no clear authority.
- **Hard locks with no override:** a disconnected operator would strand aircraft, so a
  supervisor override is required.
- **Client-side confirmation only** (`confirm: true` flag): any client bug or script bypasses
  it. The server-issued token forces the human-facing summary through the server's view of
  the world.

## Consequences

- Every rule above has a regression test (ADR 0015). The rule list in this ADR is the test
  checklist.
- Commands take one extra round-trip when confirmation is needed, which is acceptable.
