# Simulation and real-autopilot testing

This page covers three ways to exercise the station without flying, from the lightest to the
most faithful.

| | What flies | Needs | Use for |
|---|---|---|---|
| **Simulation mode** (ADR 0021) | The station's own kinematic mock | Nothing (any OS) | Console work, demos, load tests to 50 aircraft |
| **MAVLink loopback tests** (ADR 0022) | Minimal PX4-like pymavlink vehicles | Nothing (any OS) | The MAVLink driver and real MAVSDK binding, in `pytest` |
| **PX4 SITL** (ADR 0023) | Real PX4 with the SIH simulator | Linux + Docker, or the CI `sitl` workflow | PX4 behaviour: modes, failsafes, fixed-wing, failures |

Simulation mode is described in [dev-setup.md](dev-setup.md#simulation-mode-live-aircraft-without-hardware).

## MAVLink loopback tests

These are part of the normal test run (`tests/test_mavlink_loopback.py`). They start
vehicles on local UDP ports and fly them through the REST API.

```bash
cd fleet-service
python -m uv run pytest tests/test_mavlink_loopback.py tests/test_mavlink_driver.py -v
```

The vehicles in `tests/mavlink_vehicle.py` are test doubles. They teleport, and they know
only what the driver uses, so a passing loopback run says nothing about PX4 compatibility.

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

Neither Docker nor PX4 runs on the reference Windows host. Use the loopback tests, and read
SITL results from CI. WSL2 with Docker Desktop would run the compose file too, but its
network mode needs `host.docker.internal` addressing, which is not set up here.
