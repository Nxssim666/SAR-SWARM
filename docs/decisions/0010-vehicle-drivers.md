# 0010. Vehicle integration: driver interface, MAVSDK, ROS 2 bridge, mock

- Status: Accepted
- Date: 2026-09-28

## Context

The fleet service must track and command three kinds of aircraft: PX4 aircraft over MAVLink,
swarm aircraft over ROS 2 (ADR 0003), and simulated aircraft for tests and development. This
host has no ROS 2 or PX4 SITL (Windows, no Docker). Up to 50 aircraft are connected at once.

## Decision

- Everything above the drivers depends on a **`VehicleDriver` interface**:
  - Declared **capabilities**: arm, takeoff, goto, mission, geofence, hold, RTL, land,
    swarm-mission and so on.
  - A telemetry async stream of canonical `TelemetrySample` values, with explicit units
    and reference frames (ADR 0014).
  - `execute(command)` returning ack, nack (with reason) or timeout.
  - Mission and geofence upload with verification: read back and compare.
- **Drivers:**
  1. **`mock`** (M1): in-process kinematic simulation of multirotor and fixed-wing aircraft
     with battery drain, link loss, GPS loss and geofence breach injection. It is
     deterministic with a seed. It serves unit, API, E2E and load tests to 50+ aircraft, and
     development on Windows. It is not a flight-dynamics simulator.
  2. **`mavsdk`** (M2): MAVSDK-Python, with one `mavsdk_server` process per aircraft on its own
     gRPC port. The connection is configured per aircraft, for example `udp://:14541`.
     - Uses the telemetry, action, mission, geofence, param and failure plugins.
     - Why MAVSDK rather than raw pymavlink: correct, PX4-maintained implementations of the
       mission and geofence protocols with retries, and typed APIs.
  3. **`swarm`** (M2): no driver in-process. The ROS 2 bridge process publishes normalized
     telemetry and consumes commands over the bus (ADR 0008).
- **Link state** is derived in the fleet registry from sample age, not reported by drivers:
  *live*, then *stale* (no sample for more than 3 s), then *lost* (more than 15 s). Thresholds
  are configurable per link type, and each transition raises an alert.
- **Coexistence with QGroundControl:** `mavlink-router` on the ground host fans radio links out
  to the fleet service and to an optional QGroundControl, which the safety crew can use as an
  independent backup GCS. The MAVLink system ID of the GCS is configurable (default 245;
  QGroundControl uses 255).

## Alternatives considered

- **pymavlink with one multiplexed UDP socket:** lighter at 50 aircraft (no per-aircraft
  process), but we would own the mission, geofence and parameter protocol state machines.
  Kept as the **fallback** if the per-aircraft mavsdk_server memory or CPU cost fails the M5
  budget. The interface makes the swap local.
- **MAVROS:** ties the GCS to ROS and was designed for companion-side use.
- **uXRCE-DDS (`px4_msgs`) over the radio link:** DDS over lossy long-range radio performs
  poorly. uXRCE-DDS is meant for the companion-to-flight-controller link.

## Consequences

- One `mavsdk_server` per aircraft costs roughly 15–30 MB each, about 1.5 GB at 50 aircraft.
  This is acceptable on the 16 GB reference host and will be measured in M5.
- The mock driver keeps M1 and M3 fully testable without Linux or Docker. Its fidelity limits
  are documented so nobody mistakes it for SITL.
- Capabilities make the UI and the command pipeline honest about what each aircraft can do.
