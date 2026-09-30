# 0026. Scale runs on the CI runner, and the simulated swarm for the bridge

- Status: Accepted
- Date: 2026-09-30
- Refines: [0017](0017-simulation.md), [0023](0023-sitl-in-ci.md)

## Context

M2b must show two things:

- **Scale:** 50 PX4 SIH aircraft tracked with no stale states.
- **The swarm path:** a swarm of 3 simulated `swarm_sar` drones accepting an area mission
  and a HOLD from the ground station.

**Development host:** Windows with no Docker, so everything runs in CI (ADR 0023). The
GitHub runners free for this public repository have 4 vCPU and 16 GB of memory. Larger
runners need a paid organization plan.

**The swarm:** the onboard `drone_node` needs PX4 over uXRCE-DDS (a `px4_msgs` build) and a
depth camera (Gazebo, M2c).

## Decision

1. **Scale fleets are generated.**
   - `sim/sitl/fleet.py` takes the image and parameters of `sim/sitl/compose.yaml`, places
     homes on a 25 m grid, and makes every fifth aircraft an airplane.
   - The `sitl-scale` workflow ran 25, 35 and 50 aircraft in M2b; it now runs 25.
   - `tests/integration/test_scale.py` measures through the WebSocket, for 60 s:
     - per aircraft: update rate, largest gap;
     - internal latency (driver sample time to console receipt);
     - fleet-service CPU and peak memory, and the host's load;
     - the containers' CPU and memory, sampled by the workflow.
   - It asserts no stale state. It also asserts that a confirmed bulk arm, then disarm,
     takes effect on every aircraft; the answers themselves are recorded, not asserted
     (item 3).
   - Measurements go to annotations. The test step has its own time limit, so a crawling
     runner still reports.
2. **MAVSDK gets its own-sized thread pool.**
   - MAVSDK's asyncio API runs each blocking call (arm, hold…) in the event loop's default
     executor. asyncio's default of 8 threads on 4 cores queued a 25-aircraft bulk arm.
   - With MAVLink links on, the runtime sets a pool of `mavlink_threads` (64). There is a
     regression test.
3. **On an oversubscribed host, late answers are timeouts.**
   - PX4 SITL runs SIH in lockstep at 200 Hz at least; no parameter lowers it. Short of CPU,
     PX4 runs slower than real time, and some answers arrive after MAVSDK's retries.
   - The station reports those as timeouts (ADR 0022: never guessed), and the aircraft may
     still act. So the scale test asserts the end state, and measures the answers.
4. **The swarm in CI is the onboard simulation on ROS 2** (`sim/swarm/swarm_sim.py`).
   - It is `swarm_sar.sim.Simulation`, which runs the real `DroneController` against
     simulated vehicles, forest and radio.
   - Its clock is offset to the Unix epoch, because drones reject ground sequences ahead of
     their clock.
   - It speaks the real `DroneState`, `Mission` and `SwarmCommand` messages, through the
     onboard codec, on the real topics and QoS.
   - It runs with `sar_gcs_bridge` and NATS in `sim/swarm/compose.yaml` (host network, one
     ROS domain, shared IPC for DDS), and uses the onboard code unchanged (ADR 0003).
   - Not `drone_node` with PX4 and a depth camera: that needs M2c's Gazebo.

## Measurements

GitHub `ubuntu-24.04` runner, 4 vCPU, PX4 v1.18.0-rc1 SIH:

| Aircraft | Tracking (60 s) | Rate per aircraft | Largest gap | Latency p50 / p95 / max | Fleet service CPU | Containers' CPU (mean) | Host load (1 min) |
|---|---|---|---|---|---|---|---|
| 5 | no stale state | 5.0 Hz | 0.40 s | 65 / 99 / 197 ms | 0.32 core | — | 1.4 |
| 25 | no stale state | 4.9–5.0 Hz | 0.60 s | 59 / 102 / 263 ms | 0.72 core | 298 % | 19 |
| 25 (2nd run) | no stale state | 4.9–5.0 Hz | 0.61 s | 57 / 102 / 133 ms | 0.75 core | 291 % | 27 |
| 35 | no stale state | 4.8–4.9 Hz | 0.80 s | 56 / 102 / 687 ms | 0.74 core | 304 % | 41 |
| 35 (2nd run) | **2 of 35 stale** | 3.8–4.0 Hz | 2.27 s | 62 / 107 / 481 ms | 0.67 core | 328 % | 56 |
| 50 (1st run) | not measured: the runner became unresponsive until GitHub cancelled the job | | | | | | |
| 50 (2nd run) | **27 of 50 stale** | 2.5–2.8 Hz | 4.25 s | 55 / 128 / 1196 ms | 0.45 core | 335 % | 92 |

**Bulk arm on this host,** after the thread-pool fix:

- The share of answers within the 5 s command timeout varied by run: 19 of 25, 1 of 25,
  31 of 35.
- Every aircraft armed in the end, and disarmed.
- A 4-vCPU runner cannot run 25 or more PX4 SITL instances in real time, and the result
  follows its load. The fleet service itself is not the bottleneck: it used under one
  core at 35 aircraft.
- **Conclusion:** tracking is verified in CI to 25 aircraft, and `sitl-scale` runs 25.
  35 is at the runner's limit, where one run in three went stale. At 50, PX4 runs at about
  half speed and half the fleet goes stale, while the station's own latency and CPU stay
  low. So the limit is the host running PX4, not the station.

## Consequences

- 50 PX4 SIH aircraft need a host with about 8 or more cores. Running them in real time on
  the free runner is not possible, and the first 50-aircraft job made it unresponsive.
  - **The user deferred the 50-aircraft measurement to the field hardware in M5 or M6.**
  - `sitl-scale` runs 25 aircraft; 35 and 50 are measured on the field hardware.
- MAVSDK's per-command timeout (0.5 s × 3 tries) is fixed: the Python v4 binding does not
  expose `mavsdk_set_timeout_s`. On slow radio links at fleet scale this may be tight; it
  is measured again in M5.
- The swarm path is verified end to end in CI:

  | Test | Time |
  |---|---|
  | Tracking | 0.7 s |
  | Mission start | 3.7 s |
  | NATS restart | 2.6 s |

  What is not covered: PX4 under a companion, depth and radio behaviour, and DDS over
  Wi-Fi. They need M2c (Gazebo) and field tests.
