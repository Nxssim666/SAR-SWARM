# sim

Simulation tools for testing the ground station against real autopilot software (ADR 0017,
ADR 0023). This is not the station's own simulation mode (ADR 0021): that one needs no PX4
and runs anywhere.

| Path | What |
|---|---|
| `sitl/compose.yaml` | Five PX4 SITL instances with the built-in SIH simulator, headless |
| `linkem.py` | Link emulator: a UDP relay that loses, delays or cuts MAVLink traffic |

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
