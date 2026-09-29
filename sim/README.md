# sim

Simulation tools for testing the ground station against real autopilot software (ADR 0017,
ADR 0023). This is not the station's own simulation mode (ADR 0021): that one needs no PX4
and runs anywhere.

| Path | What |
|---|---|
| `sitl/compose.yaml` | Five PX4 SITL instances with the built-in SIH simulator, headless |
| `sitl/fleet.py` | Generates a PX4 SIH fleet of any size (scale runs, ADR 0026) |
| `sitl/annotate.py` | Turns CI results into GitHub annotations (readable without signing in) |
| `linkem.py` | Link emulator: a UDP relay that loses, delays or cuts MAVLink traffic |
| `swarm/` | Simulated `swarm_sar` drones on ROS 2, the bridge and NATS (ADR 0026) |
| `video/` | Mock video: MediaMTX with ffmpeg test streams |

## The PX4 fleet (`sitl/compose.yaml`)

- **Image:** `px4io/px4-sitl:v1.18.0-rc1`, pinned by digest (ADR 0023).
- **Needs:** Linux with Docker Engine and Compose v2. The containers use the host network.

```bash
docker compose -f sim/sitl/compose.yaml up -d
docker compose -f sim/sitl/compose.yaml logs -f px4-0    # one instance's console
docker compose -f sim/sitl/compose.yaml down
```

| Instance | Container | System id | Airframe | Home (lat 47.397742, AMSL 488 m) |
|---|---|---|---|---|
| 0 | `px4-0` | 1 | `sihsim_hex` | lon 8.545594 |
| 1 | `px4-1` | 2 | `sihsim_hex` | 25 m east |
| 2 | `px4-2` | 3 | `sihsim_hex` | 50 m east |
| 3 | `px4-3` | 4 | `sihsim_airplane` | 75 m east |
| 4 | `px4-4` | 5 | `sihsim_quadx` | 100 m east |

Ports, as PX4 sets them for instance *i*:

- **Ground station link:** every instance sends to UDP **14550**. Register each aircraft
  with `mavlink_connection` `udpin://0.0.0.0:14550` and its system id; the fleet service
  tells them apart by system id (ADR 0022).
- **Onboard/API link:** each instance sends to UDP **14540+i**. The tests use it for fault
  injection, and for instance 4's link through the link emulator.

Parameters set for the tests:

- `NAV_DLL_ACT=2` and `COM_DL_LOSS_T=5`: return home after 5 s without a ground station.
- `SYS_FAILURE_EN=1`: allow injected failures.
- `COM_DISARM_PRFLT=-1`: no auto-disarm before takeoff.
- Airplane only: `RWTO_TKOFF=0`, `FW_LAUN_DETCN_ON=0` (launch-style takeoff). The rc1 SIH
  airplane cannot finish a runway takeoff; see ADR 0023.

Change them in `compose.yaml` with `PX4_PARAM_<NAME>` variables.

## The link emulator (`linkem.py`)

It uses only the standard library, and runs on any OS.

```bash
# Instance 4's onboard link, with 20 % loss and 300 ± 100 ms latency:
python sim/linkem.py --listen 14544 --forward 127.0.0.1:24544 --loss 0.2 --latency-ms 300 --jitter-ms 100
# Cut it after 30 s, for 20 s:
python sim/linkem.py --listen 14544 --forward 127.0.0.1:24544 --blackout-after 30 --blackout-for 20
```

Register the aircraft on the forward port (`udpin://0.0.0.0:24544`, system id 5). The
integration tests use its Python API (`LinkEmulator`, `Impairment`).

## Running the SITL integration tests

They run on every push and pull request in the `sitl` workflow. To run them on a Linux host
with Docker:

```bash
docker compose -f sim/sitl/compose.yaml up -d
cd fleet-service && SARGCS_SITL=1 uv run pytest -m sitl tests/integration -v
```

The tests share the one PX4 fleet and run in file order. Restart the fleet (`down`, then
`up -d`) before a second run, because the fixed-wing is left circling.

## Scale fleets (`sitl/fleet.py`)

Generates `compose.yaml` and `fleet.json` for *N* aircraft. It uses the image and
parameters of `sitl/compose.yaml`, puts homes on a 25 m grid (10 per row), and makes every
fifth aircraft an airplane. The `sitl-scale` workflow runs 25, 35 and 50 on GitHub's
standard runner (4 vCPU); the measurements are in `PLAN.md` (M2b).

```bash
python sim/sitl/fleet.py --count 25 --out sim/sitl/generated
docker compose -f sim/sitl/generated/compose.yaml up -d
cd fleet-service && SARGCS_SCALE_FLEET=../sim/sitl/generated/fleet.json uv run pytest -m sitl_scale tests/integration/test_scale.py -v
```

## The swarm (`swarm/`)

`swarm/compose.yaml` runs three containers on the host network, with ROS domain 42:

| Container | What |
|---|---|
| `nats` | The broker (`nats:2.15.0-alpine`, pinned) |
| `swarm-sim` | Three simulated `swarm_sar` drones (see below) |
| `bridge` | `sar_gcs_bridge` (`src/sar_gcs_bridge`) |

The swarm simulation, `swarm/swarm_sim.py`, runs the onboard closed-loop simulation in real
time on the Unix-epoch clock. That is the real `DroneController`, flying simulated vehicles
through a simulated forest, and publishing the real `DroneState` messages. The drones start
airborne and in offboard control, hovering at 4 m. They refuse missions whose altitude is
more than 2 m from that (`ALTITUDE_MISMATCH`). The fleet service runs on the host with
`SARGCS_NATS_URL=nats://127.0.0.1:4222`.

```bash
docker compose -f sim/swarm/compose.yaml up -d --build
cd fleet-service && SARGCS_SWARM=1 uv run pytest -m swarm tests/integration/test_swarm.py -v
```

## Mock video (`video/`)

MediaMTX (`bluenviron/mediamtx:1.21.1-ffmpeg`, pinned) publishes four streams, one per
aircraft. Each is an ffmpeg `testsrc2` pattern, 640×360 at 15 fps in H.264, at
`rtsp://127.0.0.1:8554/aircraft-01` to `-04` (WebRTC on port 8889). The frames carry no
callsign or timestamp overlay yet: the image has no fonts. That overlay comes with the
video latency tests in M5.

```bash
docker compose -f sim/video/compose.yaml up -d
python3 sim/video/check.py --streams 4
```
