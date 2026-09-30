# Field deployment

Set up a ground station for a search: one Linux laptop or mini-PC with Docker, the telemetry
radio, a WLAN or switch for the operator devices. No Internet is needed at any point in the
field; prepare the offline bundle beforehand (step 1).

## 0. The station hardware

| Item | Minimum | Why |
|---|---|---|
| CPU / RAM | 4 cores, 8 GB (8 cores for 50 aircraft with video) | Measured: 0.23 core and 143 MB for the fleet service at 50 simulated aircraft (M5) |
| Disk | 64 GB SSD, **encrypted** (LUKS) | Telemetry history is 1 sample/s per aircraft (an estimated 200 bytes each, about 36 MB per hour for 50 aircraft), kept 30 days; the disk guard alerts below 2 GB free |
| OS | Ubuntu 24.04 LTS (or any Linux with Docker Engine 27+ and Compose v2) | |
| Network | One LAN (WLAN AP or switch) for operator devices; a fixed IP for the station | Consoles, video (WebRTC over UDP 8189) |
| Radio | Telemetry radio with **AES encryption and a unique network ID** | MAVLink itself is unauthenticated (security review) |
| Power | UPS or vehicle power with 30 min hold-up | A clean shutdown keeps the databases consistent (they survive a crash too, WAL) |

## 1. Before leaving: the offline bundle (with Internet)

On any Linux host with Docker, in a checkout of the release to deploy:

```bash
node fleet-console/scripts/fetch-basemap.mjs --region <id>     # basemap (see basemap.md)
python -m uv run scripts/fetch_region.py --region <id>          # terrain and imagery
deploy/bundle.sh --output /media/usb/sar-gcs-bundle             # images, config, data, checksums
```

Copy the bundle to the station (or carry it on the USB stick). It holds everything:
images, configuration, region data, these runbooks and `SHA256SUMS`.

## 2. Install (at the station, no Internet)

```bash
cd /path/to/sar-gcs-bundle
sudo ./deploy/install.sh
```

It verifies the checksums, loads the images, starts the stack and installs the region
data. First install only:

```bash
cd /path/to/sar-gcs-bundle
docker compose -f deploy/compose.yaml exec fleet-service fleet-service create-admin --username chief
```

Settings go in `deploy/.env` next to `compose.yaml` (then `docker compose -f deploy/compose.yaml up -d`):

```ini
SARGCS_STATION_NAME=gcs-rescue-1
SARGCS_SITE_ADDRESS=10.0.0.2          # the station's LAN address or name, used for TLS and WebRTC
# SARGCS_VIDEO_PUBLISH_USER=camera    # only if cameras push video (RTSP/SRT) into the relay
# SARGCS_VIDEO_PUBLISH_PASSWORD=...
```

## 3. Host firewall

Open only what the field needs; everything else stays closed (security review):

```bash
sudo ufw default deny incoming
sudo ufw allow 80,443/tcp        # consoles (HTTP redirects to HTTPS)
sudo ufw allow 8189/udp          # WebRTC video to consoles
sudo ufw allow 14550/udp         # MAVLink, if the radio is on another host; else skip
sudo ufw allow 8554/tcp          # only if cameras push RTSP
sudo ufw allow 8890/udp          # only if cameras push SRT
sudo ufw enable
```

## 4. The telemetry radio

Install `mavlink-router` on the host and use `deploy/mavlink-router/main.conf` as a template
(radio device, baud rate). It forwards the radio to the fleet service on UDP 14550 and offers
a port to a backup QGroundControl for the safety pilot. Register each aircraft with
`mavlink_connection` `udpin://0.0.0.0:14550` and its MAVLink system id (unique per aircraft).

## 5. Each aircraft, before the first flight of the day

- [ ] Unique MAVLink system id; the radio's AES key and network ID match the station's.
- [ ] Failsafe parameters, as the station's preflight check expects (ADR 0035). In QGroundControl:
  `NAV_DLL_ACT` = 2 (return) or 3 (land); `COM_DL_LOSS_T` ≤ 30 s; `GF_ACTION` = 2, 3 or 5;
  `COM_LOW_BAT_ACT` = 2 or 3; `BAT_CRIT_THR` ≥ 0.07; `RTL_RETURN_ALT` between 30 m and the
  ceiling (120 m by default). Airplanes: `MIS_TKO_LAND_REQ` 0 or 1.
- [ ] In the console: select it, **Check failsafes** (aircraft panel). Ready, or fix what it lists.
- [ ] Geofence and home position set; the safety pilot has RC and can take over.

## 6. Operator devices

- Trust the station's certificate once per device ([certificates.md](certificates.md)).
- Open `https://<station>/` in Chrome or Edge (they decode the aircraft's H.264 video).
- Each operator signs in with their own account (supervisors create them: **Admin**).

## 7. Check the station

```bash
docker compose -f deploy/compose.yaml ps           # all running (healthy)
docker compose -f deploy/compose.yaml exec fleet-service fleet-service audit-verify
```

In a console: the map shows the region, the aircraft list shows the registered aircraft with
live links, **Video** plays each camera, and **Admin → Audit → Verify chain** is intact.

Then start the incident ([incident.md](incident.md)).
