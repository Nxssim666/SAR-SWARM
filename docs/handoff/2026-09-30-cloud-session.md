# Handoff: cloud session of 2026-09-30

For the agent in the local session. It covers everything a Claude Code cloud session changed
after the local session stopped at `dc6d5d8` (M4 backend, branch `exp/m4`).

## Where the work is

- **Branch:** `claude/dazzling-mayer-crl33a` on GitHub (`Nxssim666/SAR-SWARM`). It builds on
  `dc6d5d8` (= `origin/exp/m4`). It is **not merged** into `main`, which is still at
  `6420401` (M2a), and there is no PR.
- **To pick it up:**
  - `git fetch origin && git switch -c claude/dazzling-mayer-crl33a origin/claude/dazzling-mayer-crl33a`,
    or merge it into your branch.
  - Run `python -m uv --directory fleet-service sync` and `npm ci` in `fleet-console/`.
    New dependencies were added and the lock files are committed.
- **Size:** 13 commits `dc6d5d8..HEAD`, about 190 files, +18.5k / -0.5k lines. `PLAN.md` and
  the CLAUDE.md status table are up to date: **M4, M5 and M6 are all Done.**

## Decisions the user made in the cloud session

- **Finish every milestone** (M4, M5, M6), not only M4.
- **Gazebo is dropped entirely** from the plan (ADR 0033). The acceptance uses PX4 SIH and
  mock video. Onboard avoidance during ground commands is documented, not verified.
- **Kept defaults:**
  - regions: Zurich (the simulator's site) and Kramatorsk;
  - no fixed-wing landing patterns (the station does not plan landings; ADR 0028).
- **A Windows package was requested:** a zip with the files and a Windows exe (ADR 0037).
- **The satellite map (Sentinel-2) must be visible** in the console and in the package. The
  user reported it missing, and it is fixed in the last commit.

## Commits, oldest first

1. `53c40c5` **M4: start missions once PX4 has checked them; SITL fixes; ADRs 0028-0031**
   - The MAVLink driver retries a mission start while PX4 answers DENIED or BUSY: every
     0.25 s, for up to 5 s. PX4 refuses Mission mode until it has checked a new upload.
   - The SITL airplane uses `MIS_TKO_LAND_REQ=0`.
   - The mixed lawnmower SITL test is split: three multirotors must complete, and the
     airplane only has to be accepted and started.
   - ADRs 0028 (mission planning), 0029 (split, deconfliction, bulk goto), 0030 (offline
     region data), 0031 (M4 alerts, POIs, survivor sightings).
2. `e5ebe36` M4: records the SITL verification in PLAN (sitl 8/8).
3. `84c7775` **M4 console: planning and tasking; Gazebo dropped (ADR 0032, 0033)**
   - Incident picker, and side-pane tabs Fleet, Missions and Points.
   - Map overlays for search areas, planned routes, coverage and POIs, plus drawing tools.
   - Search-area import from GeoJSON, KML and GPX.
   - Waypoint editor, and a plan form with a dry-run deconfliction preview.
   - Start, pause and resume through the 428 confirmation flow.
   - POI panel, bulk goto confirmation, and audible alert cues.
   - New E2E spec: `e2e/missions.spec.ts`.
4. `84a8d5d` **M4 done**
   - E2E: plan to completion (coverage ≥ 80 %).
   - New SITL tests: a geofence breach alert, and battery drain where PX4 returns on its own.
5. `4e1551a` **M5: video, multi-operator, audit viewer, retention, load suite** (ADR 0034)
   - MediaMTX relay reconciliation and health, with a `video_down` alert.
   - A WHEP player grid with an LL-HLS fallback; every view is audited.
   - The mock relay has a burned-in overlay and a VP9 test stream.
   - User admin, presence, handover and supervisor assignment.
   - Audit viewer with chain verify and CSV/JSONL export.
   - Retention purge every 6 h (never the audit trail).
   - Load suite with budgets at 25 and 50 aircraft and 6 consoles (`load.yml`, nightly).
   - Link hysteresis: a degraded link turns live only after 2 s of data.
   - Fix: the simulated airplane now follows each leg instead of cutting lanes.
6. `a5215a4` **M6: preflight failsafe checks and other station safeguards** (ADR 0035)
   - Arm and takeoff read the aircraft's failsafe parameters and check them against station
     policy. A blocking finding needs a supervisor override, which is confirmed and audited.
   - Commands a restart interrupted are closed as timeout/unverified ("interrupted"), never
     re-sent.
   - The audit chain head is exported to a file every 5 min, so truncation is detectable.
   - Disk guard: a `disk_low` alert, and telemetry history pauses at critical.
   - New `fleet-service backup` command.
   - Swagger UI is vendored (no CDN).
   - `GET /incidents/{id}/export`: a zip with a SHA-256 manifest.
   - Fix: `video_down` alerts never cleared.
7. `f20cfd4` **M6: relay access control, hardening, runbooks, Windows package** (ADR 0036, 0037)
   - Viewing tickets (HMAC, per stream, 4 h), and MediaMTX asks the service to authorize.
   - The gateway refuses `/api/v1/internal/*`.
   - Containers are read-only and non-root, with no capabilities and with limits.
   - `deploy/smoke.sh` runs in CI.
   - `docs/security-review.md` and runbooks: field-deployment, certificates, basemap,
     incident, operator-card, recovery, upgrade.
   - `deploy/bundle.sh` and `install.sh` for the offline bundle.
   - Console: geofences, the aircraft registry, closing an incident.
   - Windows package: the service serves the built console (`console_dir`), with a
     PyInstaller spec, launchers and `.github/workflows/package.yml`.
   - Fixes:
     - `httpx` moved from a dev dependency to a runtime dependency, guarded by
       `test_dependencies.py`;
     - the relay's LL-HLS redirect escaped the gateway prefix.
   - CI now also runs on `claude/**` branches.
8. `7719203` **M6: acceptance 7/7, M6 done**
   - `scripts/acceptance.py`: 50 simulated aircraft and the mock video, 7 steps.
9. `5ab806f` **Windows package: refuse a busy port, open the browser only when up**
   - The user saw a 404 JSON at `127.0.0.1:8000`. Another server was on the port, and on
     Windows uvicorn's `SO_REUSEADDR` let a second bind succeed silently.
   - `cli.serve` now checks the port first with `port_problem()`.
   - `SARGCS_OPEN_BROWSER` opens the browser only once `/api/v1/health` answers.
   - The log says where the console is served from.
   - The package workflow smoke-tests the zip after unpacking it elsewhere.
10. `3fd542c` Package workflow: the port-in-use smoke step ends with `exit 0`.
11. `61bcd3f` **Launchers take the next free port** (up to 20 more) when 8000 is busy, and say
    so. Started by hand, `sar-gcs.exe` still refuses a busy port.
12. `7a9d0fc` **Console satellite view, and region data in the package**
    - `fleet-console/src/map/basemap.ts` reads `/basemap/index.json`, the file the fetch
      scripts write. It used to read a stale `manifest.json`, so imagery never showed.
    - Per region it adds the vector basemap and the Sentinel-2 image as a raster layer,
      hidden by default, drawn above the fills and below the labels.
    - The 🛰/🗺 button next to the coordinate readout switches the view. The choice is stored
      in `localStorage` `sargcs.satellite`, and the imagery credit is shown in the map
      attribution.
    - Tests: `src/map/basemap.test.ts` and `e2e/satellite.spec.ts`. The E2E test uses a
      synthetic magenta image and checks screen pixels.
    - `package.yml` has a new `region` job (Linux, cached) that fetches every region's
      basemap, imagery and terrain. The Windows job packages them, fails if the imagery is
      missing, and ships `terrain\`. The launchers set `SARGCS_TERRAIN_DIR`.
13. This file.

## New settings (`SARGCS_*`, `config.py`)

| Area | Settings |
|---|---|
| Links and preflight | `link_recover_after_s`, `preflight_max_link_loss_s`, `preflight_min_return_altitude_m`, `preflight_min_critical_battery_pct`, `preflight_timeout_s`, `preflight_max_age_s` |
| Video | `mediamtx_api_url`, `video_base_path`, `video_poll_interval_s`, `video_ticket_ttl_s`, `video_publish_user`, `video_publish_password` |
| Retention and disk | `telemetry_retention_days`, `alert_retention_days`, `command_retention_days`, `disk_warn_free_mb`, `disk_critical_free_mb` |
| Audit and serving | `audit_head_file`, `audit_head_interval_s`, `console_dir`, `open_browser` |

New CLI commands: `purge` and `backup`. There are no new database migrations after `0003`.

## Verification

- **Local results in the cloud container**, recorded in PLAN:
  - fleet-service: 676 passed at `a5215a4`, and the later CLI tests pass (`test_cli.py`, 9);
  - console: 105 Vitest tests;
  - E2E: 14/14 with the mock relay, and the new satellite spec also passes;
  - acceptance: 7/7.
- **GitHub, commit `7a9d0fc`:**
  - `package`: green. The `region` job fetched real Sentinel-2 imagery:
    - Zurich: `S2B_32TMT_20260724` (24 July 2026);
    - Kramatorsk: `S2C_37UCQ_20260818` (18 August 2026).
  - `swarm`: green.
  - `ci`: green. That includes the E2E suite against the real Zurich basemap, and the
    satellite spec.
  - `sitl`: see the addendum at the end.
- **The package** is the artifact `SAR-GCS-windows-<sha>` of the `package` run (30 days).
  Pushing a `v*` tag also attaches it to a release.
- **Not verified:** the real Sentinel-2 image drawn in a browser. This container's proxy
  blocks the imagery sources, so only the synthetic image was tested. Check it by eye in the
  package, or locally after `node fleet-console/scripts/fetch-basemap.mjs` and
  `uv run scripts/fetch_region.py`.

## Known gaps and open items

- **50 PX4 SIH aircraft remain unmeasured.** They need the field hardware (the user's
  M2b decision).
- **The planner** leaves transit conflicts of dense mixed groups to a supervisor's audited
  override.
- **The Windows package** serves plain HTTP, with no video relay and no NATS. The Docker
  stack is the field deployment.
- **The offline bundle** (`bundle.sh`, `install.sh`) has not been run end to end.
- **MAVLink is unsigned**, and the databases are not encrypted at rest. See
  `docs/security-review.md`.
- **The `sitl` workflow failed once, on `61bcd3f`**, a commit that didn't touch flight code:
  - The previous and next runs passed on the same flight code.
  - In `test_a_hexacopter_flies_a_full_tasking`, HX-1 stayed in HOLD at 20 m after the RTL,
    and its telemetry timestamp stopped advancing while the link stayed "live".
  - The next three tests then failed with `already-armed`, because the aircraft was never
    disarmed.
  - This looks intermittent, but the root cause isn't known yet: a stalled MAVSDK
    subscription, or PX4 SIH. Worth investigating. The sitl tests could also disarm or
    reset between tests, so one failure does not cascade.
- **Region data is gitignored.** Fetch it locally with the pmtiles CLI in `.tools/pmtiles/`
  and `scripts/fetch_region.py`. The package gets it from the `region` job.

## Tips from the cloud session

- **The service's own port check:** uvicorn on Windows silently double-binds, so keep
  `port_problem()` in `cli.serve`.
- **Windows user symptoms:**

  | Symptom | Meaning |
  |---|---|
  | `{"title":"Not Found"}` at `/` | Another server is on the port, or an old build |
  | "Cannot start: port ..." | The exe was started by hand, not from a launcher |
  | "using port 8001 instead" | Normal launcher fallback |

- **E2E in a container** needs `executablePath: '/opt/pw-browsers/chromium'` through a
  temporary Playwright config. On the Windows dev host the normal `npm run e2e` applies.

## Addendum: `sitl` on `7a9d0fc`

This run was still going when this file was written. Check the `sitl` workflow run for
`7a9d0fc` on GitHub. If it failed like the `61bcd3f` run did, see "Known gaps" above.
