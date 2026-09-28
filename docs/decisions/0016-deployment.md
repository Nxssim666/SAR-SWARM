# 0016. Deployment: single-host Docker Compose, offline

- Status: Accepted
- Date: 2026-09-28

## Context

The ground station is a ruggedized laptop or mini-PC in a vehicle or tent, often with no
Internet, set up by responders rather than IT staff. It must start with one command, survive
power loss and be upgradable with a rollback path. Developers use Windows (this host) and Linux.

## Decision

### Target host

- Ubuntu 24.04 LTS on x86-64 (ARM64 images later if needed).
- At least 8 cores, 16–32 GB RAM and an SSD.
- Docker Engine with Compose v2.

### Services

Defined in `deploy/compose.yaml`, each added in its milestone:

| Service | Role | Milestone |
|---|---|---|
| `console` | Caddy: serves the built console, reverse-proxies `/api` (including WebSocket) and WHEP, and terminates TLS with Caddy's internal CA | M0 |
| `fleet-service` | API, domain logic, drivers; data on a volume | M0 |
| `nats` | Event bus for out-of-process adapters | M2 |
| `ros-bridge` | ROS 2 Jazzy bridge to `swarm_sar` (profile `swarm`) | M2 |
| `mavlink-router` | Fans radio MAVLink out to the fleet service and a backup QGroundControl | M2 |
| `mediamtx` | Video relay | M5 |
| `px4-sih-*` / `px4-gz` | Simulation (profiles `sim`, `sim-gz`); never in field deployments | M2 |

### Offline operation

- An **offline bundle**: `docker save` of all images, PMTiles basemaps, the compose file and an
  install script.
- The field host never pulls anything (M6).

### Network

- The only exposed ports are 443 (and 80, which redirects), the WebRTC UDP port for video,
  and the MAVLink UDP ports facing the radio network.
- The fleet service itself is never exposed directly.

### TLS

- Caddy `tls internal` issues a certificate for the station's LAN name or IP.
- Operator devices trust Caddy's root CA once, as a runbook step. Passwords never cross the
  LAN in clear text.

### Time

chrony keeps time, with a GPS receiver (NMEA/PPS) as the offline time source when available
(ADR 0002, A7).

### Resilience

- `restart: unless-stopped`, and the stack starts on boot.
- SQLite durability settings are in ADR 0007.

### Upgrades

- Images are versioned. Before an upgrade the operational database is backed up
  automatically. Migrations are forward-only.
- **Rollback** means the previous image tag plus the pre-upgrade backup.

### Development

- On Windows the fleet service and console run **natively** (uv, Node). PX4 SITL needs Linux:
  WSL2 with Docker Desktop, or a separate Linux host (ADR 0017).

## Alternatives considered

- **k3s / Kubernetes:** orchestration for a single node adds failure modes and skills the
  field team doesn't have.
- **Native systemd services:** fewer layers, but Python, Node and video tool versions drift
  per host. Kept as a fallback for hosts that can't run Docker.
- **Podman:** compatible. The compose file should work with `podman compose`, but it's not
  tested yet.

## Consequences

- Docker is a prerequisite on the field host.
- Compose and image builds can't be verified on the current development host. CI builds
  the images (`.github/workflows/ci.yml`, job `images`).
