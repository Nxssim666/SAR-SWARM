# 0028. Mission planning and GCS-planned missions

- Status: Accepted
- Date: 2026-09-30
- Refines: [0003](0003-onboard-swarm-relationship.md), [0011](0011-command-authority.md), [0014](0014-geospatial-conventions.md), [0022](0022-mavlink-driver-mavsdk-v4.md)

## Context

M4 lets operators search an area with a group of aircraft, not only command them one at a
time. Aircraft with a `swarm_sar` companion already accept an area mission through the
bridge and plan it on board (ADR 0003, ADR 0024). Aircraft with only an autopilot need the
ground station to plan their routes and hand them to PX4. This ADR records how the station
plans, uploads, starts and monitors such missions. Splitting an area among aircraft and
keeping them apart is ADR 0029.

## Decision

1. **Two kinds of area mission.**
   - A *swarm mission* goes to the companions, which plan and fly it on board (unchanged).
   - A *GCS-planned mission* (waypoint route or area search) is planned by the fleet
     service and flown by each aircraft's autopilot as an ordinary PX4 mission.

   Starting and resuming a GCS-planned mission always goes over MAVLink, even for an
   aircraft whose companion is live.
2. **Patterns are pure functions** (`domain/patterns`). They are computed in metres in the
   area's UTM zone and returned in WGS84 with explicit keys (ADR 0014):
   - parallel track (lawnmower) and creeping line;
   - expanding square and sector search from a datum (IAMSAR), bearings in degrees true;
   - contour search along the DEM's contour lines (ADR 0030). Without terrain for the whole
     area, rings offset inwards from its edge are flown instead, and the plan says so.
3. **Lane spacing** comes from the camera footprint (`2·h·tan(HFOV/2)·(1 − overlap)`, height
   above ground) or is set explicitly. It must be 5–2000 m.
4. **Fixed-wing turns.**
   - The turn radius is `v² / (g·tan(bank))`; the bank defaults to 30°.
   - Lanes get run-in and run-out legs of one turn radius.
   - Lanes are flown in an order where no U-turn is tighter than the turn diameter.
   - Turns that cannot be made feasible (too few lanes) are counted and reported; PX4
     widens them itself.
5. **Planning API.** `POST /missions/{id}/plan` computes every aircraft's route:
   - It either answers only (`dry_run`) or saves the plan, which marks the mission
     `planned`.
   - The computation runs in a worker thread, after the request's transaction has ended
     (ADR 0019). If the mission changed meanwhile, saving is refused.
   - A plan with deconfliction or clearance issues is saved as it is and reported. It can
     be started only with a supervisor's override, confirmed and audited.
6. **Starting a GCS-planned mission** (`mission_start`, always confirmed) sends each
   aircraft its own route, in three steps:
   1. **upload** the route;
   2. **read it back** and compare every item (positions to 2·10⁻⁷°, altitudes to 5 cm);
   3. **start** only if they match.

   Nothing flies unverified: a mismatch is a nack with its reason. The aircraft must be in
   the air with a 3D fix and not under its companion's control (offboard). Routes end with
   a return home. The whole start is bounded by `mission_upload_timeout_s` (60 s).
7. **PX4 checks a new mission after acknowledging the upload.** Until that check is done it
   refuses Mission mode ("Switching to Mission is currently not available"). MAVSDK reports
   this refusal as `DENIED`. So the driver retries the start while PX4 answers `DENIED` or
   `BUSY`, every 0.25 s for up to 5 s. After that the refusal is final and becomes a nack
   with its reason. This was found in SITL: both hexacopters' starts were nacked with no
   retry.
8. **Pause and resume.** `mission_pause` pauses a running mission. A HOLD during a mission
   also pauses it, and RESUME continues it where it stopped.
9. **Progress and coverage** (`services/missions`, tick-driven):
   - **Progress** is what the autopilot reports: the current item and the item count.
   - **Coverage** is the track flown in Mission mode, widened by the sweep width, united and
     clipped to the area. It measures what was flown over, not a probability of detection.
   - A mission whose tasks are all finished is completed. Its area is then marked searched
     and a `mission_complete` alert is raised.
   - An aircraft more than 25 m (or its sweep width, if larger) off its leg for 5 s raises
     a `route_deviation` condition alert.
   - Progress is published on the `missions` WebSocket topic.
10. **Onboard avoidance.** A companion's vision-based obstacle avoidance steers only while
    PX4 is in offboard mode, that is, during swarm missions. A goto or a GCS-planned mission
    for an aircraft with a companion is flown by the autopilot, without avoidance. The plan
    and the confirmation both say so.
11. **Fixed-wing landings are not planned.** A route ends with a return, not a landing
    pattern. A PX4 airframe that requires a landing in every mission
    (`MIS_TKO_LAND_REQ = 2`) rejects every GCS route ("Landing waypoint/pattern required").
    Such airplanes must be set to 0 or 1 until the station plans landings. The SITL airplane
    is set to 0. The M6 preflight parameter check will report the setting before takeoff.

## Consequences

- Operators can task autopilot-only aircraft with the same search patterns the swarm uses,
  and see progress and coverage for both.
- A start answers within seconds when PX4 is quick, and at most 5 s later when it refuses
  for good. The operator then sees PX4's refusal, not the station's guess.
- The station depends on PX4's mission protocol and on its feasibility checks. What PX4
  rejects is reported as MAVSDK words it (for example `DENIED`), not with PX4's own sentence;
  reading PX4's status text into the nack is future work.
- Landing patterns for airplanes (runway or approach direction, touchdown point) are future
  work. Until then the landing requirement is a field configuration item.
