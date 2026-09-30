SAR Fleet Ground Control Station - Windows package
====================================================

Ground control for civilian search-and-rescue drone fleets: the fleet service (API, command
pipeline, alerts, audit trail) with the operator console, in one folder. No installation
and no Internet needed.

Contents
--------
  SAR-GCS\sar-gcs.exe      the fleet service; it also serves the console
  start-simulation.bat     start with simulated aircraft (training, evaluation)
  start-station.bat        start for real aircraft over MAVLink
  source\                  the complete source code of this release
  VERSION.txt              the release (git commit) this package was built from

Quick start (simulation)
------------------------
1. Unzip anywhere (for example C:\SAR-GCS). Windows 10/11, 64-bit.
2. Double-click start-simulation.bat. On the first start it asks for a password for the
   administrator "chief" (at least 10 characters).
3. The console opens in the browser at http://127.0.0.1:8000/ once the station answers
   (use Chrome or Edge). Sign in as "chief". The window's log says "serving the console
   from ..." when it started.
4. Register aircraft: Admin -> Aircraft -> Register an aircraft. In simulation mode each
   registered aircraft is simulated (it spawns at the simulator's origin near Zurich; set
   SARGCS_SIM_ORIGIN_LATITUDE/LONGITUDE to move it) and can be armed, flown and tasked.
5. Stop with Ctrl+C in the console window. Data stays in data-sim\.

Windows may ask to allow network access for sar-gcs.exe: allow it on private networks
(needed for other devices and for MAVLink over UDP).

Troubleshooting
---------------
- "Cannot start: port 8000 ... is not free": another program uses the port, often another
  SAR-GCS window or a fleet-service started from the source code. Close it, or run
  "set SARGCS_PORT=8080" in a command prompt, then start the .bat from that prompt and
  open http://127.0.0.1:8080/.
- The browser shows {"title":"Not Found"...} at http://127.0.0.1:8000/: that is not this
  package's console (an older version, or another server on the port). Close other
  servers and start again.

Command line
------------
  SAR-GCS\sar-gcs.exe                          run the service (http://127.0.0.1:8000)
  SAR-GCS\sar-gcs.exe create-admin --username NAME
  SAR-GCS\sar-gcs.exe audit-verify             check the audit trail
  SAR-GCS\sar-gcs.exe backup --output DIR      consistent copy of the databases
  SAR-GCS\sar-gcs.exe purge --dry-run          what data retention would remove
  SAR-GCS\sar-gcs.exe --help

Settings are environment variables SARGCS_* (see source\fleet-service\src\fleet_service\
config.py), for example SARGCS_PORT=8080 or SARGCS_DATA_DIR=D:\sar-data.

What this package is, and is not
--------------------------------
This single-machine package is for training, evaluation and small deployments. It serves
plain HTTP and has no video relay. The field stack (Linux, Docker) adds TLS, the video
relay with access control, NATS for onboard swarms, and hardened containers; see
source\docs\runbooks\field-deployment.md and source\docs\security-review.md.

Safety: the station never replaces the aircraft's own failsafes or the safety pilot.
Civilian search and rescue only.
