# 0023. PX4 SITL in CI: pinned SIH image, integration tests, link emulator

- Status: Accepted; scale runs and the swarm workflow in [0026](0026-scale-runs-and-swarm-simulation.md); Gazebo moved to M2c
- Date: 2026-09-28
- Refines: [0017](0017-simulation.md), [0015](0015-testing-strategy.md)

## Context

ADR 0017 left open where PX4 SITL runs. The development host is Windows without Docker, and
the user chose **CI only** for M2a: SITL runs on GitHub-hosted Ubuntu runners, and the
results are read from CI. Open points were:

- which PX4 build to use;
- which vehicles;
- how to test link loss;
- what stays testable locally.

Facts found in M2a:

- PX4 v1.17.0 is the latest stable release. The official prebuilt headless image,
  `px4io/px4-sitl` (SIH), is published for `v1.18.0-rc1` and main builds, not for v1.17.0.
- PX4 has SIH airframes for a hexacopter (`sihsim_hex`), a quad (`sihsim_quadx`) and an
  airplane (`sihsim_airplane`).
- The image runs `px4` directly, so `-d -i <instance>` starts instance *i* with system id
  *i+1*.
- `PX4_HOME_LAT/LON/ALT` set the start position, and `PX4_PARAM_<NAME>` sets any parameter.

## Decision

- **Image:** `px4io/px4-sitl:v1.18.0-rc1`, **pinned by digest** in `sim/sitl/compose.yaml`.
  - Using the prebuilt image avoids a 10–15 minute PX4 build per run that nobody could
    reproduce on the development host.
  - The ground station depends on MAVLink behaviour, which is the same in 1.17 and 1.18.
  - The pin moves to the 1.18.0 release when it is published, by a reviewed change.
- **Fleet:** five containers on the host network:

  | Instance | System id | Airframe | Home |
  |---|---|---|---|
  | 0–2 | 1–3 | `sihsim_hex` | Zurich, 25 m apart, eastwards |
  | 3 | 4 | `sihsim_airplane` | next position east |
  | 4 | 5 | `sihsim_quadx` | next position east |

  Parameters:
  - `NAV_DLL_ACT=2` (return on ground-station link loss) and `COM_DL_LOSS_T=5`;
  - `SYS_FAILURE_EN=1` (fault injection);
  - `COM_DISARM_PRFLT=-1`.

  The quad stands in for a second multirotor type. SIH has no hexa-specific failure modes
  that matter to the GCS.
- **Integration tests** (`fleet-service/tests/integration`, marker `sitl`, run only with
  `SARGCS_SITL=1`). They drive the real app through REST, with real time and real MAVLink:
  1. all five aircraft tracked on the shared port 14550, told apart by system id, with
     sane telemetry;
  2. a hexacopter full tasking: arm, takeoff, goto, hold, return, landing; each command
     acked and verified from telemetry;
  3. a confirmed bulk takeoff and hold of three hexacopters;
  4. fixed-wing takeoff and return;
  5. link loss through the link emulator: stale then lost alerts. **PX4's own failsafe**
     returns the aircraft, and the link comes back live;
  6. GNSS failure injected with MAVSDK's failure plugin: no fix, position `null`, and the
     `gps_lost` alert.
- **Fixed-wing takeoff is launch-style** (`RWTO_TKOFF=0`, `FW_LAUN_DETCN_ON=0` on the
  airplane). Measured in CI with four variants:

  | Variant | Result |
  |---|---|
  | v1.18.0-rc1 runway takeoff (the default) | Taxis at about 6 m/s and never rotates |
  | The same with `SIH_T_MAX` doubled | The same |
  | **Launch-style** | Takeoff detected; climbs at about 0.2 m/s, 10 m after ~50 s |
  | The newest main build | A real takeoff, then a dive into the ground at the handover to loiter ([PX4 #27344](https://github.com/PX4/PX4-Autopilot/issues/27344)) |

  The station's fixed-wing test checks tracking, the takeoff ack, being airborne and a
  verified return; it asserts nothing about flight performance, which SIH does not model
  faithfully in this version.
- **Link emulator** (`sim/linkem.py`, standard library only): a UDP relay with per-link
  loss, latency, jitter and blackout. It is used in-process by the tests and has a CLI for
  manual runs.
- **Workflow** `.github/workflows/sitl.yml`:
  - Triggers: push to main, pull requests, manual runs.
  - It starts the fleet, runs the tests, and always uploads the JUnit results and the PX4
    container logs as artifacts.
- **Locally**, on any OS, the MAVLink path is tested without PX4:
  - loopback tests run the real MAVSDK v4 binding against minimal PX4-like pymavlink
    vehicles (`tests/mavlink_vehicle.py`), through the whole command pipeline;
  - the link emulator has its own tests.
- **Gazebo (tier 1) moves to M2b,** with camera video and mock video, where it is needed.

## Alternatives considered

- **Build PX4 v1.17.0 in CI:** stable, but slow and fragile to cache. Revisit if 1.18 is
  late or differs in something the station relies on.
- **One port per aircraft:** does not scale past 10 instances (see
  ADR 0022).
- **Gazebo in CI now:** heavy on hosted runners and adds nothing to what M2a tests
  (MAVLink behaviour).

## Consequences

- Flight behaviour is verified only in CI; a local run needs Linux with Docker (see
  `docs/runbooks/simulation.md`). The loopback vehicles are deliberately minimal, and
  passing loopback tests are no evidence of PX4 compatibility.
- The tests share one PX4 fleet and run in file order; each lands its aircraft except the
  fixed-wing, which keeps circling home.
- Hosted runners (4 vCPU) fit about 10 SIH vehicles. The 25 and 50 aircraft targets of ADR
  0017 need a larger runner or host (M5).
