# 0022. MAVLink driver: MAVSDK v4 in-process, shared links, aircraft by system id

- Status: Accepted
- Date: 2026-09-28
- Amends: [0010](0010-vehicle-drivers.md) (replaces "one `mavsdk_server` per aircraft")

## Context

ADR 0010 chose MAVSDK for PX4 aircraft, with one `mavsdk_server` process per aircraft
reached over gRPC on its own port. Three things changed before M2a built it:

- **MAVSDK v4 (Python `mavsdk` 4.0, September 2026)** is a native binding: the C++ library
  runs in-process through ctypes, with an asyncio API. There is no `mavsdk_server` any more.
  It ships wheels for Linux (x86-64, arm64), Windows and macOS. One instance serves many
  systems.
- **A field radio carries the whole fleet on one link,** and so does `mavlink-router`. PX4
  SITL is the same: every instance sends its ground station link to UDP 14550, and instances
  after the tenth share one offboard port (14549). The port does not identify an aircraft;
  its MAVLink system id does.
- One process per aircraft costs memory (ADR 0010 estimated 1.5 GB at 50 aircraft) and makes
  the service a process supervisor.

## Decision

- **Hubs by connection.** `drivers/mavlink.py`:
  - A `MavlinkHub` is one MAVSDK instance on one connection URL (a UDP port, a serial radio).
  - Every aircraft whose registration names that connection is served by the same hub.
  - Connections are normalized, so `udp://:14550` and `udpin://0.0.0.0:14550` share a hub.
  - A hub opens with the first aircraft on its connection and closes, releasing the port,
    with the last one.
  - If the connection cannot be opened (port taken, radio unplugged), it retries every 5 s;
    its aircraft stay *offline*.
- **Aircraft by system id.**
  - A `MavlinkDriver` serves one system id on its hub. It attaches when the hub first hears
    from that id; until then the aircraft is *offline* and commands wait (the pipeline
    times them out).
  - The API therefore requires `mavlink_system_id` with `mavlink_connection` (422
    `system-id-required`). System ids were already unique per station.
- **Telemetry is the aircraft's stream, not ours.**
  - The driver subscribes to position, heading, velocity, battery (the first battery), GNSS,
    flight mode, armed, in air and home. It keeps the newest of each.
  - It emits a canonical sample (ADR 0014) five times a second, **only if something new
    arrived**. Silence on the link then ages the sample and shows as *stale*/*lost* (ADR
    0010), instead of repeating old values.
  - Unknown values stay unknown: NaN becomes `null`. A position without a 3D fix, or older
    than 3 s, is `null`. A GNSS report older than 5 s counts as no fix, because a failed
    receiver may just go quiet while MAVSDK keeps its last report.
  - The station does not raise stream rates: on a shared radio, that budget belongs to the
    link configuration (PX4 `MAV_*` stream settings, the router).
- **Flight modes.**
  - PX4 modes map onto ours. `OFFBOARD` is added for aircraft steered by an onboard computer
    (the swarm companion). Position, altitude, stabilized and acro modes show as `manual`,
    and `READY` as `hold`.
  - PX4 flies a reposition in HOLD (loiter). The driver remembers the target it sent and
    reports `goto` until the aircraft arrives (3 m for multirotors; 120 m for fixed-wing,
    which circles the point) or leaves HOLD.
  - HOLD keeps that target, and RESUME sends it again. RESUME without a paused reposition is
    refused ("nothing to resume").
- **Commands.**

  | Command | MAVSDK call |
  |---|---|
  | arm, disarm | `arm`, `disarm` |
  | takeoff | `set_takeoff_altitude`, then `takeoff` |
  | hold | `hold` |
  | return to launch | `return_to_launch` |
  | land | `land` |
  | goto | `goto_location` |

  - Goto altitudes are relative to home (ADR 0014). MAVLink takes AMSL, so the driver adds
    the home AMSL from the aircraft. Without a home, or without the current altitude when
    none is given, it refuses rather than guess.
  - An aircraft's refusal (`COMMAND_DENIED`, `BUSY`, ...) is a nack, with operator-readable
    text.
  - "No answer" (`TIMEOUT`, `NO_SYSTEM`, `CONNECTION_ERROR`) is **not** a nack. The driver
    keeps waiting, and the pipeline reports a timeout, which is what it was.
- **Logs.** MAVSDK's own log lines go to the `mavsdk` logger (warnings and errors as
  WARNING, the rest as DEBUG), not to stdout.
- **Simulation mode wins.** In simulation mode (ADR 0021), no MAVLink connection is opened.
  `SARGCS_MAVLINK_LINKS=false` also keeps them closed; the unit tests use it so they never
  bind UDP ports.

## Alternatives considered

- **`mavsdk_server` per aircraft (ADR 0010):** heavier, a process to supervise per aircraft,
  and superseded upstream.
- **One hub per aircraft:** would work only while every aircraft has its own port. It fails
  at 11+ SITL instances and on a shared radio.
- **pymavlink with our own state machines:** still the fallback named in ADR 0010. It would
  mean owning mission, geofence and parameter protocol logic that MAVSDK gets right.
- **Raising stream rates from the GCS:** easy for SITL. On a shared 57600 baud radio it
  would starve the other aircraft.

## Consequences

- One process and one port for the fleet; no per-aircraft memory cost beyond MAVSDK's own
  state. To be measured in M5 with 50 SITL aircraft.
- MAVSDK v4 was days old when adopted. The MAVLink behaviour the driver relies on is covered
  by two suites:
  - loopback tests of the real binding against minimal PX4-like vehicles (any OS);
  - PX4 SITL tests in CI (ADR 0023).
- MAVSDK's asyncio wrapper runs blocking calls in the default thread pool. Commands to many
  aircraft at once share it, which is fine at the pipeline's rate limit. Revisit if the M5
  budgets say otherwise.
- The `goto` shown for a PX4 reposition is the driver's inference. If another GCS (e.g. the
  safety pilot's QGroundControl) repositions the aircraft, the mode shows `hold`.
