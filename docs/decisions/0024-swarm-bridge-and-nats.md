# 0024. The swarm bridge over NATS: contract, sequencing, acknowledgement

- Status: Accepted
- Date: 2026-09-30
- Refines: [0003](0003-onboard-swarm-relationship.md), [0010](0010-vehicle-drivers.md)
- Supersedes in part: [0008](0008-messaging.md) (which bus carries what)

## Context

M2b connects the fleet service to the onboard swarm (ADR 0003, model B) through a ROS 2
bridge running in its own container. ADR 0008 planned NATS for out-of-process adapters, and
a NATS implementation of the fleet service's `EventBus`, with the bus tests run against both.

Facts about the onboard protocol that shape the design (`src/swarm_sar`, unchanged):

- **Missions have no addressing.** Every drone on the DDS domain adopts a `Mission` whose
  sequence is higher than any it has seen. Commands carry `drone_ids`.
- **There is no acknowledgement message.** A drone reports the last mission and command
  sequence it processed in its `DroneState` (5 Hz).
- **Sequences are milliseconds on the ground clock.** A drone ignores a sequence ahead of
  its own clock by more than `max_clock_skew` (0.5 s), and commands older than 30 s.
- **The command sequence moves for every command.** A drone records a command's sequence
  even when it is addressed to other drones. So "caught up" does not prove that a
  particular command was applied: a command lost on the radio, followed by a later one
  for another drone, is never applied, and never re-applied.
- **`DroneState` lacks some fields.** It has no altitude, battery, GNSS quality or
  autopilot mode. Its heading is in radians, counter-clockwise from east, and a target
  estimate is in the mission frame.

## Decision

1. **The fleet service's internal bus stays in-process.** NATS carries only the boundary
   with out-of-process adapters, which is the bridge today.
   - Consoles get their data from the one fleet-service process. Routing that fan-out
     through a broker would add a failure mode (a broker outage blinds every console) and
     latency, and gain nothing.
   - This replaces ADR 0008's "run the bus tests against both implementations". Instead,
     **the wire contract is tested from both sides.**
2. **Subjects and messages.** For a swarm named `<swarm>` (one per ground station for now,
   `default`), the subjects are `sar.v1.swarm.<swarm>.*`:

   | Subject | Kind | Content |
   |---|---|---|
   | `status` | bridge → station, per drone state, ≤ 5 Hz per drone | Station units (see below) |
   | `command` | request/reply | `{kind, drone_ids}` → `{sequence}` or `{error}` |
   | `mission` | request/reply | Area, waypoints, origin, altitude, grid → `{sequence}` or `{error}` |
   | `bridge` | heartbeat, 1 Hz | Version, drones heard |

   - **Units in `status`:** WGS84 position, heading in degrees true (the onboard
     `core.frames` conversion), fault bits as names, and the onboard "target" estimate as a
     **survivor sighting** in WGS84. The sighting is placed through the origin of the
     mission the bridge sent under that sequence; for any other mission it is `null`,
     never a guess.
   - **Where the contract lives:**
     - the station's models: `fleet_service/drivers/swarm_wire.py`, published as
       `docs/api/swarm-bridge.json` with a drift test;
     - the bridge's builders: `sar_gcs_bridge/wire.py`, standard library only;
     - the check between them: `tests/test_bridge_contract.py`, in both directions.
3. **The bridge sequences and republishes; the station acknowledges.**
   - **Sequencing:** the bridge numbers each request `max(now_ms, last + 1)` on its clock,
     validates it with the onboard message classes, and replies with the sequence.
   - **Republishing:** it republishes a command every 0.5 s until every addressed drone
     has caught up, for at most 10 s. It republishes a mission every 1 s until every drone
     heard flies it, for at most 30 s.
   - **Acknowledgement:** the station's `SwarmDriver` acks a command when *its* drone's
     sequence reaches the one sent. It nacks a mission when the drone reports
     `mission_rejected` more than 1 s after the request.
   - **No answer:** no reply, or no catch-up, is a pipeline timeout, never a guessed
     outcome.
4. **One bulk command is one swarm message.** The drivers of one command (the same
   `command_id`) are batched into one `SwarmCommand`, because of the shared command
   sequence.
   - The residual risk is two separate operator commands, close together, to different
     drones, with the first one lost on the radio. The acknowledgement would then be
     false.
   - Effect verification catches it: HOLD is verified by the drone's phase, and a missing
     phase change becomes `unverified` with an alert. A per-drone acknowledgement in the
     onboard protocol would close it; that is proposed separately (ADR 0003 rule 1).
5. **A swarm mission is swarm-wide.**
   - `mission_start` of a `swarm_area` mission must name every registered swarm aircraft
     (`swarm-mission-partial` otherwise), and exactly the mission's tasks
     (`swarm-mission-tasks`).
   - It is always confirmed (428), and the summary says that every drone on the swarm link
     adopts it.
   - It is sent once per command. The mission frame's origin is the search area's
     centroid; the altitude is the mission's, above each drone's home.
   - On the first ack, the mission and the acked tasks become `active`, and this is
     audited.
   - Starting GCS-planned missions (model A) stays in M4 (`unsupported`).
6. **Samples from a swarm-only aircraft report only what `DroneState` carries.**
   - Known: position, heading, groundspeed, and the swarm block.
   - Unknown (`null`): everything else, including GNSS quality. `TelemetrySample.gps_fix`
     becomes nullable. Unknown GNSS raises no `gps_lost` alert, and confirmations show
     "GNSS quality unknown".
   - The flight mode is `unknown`, since the companion does not report the autopilot's
     mode. The swarm phase is shown instead.

## Consequences

- One more container (NATS) in `deploy/compose.yaml`. The fleet service connects when
  `NATS_URL` is set, retrying forever; nats-py re-subscribes after reconnecting.
- RTL and LAND of a swarm-only aircraft cannot be verified: the effect is a PX4 mode, and
  `DroneState` does not carry it. They end `unverified`. That is honest, and it is why ADR
  0003 asks swarm aircraft to also have a MAVLink link (ADR 0025).
- The NATS tests start a real `nats-server`: in CI it is a pinned, checksum-verified
  download, and on the development host it lives in `.tools/nats/`. With
  `SARGCS_REQUIRE_NATS=1` (CI, and `check.py` when the binary is found), a missing server
  fails the tests instead of skipping them.
- The rest of ADR 0008 (delivery classes, subject naming) stands.
