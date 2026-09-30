# Simulation and real-autopilot testing

This page covers three ways to exercise the station without flying, from the lightest to the
most faithful.

| | What flies | Needs | Use for |
|---|---|---|---|
| **Simulation mode** (ADR 0021) | The station's own kinematic mock | Nothing (any OS) | Console work, demos, load tests to 50 aircraft |
| **MAVLink loopback tests** (ADR 0022) | Minimal PX4-like pymavlink vehicles | Nothing (any OS) | The MAVLink driver and real MAVSDK binding, in `pytest` |
| **PX4 SITL** (ADR 0023) | Real PX4 with the SIH simulator | Linux + Docker, or the CI `sitl` workflow | PX4 behaviour: modes, failsafes, fixed-wing, failures |
| **Swarm link tests** (ADR 0024) | A fake bridge over a real nats-server | `nats-server` (any OS) | The swarm driver, NATS reconnects, mission starts, in `pytest` |
| **Swarm in CI** (ADR 0026) | The onboard controller in its simulator, on ROS 2, through `sar_gcs_bridge` | Linux + Docker, or the CI `swarm` workflow | The bridge, the real protocol, swarm tasking |
| **Scale runs** (ADR 0026) | 25 PX4 SIH instances (35 and 50 on the field hardware, M5/M6) | The CI `sitl-scale` workflow | Tracking and bulk commands at fleet size |

Simulation mode is described in [dev-setup.md](dev-setup.md#simulation-mode-live-aircraft-without-hardware).

## The acceptance run (M6)

The brief's final scenario, scripted: a station of its own with 50 simulated aircraft; an
operator tracks 25; a mixed group of 8 passes preflight, launches, and flies a planned area
search; link loss, low battery and GNSS loss are injected; video is viewed; every aircraft
returns and lands; the audit chain verifies and the incident is exported and closed.

```bash
docker compose -f sim/video/compose.yaml up -d        # optional: the mock video relay
cd fleet-service
python -m uv run python scripts/acceptance.py --video --report acceptance.json
```

Each of the 7 steps prints PASS or FAIL with what it saw; it exits 1 if any failed. Without
`--video`, the video step fails as *skipped*. It takes about 5 minutes in real time.

## MAVLink loopback tests

These are part of the normal test run (`tests/test_mavlink_loopback.py`). They start
vehicles on local UDP ports and fly them through the REST API.

```bash
cd fleet-service
python -m uv run pytest tests/test_mavlink_loopback.py tests/test_mavlink_driver.py -v
```

The vehicles in `tests/mavlink_vehicle.py` are test doubles. They teleport, and they know
only what the driver uses, so a passing loopback run says nothing about PX4 compatibility.

## Swarm link tests (NATS)

`tests/test_swarm_link.py` starts a real `nats-server` and a fake bridge
(`tests/nats_support.py`) that follows the wire contract, then drives swarm aircraft through
the REST API. The binary is looked up in `NATS_SERVER_BIN`, then `PATH`, then `.tools/nats/`.
Without it the tests are skipped, unless `SARGCS_REQUIRE_NATS=1`. CI sets that, and so does
`scripts/check.py` when it finds the binary.

```bash
cd fleet-service
python -m uv run pytest tests/test_swarm_link.py tests/test_bridge_contract.py tests/test_swarm_rules.py -v
```

## The swarm in CI

The `swarm` workflow (`.github/workflows/swarm.yml`) has two jobs:

- **Swarm:**
  1. Builds `sim/swarm/Dockerfile`: ROS 2 Jazzy, the onboard packages, the bridge, and the
     swarm simulation.
  2. Runs the bridge's tests and the ament linters inside it.
  3. Starts `sim/swarm/compose.yaml` and runs `tests/integration/test_swarm.py`. The
     tests track three drones, start an area mission, then hold and resume them, and
     restart NATS in between.
- **Mock video:** starts `sim/video/compose.yaml` and checks four H.264 streams.

On a Linux host with Docker, the same runs as:

```bash
docker compose -f sim/swarm/compose.yaml up -d --build
cd fleet-service && SARGCS_SWARM=1 uv run pytest -m swarm tests/integration/test_swarm.py -v
```

Swarm missions must suit the simulated drones: within 1 km of the site (47.397742,
8.545594), at 4 m (±2 m) above home.

## Scale runs

The `sitl-scale` workflow generates fleets with `sim/sitl/fleet.py` and runs
`tests/integration/test_scale.py`:

- 60 s of tracking over the WebSocket: update rate, largest gap and latency per aircraft;
- then a confirmed bulk arm and disarm.

Its annotations carry the measurements and the containers' CPU and memory. `sitl` runs the
same tracking measurement at 5 aircraft.

## PX4 SITL in CI

The `sitl` workflow (`.github/workflows/sitl.yml`) runs on every push to `main`, on pull
requests, and on demand (Actions → sitl → Run workflow). It:

1. starts the five PX4 instances of `sim/sitl/compose.yaml`;
2. runs `pytest -m sitl tests/integration` with `SARGCS_SITL=1`;
3. uploads the `sitl-results` artifact: `junit.xml`, `px4.log` (every PX4 console,
   timestamped) and `containers.txt`.

**When it fails:**

- **"timed out ... waiting for sys N ready":** PX4 did not reach a 3D fix, position and home
  in 120 s. Look in `px4.log` for that instance's startup errors, e.g. a wrong airframe name
  or an image pull failure.
- **Arming failed after retries:** check `px4.log` for `Preflight Fail` lines; PX4 names the
  failing check.
- **A command `unverified`:** PX4 acked it, but telemetry never showed the effect within
  20 s. Compare the mode sequence in `px4.log` with the driver's mode mapping (ADR 0022).
- **Link-loss test:** PX4 must hear no other ground station. The test's app listens only
  on the emulator's port, and the other tests close theirs at teardown. A leftover listener
  on 14550 keeps PX4's link alive.

## PX4 SITL on your own Linux host

```bash
docker compose -f sim/sitl/compose.yaml up -d
cd fleet-service
SARGCS_SITL=1 python -m uv run pytest -m sitl tests/integration -v   # the CI tests
```

To fly SITL aircraft from a running station instead:

1. Start it outside simulation mode:
   `python -m uv run fleet-service`.
2. Register aircraft with `"mavlink_connection": "udpin://0.0.0.0:14550"` and
   `"mavlink_system_id"` 1 to 5.
3. They go *live* once PX4 has booted.

Add impairments with the link emulator (`sim/README.md`). A backup QGroundControl can
listen on another port through `mavlink-router`
(`deploy/mavlink-router/main.conf`, unverified sample).

## Windows

Neither Docker, PX4 nor ROS 2 runs on the reference Windows host. Use the loopback and swarm
link tests (nats-server v2.15.0 for Windows lives in `.tools/nats/`), and read SITL, scale
and swarm results from CI. WSL2 with Docker Desktop would run the compose file too, but its
network mode needs `host.docker.internal` addressing, which is not set up here.
