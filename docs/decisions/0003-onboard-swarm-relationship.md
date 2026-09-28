# 0003. Relationship to the onboard swarm_sar software

- Status: Accepted
- Date: 2026-09-28

## Context

Before this work the repository held `src/swarm_sar` and `src/swarm_sar_interfaces`. They are
ROS 2 Jazzy companion-computer software (MIT, about 8k lines, 487 tests) for PX4 multicopters
with depth cameras. Each drone flies transit waypoints and then searches its share of an area
without a central coordinator. It avoids obstacles with its depth camera and converges on a
reported person. The ground station talks to it over three topics:

- `/swarm/v2/mission`: an area polygon plus waypoints.
- `/swarm/v2/command`: HOLD, RESUME, RETURN_TO_LAUNCH or LAND for a set of drone IDs.
- `/swarm/v2/status`: a `DroneState` broadcast carrying position, phase, health, fault bits
  and acknowledged sequence numbers.

Today the only ground tools are a command-line tool (`swarm_sar_mission`) and an RViz monitor.

The new GCS also has to fly fixed-wing aircraft and multicopters that have no companion computer.

## Decision

The GCS supports **two control models** through one aircraft abstraction:

| | Model A: direct | Model B: delegated (swarm) |
|---|---|---|
| Aircraft | Any PX4 (fixed-wing, hexa, quad) | Multicopters running `swarm_sar` |
| Link | MAVLink via MAVSDK (ADR 0010) | ROS 2 `/swarm/v2/*` via a bridge process |
| Who plans the path | The GCS generates waypoints (search patterns) and uploads a PX4 mission | The swarm partitions and searches the area onboard |
| GCS commands | Arm, takeoff, hold, resume, RTL, land, goto, mission upload/start/pause, geofence | HOLD, RESUME, RTL, LAND, plus mission (area) assignment |
| Deconfliction | By the GCS, per aircraft (ADR 0011, M4) | Inside the swarm by the swarm; the GCS deconflicts the swarm as a block (area plus altitude band) |

Rules:

1. **The onboard code stays as is.** Ground-system work does not modify `src/swarm_sar` or
   `src/swarm_sar_interfaces`. If a change is ever needed, it is proposed separately, with
   tests, in the onboard package's own style.
2. **One definition of the wire format.** The M2 bridge (`src/sar_gcs_bridge`, ament_python)
   reuses `swarm_sar.ros.codec.Codec` (`decode_status`, `encode_mission`, `encode_command`)
   and the validation in `swarm_sar.core.messages`, instead of redefining the messages.
3. **The bridge respects the onboard protocol's constraints:**
   - Sequence numbers are milliseconds on the ground clock, and drones reject sequences
     that are ahead of their own clock.
   - Missions are republished, since there are no acknowledgements beyond `DroneState`.
   - An area has at most 256 vertices, and a mission at most 64 waypoints.
   - The mission extent is at most 5 km, and it must lie inside each drone's geofence radius.
   - Acknowledgement means `DroneState.mission_sequence` or `DroneState.command_sequence`
     has caught up.
4. **Swarm aircraft should also have a MAVLink telemetry link.** `DroneState` has no battery,
   altitude, GPS quality or flight mode. In the aircraft registry an aircraft can have both
   links: swarm `drone_id` and MAVLink system ID are mapped explicitly, never assumed equal.
   The fleet service merges the two telemetry sources into one aircraft state.
5. **Capabilities decide what is allowed.** While a companion holds offboard control, the GCS
   must not upload PX4 missions or send goto commands to that aircraft. Each driver declares
   capabilities, and the command pipeline enforces them (ADR 0011).
6. **Frame conversion.** `DroneState.heading` is in radians, counter-clockwise from east.
   The GCS convention is degrees true, clockwise from north (ADR 0014). The bridge converts,
   and a test pins each sign, following the onboard `core/frames.py` practice.
7. Onboard "target" terminology maps to *survivor sighting* in the GCS.

## Alternatives considered

- **Replace the onboard swarm with GCS-planned missions for every aircraft:** this discards
  a tested decentralized search, and it would lose the companion's obstacle avoidance, which
  a waypoint mission can't provide under canopy.
- **Only support the swarm protocol:** doesn't cover fixed-wing aircraft or plain PX4 hexas.
- **Rewrite the codec in the GCS:** creates two definitions of one wire format that will
  drift apart.

## Consequences

- The bridge needs a ROS 2 Jazzy runtime, so it runs in its own container. The fleet service
  stays free of ROS (ADR 0008, ADR 0016).
- Operators see swarm aircraft with coarser control, only HOLD, RESUME, RTL and LAND. The UI
  must make that difference visible.
- The existing onboard tests stay part of `scripts/check.py` and CI.
