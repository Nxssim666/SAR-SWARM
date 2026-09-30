# 0037. The Windows single-machine package

- Status: Accepted
- Date: 2026-09-30
- Refines: [0016](0016-deployment.md)

## Context

The user asked for the whole application as a zip with a Windows executable. The field
stack (ADR 0016) is Linux containers behind a TLS gateway, with a video relay and NATS. Not
everyone who trains on the station, evaluates it or runs a small operation has a Linux host
with Docker. The development host is Windows (CLAUDE.md).

## Decision

1. **One folder, one executable.** PyInstaller builds `SAR-GCS\sar-gcs.exe` (a folder
   build, not a single file: it starts faster and does not unpack into a temporary
   directory each time). It is the `fleet-service` command line: `sar-gcs.exe` serves, and
   `create-admin`, `audit-verify`, `backup` and `purge` work as on Linux. MAVSDK's native
   library, PROJ's data, the migrations and the vendored Swagger UI go in with it.
2. **The fleet service serves the console itself** when there is no gateway. A built
   console is copied into the package (`fleet_service/static/console`), or named with
   `SARGCS_CONSOLE_DIR`. It is served at `/`, with the gateway's security headers, and
   unknown paths return the single-page app. API routes always take precedence, and nothing
   outside the console's directory is served.
3. **The zip** (`SAR-GCS-windows-<commit>.zip`) holds the executable folder, two launchers
   (`start-simulation.bat`: every aircraft simulated; `start-station.bat`: real aircraft,
   listening on the LAN), a README, `VERSION.txt` and **the complete source**
   (`git archive`).
4. **Built and tested on Windows in CI** (`.github/workflows/package.yml`, `windows-2022`)
   on every push to `main` and `claude/**`. It is an artifact of each run, and a release
   asset for `v*` tags. Before the zip is made, the workflow checks the executable:
   - in simulation: create an admin; the console, the API docs and the health page are
     served; register an aircraft, wait for its live link, pass its preflight check, arm it
     with the confirmation flow; `audit-verify` passes;
   - with MAVLink: register an aircraft on a UDP link and check that the hub opens (MAVSDK's
     native library loads on Windows).

## What it is not

The package serves **plain HTTP** and has **no video relay** and **no NATS** (so no onboard
swarms). The field deployment stays the hardened Docker stack
(docs/runbooks/field-deployment.md), which adds TLS, relay access control, container
hardening and the smoke-tested gateway. The package is for training, evaluation,
simulation and small single-laptop deployments, and the README says so.

## Alternatives considered

- **Docker Desktop on Windows.** It needs administrator rights, WSL 2 and a large
  install: not "a zip with an exe".
- **A single-file executable.** It unpacks the whole application into `%TEMP%` on every
  start, which is slow, and some antivirus products flag it.
- **Nuitka.** It compiles to C and is faster at run time, but builds are slow and fragile
  with native extensions (MAVSDK, PROJ). PyInstaller packages the same wheels the service
  is tested with.

## Consequences

- Nobody runs the Windows build before CI does: the workflow is its test, and its smoke
  steps must stay representative.
- A new runtime dependency with native code or data files may need a line in
  `packaging/windows/sar_gcs.spec`. The smoke test catches a missing one at startup.
- `tests/test_dependencies.py` (added with this ADR) fails when the service imports a
  package that only the dev group installs. The packaged executable and the production
  image contain only runtime dependencies.
