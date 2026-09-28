# swarm_sar — search-and-rescue swarm for PX4 multicopters with depth cameras

Flight software for a companion computer on each drone of a search-and-rescue
swarm. Each drone flies the operator's transit waypoints to a search area,
searches its share of the area, avoids trees and other obstacles with a
forward depth camera, keeps its distance from the other drones, and converges
on a person reported by its onboard detector. There is no central
coordinator: drones share their state and what they have searched over a mesh
radio, and the ground station only sends missions and operator commands.

It runs as two ROS 2 (Jazzy) packages talking to PX4 over uXRCE-DDS, and as a
standalone simulator that executes the exact same decision code against a
simulated forest, depth camera, radio and PX4-like autopilot.

> **Status: pre-flight.** Everything below the "not executed" line in
> [Verification](#verification) is untested on real hardware, PX4 SITL and a
> real ROS 2 installation. Follow the [rollout](#rollout) procedure.

## Contents

* [How it flies](#how-it-flies) · [Safety model](#safety-model) ·
  [Verification](#verification)
* [Hardware and PX4 setup](#hardware-and-px4-setup) · [Build](#build) ·
  [Rollout](#rollout)
* [Missions and operator commands](#missions-and-operator-commands) ·
  [Monitoring](#monitoring)
* [Simulation](#simulation) · [Tests](#tests) · [Configuration](#configuration) ·
  [Limitations](#limitations)

## How it flies

Every drone runs `DroneController` (`swarm_sar/core/controller.py`) at 10 Hz:

1. **Transit.** Fly the mission's waypoints in order (reached within
   `waypoint_radius`, deliberately generous because the whole swarm shares
   them).
2. **Search.** Split the area with the searching peers it can hear
   (Voronoi partition) and, inside its own share, fly to where its detector
   footprint would reveal the most ground not searched recently, per metre of
   travel. What has been searched spreads by gossip: sparse coverage updates
   every second plus a full snapshot every 20 s, merged with an element-wise
   maximum (idempotent, order-independent).
3. **Track.** Detections become a constant-velocity Kalman estimate; peers'
   estimates are fused by covariance intersection. The `num_trackers`
   estimate holders nearest the target hold a ring around it; the rest keep
   searching. A lost track leaves a datum that pulls the search back.
4. **Avoid.** Every velocity passes the local planner last
   (`core/local_planner.py`): it only flies into space the depth camera has
   recently seen empty, within braking distance, only in directions the
   camera can see, and never closer to another drone than it can still stop
   from (`core/avoidance.py`).

Frames: control, perception and avoidance run in **local ENU** (PX4's
estimator origin), so none of it depends on GPS consistency. The mission
(area, coverage grid, target) lives in a shared **mission frame** around the
mission origin; everything that crosses a drone boundary is **WGS84**.
`core/frames.py` is the single place where ENU/NED/FRD/optical conventions are
converted, and every sign is pinned by a test.

Module map (dependencies point downward only; `core` imports neither ROS nor
the simulator):

```
ros/        drone_node, monitor_node, mission_cli, px4 adapter, codec, sensors, visualization
sim/        simulation, vehicle (PX4-like autopilot), depth_camera, world, radio
core/       controller
            ├─ supervisor, local_planner, obstacle_map, depth, pose, avoidance
            ├─ search, coverage, swarm, tracking, mission
            └─ messages, config, frames, geodesy, geometry
```

## Safety model

**Authority.** The pilot arms, takes off and switches PX4 to offboard. The
companion never arms, takes off or enters offboard. While PX4 is not in
offboard, the companion streams a hold at the vehicle's current pose, so
engaging is bumpless. It only ever asks PX4 for a *safer* mode (Hold, Return,
Land) and only while it is in control; a request never outlives the
engagement it was made in.

**Unknown space is never free.** An obstacle-map cell is free only if the
camera saw it free within `map_memory` and did not see an obstacle there in
that time; free rays never erase obstacles. The only exception is unobserved
space within `self_clear_radius` of where the vehicle last *stood still*
(the camera cannot see its own surroundings). The vehicle translates only in
directions inside the camera's horizontal field of view, so it cannot drift
into space nobody looked at. Invalid depth pixels are no evidence; returns
beyond `depth_trusted_range` count as free up to that range only.

**Health.** The supervisor turns input freshness into faults
(`DroneState.faults`, stable bit values):

| Fault | Level | Effect |
|---|---|---|
| `FC_LINK`, `POSE_STALE`, `POSE_INVALID`, `ATTITUDE_STALE` | CRITICAL | No setpoints at all (PX4's offboard-loss failsafe takes over) and a Hold request |
| `DEPTH_STALE`, `DEPTH_BLIND`, `NO_GLOBAL_REFERENCE`, `OUTSIDE_GEOFENCE`, `ALTITUDE_MISMATCH`, `RADIO_SILENT` | DEGRADED | Hold at the stopping point; after `degraded_escalation_time` request PX4 Hold |
| `WAYPOINT_UNREACHABLE` | DEGRADED | Mission HOLD until the operator sends RESUME or a new mission; no escalation |
| `MISSION_REJECTED`, `CONTROL_OVERRUN` | OK | Informational |

`RADIO_SILENT`: a drone that heard peers during the mission and now hears
none has probably lost its own radio and can no longer deconflict, so it
holds (and its peers keep avoiding it where they last heard it for
`lost_peer_memory`). A new mission releases a drone whose peers have left for
good; `hold_on_radio_silence:=false` disables the rule.

**Trust boundaries.** Everything from the radio and the ground station is
decoded defensively (`ros/codec.py`): sizes are checked before anything is
built, every field is validated, and malformed messages are counted and
dropped. Mission and command sequence numbers are milliseconds on the ground
station clock; drones refuse sequences ahead of their own clock, so one forged
maximum cannot lock them out. Missions must lie inside `geofence_radius` of
home and within the altitude limits. Nothing that arrives by radio can bypass
the local planner or the supervisor. **Authentication is not provided by this
code:** without SROS2 anyone on the DDS domain can send missions and commands
or spoof peers (see [SROS2](#sros2-access-control)).

## Verification

Executed while building this release (Python 3.10–3.12, numpy 1.26 and 2.x):

* 487 tests (484 run without ROS; the ament linters and the ROS node test
  skip without ROS): unit tests for every core module, frame and sign
  conventions, the PX4 adapter against PX4 v1.15's verbatim message
  definitions, the codec against strict rosidl-style fakes of this
  repository's and ROS's `.msg` files, failure injection and closed-loop
  forest runs.
* 24 regression tests for bugs found in this code were mutation-checked: the
  fix reverted, the test confirmed to fail.
* Closed-loop simulation, 8 drones, 150 s, 80 trees/ha, seeds 1–8: no tree or
  drone contact, closest tree 0.84–0.95 m (surface; `obstacle_clearance`
  0.8 m), closest drones ≥ 3.00 m (`min_separation` 3 m), 100 % of the area
  searched (90 % after 75–80 s), target found in every run, no autopilot
  failsafe. Denser forest (150 trees/ha, seeds 1–3): same guarantees held.
* ament flake8 and pep257 configurations, mypy, `catkin_pkg` validation of
  both manifests, and `colcon build` of `swarm_sar` with the expected install
  layout.

**Not executed:** the ROS 2 nodes, the launch files, the interfaces package
build, PX4 SITL and any hardware. The package servers for ROS 2 and PX4 were
not reachable from the build environment. `test/test_ros_nodes.py` exercises
the nodes in-process once ROS 2, `px4_msgs` and the interfaces are sourced.

## Hardware and PX4 setup

Assumed platform: a PX4 v1.14 or v1.15 multicopter, a companion computer
running ROS 2 Jazzy, a forward-looking rectified depth camera publishing
`sensor_msgs/Image` (16UC1 millimetres or 32FC1 metres) with `CameraInfo`,
a mesh radio carrying DDS between the drones and the ground station, and a
separate downward search camera with a person detector that publishes
georeferenced `swarm_sar_interfaces/TargetReport` on `target_reports` in the
drone node's namespace (the detector is not part of this repository).

**PX4 parameters** (check each against your airframe):

| Parameter | Setting | Why |
|---|---|---|
| `COM_OF_LOSS_T` | 0.5–1.0 s | How long PX4 waits after the companion stops streaming |
| `COM_OBL_RC_ACT` | Hold (or Return) | What PX4 does when the companion goes silent |
| `RTL_RETURN_ALT` | above the canopy | PX4's Return flies straight home without obstacle avoidance |
| `GF_ACTION`, `GF_MAX_HOR_DIST`, `GF_MAX_VER_DIST` | enabled, ≥ `geofence_radius` | Independent geofence in the autopilot |
| `MAV_SYS_ID` | unique per drone | Must equal the node's `px4_system_id` |
| `UXRCE_DDS_CFG`, `UXRCE_DDS_SYNCT` | companion link, enabled | uXRCE-DDS client and timestamp sync |

**uXRCE-DDS.** Run the agent on the companion (for a serial link:
`MicroXRCEAgent serial --dev /dev/ttyTHS1 -b 921600`). Build `px4_msgs` from
the branch that matches the flight controller's firmware exactly
(`release/1.15` for v1.15). PX4 v1.16 renamed and versioned some topics;
`ros/topics.py` holds the v1.14/v1.15 names. Check
`ros2 topic hz /fmu/out/vehicle_status` shows at least 1 Hz (`fc_timeout` is
2 s).

**Depth camera.** With `realsense2_camera` 4.x the defaults match:
`/camera/camera/depth/image_rect_raw` and `/camera/camera/depth/camera_info`
relative to the node namespace (set `depth_topic`, `camera_info_topic`
otherwise). Run depth at 15 fps; `depth_stride` 4 on 848×480 keeps sample
spacing well below the clearance. Enter the mount in body FRD:
`camera_offset:='[0.12, 0.0, 0.03]'`, `camera_rpy_deg:='[0.0, -5.0, 0.0]'`
(pitch positive up). The camera must sit inside the obstacle band
(`band_above`/`band_below`). Depth frames are paired with poses by their
header stamp, so the driver must stamp them on the companion's clock
(realsense2_camera does by default). At start-up the node warns if the
sample spacing or `self_clear_radius` does not suit the camera.

**Time.** Drones compare stamps from each other, so clocks must agree within
`max_clock_skew` (0.5 s). Use chrony and let it step only at boot
(`makestep 1 3`). A backward step in flight is absorbed; a forward step ages
every input and makes the drone hold.

### SROS2 access control

Enable DDS security (`ROS_SECURITY_ENABLE=true`, `ROS_SECURITY_STRATEGY=Enforce`)
with one enclave per drone and one for the ground station, and grant:

| Enclave | Publish | Subscribe |
|---|---|---|
| ground station (`swarm_sar_mission`, `monitor`) | `/swarm/v2/mission`, `/swarm/v2/command`, `/swarm_sar/*` | `/swarm/v2/status` |
| each drone (`drone`) | `/swarm/v2/status`, `/swarm/v2/coverage`, `fmu/in/*`, `drone/shadow/*` | `/swarm/v2/*`, `fmu/out/*`, camera topics, `target_reports` |

Generate the policy from a running system (`ros2 security generate_policy`),
then remove everything not in this table. Without this, the drones' safety
envelope still holds, but anyone on the DDS domain can command them.

## Build

```bash
mkdir -p ~/ws/src && cd ~/ws/src
git clone -b release/1.15 https://github.com/PX4/px4_msgs.git
cp -r /path/to/swarm_sar_ws/src/* .
cd ~/ws && source /opt/ros/jazzy/setup.bash
rosdep install --from-paths src --ignore-src -y
colcon build --symlink-install && source install/setup.bash
```

## Rollout

`control_enabled` is the kill switch between computing and flying. It
defaults to `false`: the node runs everything but publishes nothing to PX4,
and the setpoints it would send appear on `/drone_<id>/drone/shadow/trajectory_setpoint`.

1. **Bench**, props off: start the agent, the camera and
   `ros2 launch swarm_sar drone.launch.py drone_id:=1`. Move the vehicle by
   hand and check that the shadow setpoints and `DroneState` positions move
   the right way (east is +x in ENU, PX4 reports it as +y in NED).
2. **Shadow flight**, one drone flown manually: send a mission and watch
   phases, faults and shadow setpoints; wave an obstacle in front of the
   camera and check the planner stops.
3. **One drone in control**: `control_enabled:=true max_speed:=1.0`, pilot
   on the sticks, open terrain first. Switching PX4 out of offboard takes
   control back at any time; so does `swarm_sar_mission hold`.
4. **Two drones**, then more, in the same order.

Rollback is the same switch: relaunch with `control_enabled:=false` (or
simply keep PX4 out of offboard). Protocol v2 uses `/swarm/v2/*` topics, so v1
and v2 nodes never exchange misinterpreted messages; do not fly mixed
versions (the ground station's acknowledgement check shows the stragglers).

## Missions and operator commands

```bash
ros2 run swarm_sar swarm_sar_mission example > mission.json   # edit it
ros2 run swarm_sar swarm_sar_mission send mission.json        # serves it until Ctrl-C
ros2 run swarm_sar swarm_sar_mission hold --drones 2,5        # also: resume, rtl, land
```

Positions are `{"latitude": ..., "longitude": ...}` objects (never bare
pairs), unknown keys are rejected, and the file is validated with the same
geometry checks the drones run, so a mission that would be rejected in the
air is rejected at the ground station. `send` reports which drones fly it;
commands exit non-zero unless every addressed drone that is online has
acknowledged them. HOLD and RESUME act in the companion; RTL and LAND are
requests to PX4 and only apply to drones the companion controls.

## Monitoring

`ros2 launch swarm_sar monitor.launch.py metrics_csv:=/tmp/run.csv` publishes
`/swarm_sar/metrics`, RViz2 markers on `/swarm_sar/markers` and the searched
area on `/swarm_sar/coverage` (fixed frame `mission`), and logs a WARN when a
drone degrades, goes silent, or two drones come closer than `min_separation`.
Each drone node logs events (phase changes, faults, mode requests) and a
diagnostics line with message counters every 10 s.

## Simulation

Without ROS (numpy; matplotlib and ffmpeg for rendering):

```bash
pip install -r requirements-standalone.txt
python3 run_standalone.py --num-drones 8 --duration 150 --out demo.mp4 \
    --metrics-csv run.csv --metrics-plot run.png
python3 run_standalone.py --help   # every drone and world parameter is a flag
```

`swarm_sar_demo.mp4`, `metrics.png` and `metrics.csv` in this directory come
from that command (seed 2). The simulated vehicles are acceleration-limited
point masses with a PX4-like autopilot (modes, offboard-loss failsafe, RTL
climb); the depth camera ray-casts the trunks and the ground; the radio has a
range and optional packet loss. Other drones are not rendered in depth
images.

PX4 SITL (not executed here): `make px4_sitl gz_x500_depth` provides a depth
camera in Gazebo; bridge its image and camera info with `ros_gz_bridge`, run
`MicroXRCEAgent udp4 -p 8888`, and launch the drone node with
`use_sim_time:=true` and the bridged topic names. Everything then runs on
`/clock`: launch the monitor with `use_sim_time:=true` too and pass
`--use-sim-time` to `swarm_sar_mission`, otherwise the drones refuse its
wall-clock sequence numbers as coming from the future.

## Tests

```bash
pip install -r requirements-standalone.txt
python3 -m pytest                          # from this directory; ~45 s
python3 -m pytest -m "not slow"            # skip the long closed-loop run
colcon test --packages-select swarm_sar && colcon test-result --verbose
```

## Configuration

Every tunable is declared once, in `swarm_sar/core/config.py`, and generated
into ROS parameters, launch arguments and simulator flags;
`ros2 launch swarm_sar drone.launch.py --show-args` lists all of them with
units. The ones to review per airframe: `max_speed`, `max_accel` (a
deceleration the vehicle can always achieve), `reaction_time`,
`obstacle_clearance`, `camera_offset`, `camera_rpy_deg`,
`depth_trusted_range`, `min_separation`, `geofence_radius`.

## Limitations

* Speed in open terrain is 1–2 m/s: the planner only flies where the camera
  has proven free space within braking distance.
* Thin wires, glass and textureless surfaces are invisible to stereo depth.
* Altitude changes (up to `max_altitude_correction`) are not observed by the
  forward camera; flat terrain relative to home is assumed.
* PX4's Return mode does not avoid obstacles.
* Drones that queue at a shared waypoint wait for each other; a genuine
  deadlock surfaces as `WAYPOINT_UNREACHABLE` after
  `4 × stuck_timeout`.
* Full coverage snapshots grow with the area searched; size the grid to the
  radio's bandwidth.
