# sar_gcs_bridge

The ground station's bridge to the onboard swarm (ADR 0003, ADR 0024). It carries the
`swarm_sar` protocol between ROS 2 (`/swarm/v2/*`) and the fleet service (NATS,
`sar.v1.swarm.<swarm>.*`). It is ground-side code, and the onboard packages are used
unchanged: their codec, message validation, topics, QoS and frame conversions.

| Direction | ROS 2 | NATS |
|---|---|---|
| drone states → station | `/swarm/v2/status` (`DroneState`) | `status` (≤ 5 Hz per drone) |
| station → drones | `/swarm/v2/command` (`SwarmCommand`) | `command` request → `{sequence}` or `{error}` |
| station → drones | `/swarm/v2/mission` (`Mission`) | `mission` request → `{sequence}` or `{error}` |
| — | — | `bridge` heartbeat (1 Hz) |

**What it does:**

- **Converts units.** Headings become degrees true, clockwise from north. The onboard
  "target" estimate becomes a survivor sighting in WGS84, through the origin of the
  mission this bridge sent.
- **Numbers requests.** Each request gets a sequence in milliseconds on the ground clock,
  strictly increasing, and is validated by the onboard message classes.
- **Republishes until the drones catch up.** Commands go out every 0.5 s for up to 10 s;
  missions every 1 s for up to 30 s.

The station acknowledges from the drones' reported sequences. The bridge makes no flight
decision, and drones validate everything again.

## Layout

| Module | What |
|---|---|
| `sar_gcs_bridge/wire.py` | The NATS messages. Standard library only; checked against the fleet service's `swarm_wire` models |
| `sar_gcs_bridge/core.py` | Decisions without ROS or NATS: conversion, sequencing, republishing |
| `sar_gcs_bridge/node.py` | The ROS 2 node (rclpy in a thread) and the NATS client (asyncio) |

## Run

In the ROS 2 Jazzy container (`sim/swarm/Dockerfile`), or in a sourced workspace with
`nats-py` installed:

```bash
ros2 run sar_gcs_bridge bridge_node --ros-args -p nats_url:=nats://127.0.0.1:4222 -p swarm:=default
```

## Tests

- **Local, without ROS:** in the onboard environment, using the onboard message fakes.

  ```bash
  python -m uv run --no-project --with-requirements requirements-standalone.txt python -m pytest -q src/sar_gcs_bridge/test
  ```

- **ament flake8 and pep257:** run in the ROS container (the `swarm` workflow). The same
  rules are checked locally with `ruff check --config src/sar_gcs_bridge/ruff.toml`.
- **End to end:** simulated drones, this bridge, NATS and the fleet service, in the
  `swarm` workflow (`fleet-service/tests/integration/test_swarm.py`).
