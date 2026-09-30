# 0035. Preflight failsafe checks and degraded links

- Status: Accepted
- Date: 2026-09-30
- Refines: [0002](0002-scope-safety-and-assumptions.md), [0010](0010-vehicle-drivers.md), [0011](0011-command-authority.md)

## Context

The ground station is not the aircraft's safety net. When the radio link fails, only the
aircraft's own failsafes act (ADR 0002, S1), and they are PX4 parameters that a field crew
can change with any ground station. An aircraft that would do nothing on link loss, or
would terminate its flight on a geofence breach, must not be launched by accident. The
original brief asks M6 to read these parameters, compare them with the incident policy,
and warn about or block takeoff, with an audited supervisor override.

Field radios also degrade gradually: at the edge of its range a link delivers a sample now
and then. Before M6, one fresh sample turned a lost link live again. That re-enabled the
aircraft's commands and cleared its link alert, and a second later the link was lost
again.

## Decision

1. **Arm and takeoff read the failsafe parameters first**:
   - `NAV_DLL_ACT` and `COM_DL_LOSS_T`: link loss;
   - `GF_ACTION`: geofence breach;
   - `COM_LOW_BAT_ACT`, `BAT_CRIT_THR` and `BAT_EMERGEN_THR`: battery;
   - `RTL_RETURN_ALT`: the return altitude;
   - `MIS_TKO_LAND_REQ`: whether GCS-planned missions are accepted.

   The rules are pure functions (`domain/preflight.py`), tested row by row. Each finding
   **blocks** or **warns**:

   | Blocks | Warns |
   |---|---|
   | no link-loss action, or terminate/lockdown on link loss | hold on link loss (until the battery failsafe) |
   | no link-loss delay | link-loss delay above the policy (30 s) |
   | terminate on a geofence breach | a geofence breach only warns, or does nothing |
   | a return above the altitude ceiling | a return below the obstacle clearance (30 m) |
   | an unknown enum value | a critical battery level below the policy (7 %) |
   | **a safety parameter that could not be read** (ADR 0002, S7) | a low battery that only warns; emergency level not below critical |
   | | a landing item required (GCS routes are refused, ADR 0028) |

2. **Blocking findings reject the aircraft** (code `preflight`) unless a supervisor
   overrides: the command then needs confirmation, the summary lists the findings
   (`preflight`), and the dispatch audit event records them (`overridden`). Warnings appear
   with the aircraft in the confirmation. The ground station never changes an aircraft's
   parameters; the crew fixes them with their own tools.
3. **Arm reads the parameters now; takeoff reuses a report younger than 5 minutes** (the arm's).
   Reading takes radio time: over MAVSDK it is one request per parameter, bounded by
   `preflight_timeout_s`, concurrent across aircraft, and never inside a database
   transaction (ADR 0019). `POST /aircraft/{id}/preflight` reads on demand (audited), and
   `GET` returns the last report. The console shows it in the aircraft panel.
4. **Drivers read parameters if they can** (`ParameterReader`): MAVLink over MAVSDK's param
   plugin, and the simulator, whose link-loss failsafe follows its `NAV_DLL_ACT` and
   `COM_DL_LOSS_T`. For an aircraft with two links, the reads go over MAVLink. A swarm-only
   aircraft has no autopilot parameters to read, but it cannot be armed from the GCS
   either (ADR 0003).
5. **Link state has hysteresis** (`domain/links.py`). A link still degrades at once: it is
   stale after 3 s without data and lost after 15 s. Safety never waits. It turns live again
   only after samples have kept arriving, with no gap longer than the stale threshold, for
   `link_recover_after_s` (2 s). Until then fresh data after a loss shows as stale
   (recovering), so only hold, return and land can be sent. First contact is live at once.
6. **Nothing is re-sent automatically.** A command that timed out while the link was down
   stays timed out: the operator decides again with the current state (ADR 0002, S5).

## Alternatives considered

- **Warn only, never block.** Rejected: "the aircraft would do nothing on link loss" is
  the one misconfiguration that turns a lost radio into a flyaway, and a warning in a
  confirmation is easy to hold through.
- **Set the parameters from the GCS.** Rejected: silently changing an aircraft's failsafes
  is itself a safety risk and belongs to the aircraft's maintainer. The GCS reports; the
  crew changes them.
- **Read all parameters (`get_all_params`).** Rejected: hundreds of messages per aircraft
  on a shared field radio, for eight values.
- **Hysteresis in both directions.** Rejected: delaying the transition to stale or lost
  delays alerts and the restriction to safe commands.

## Consequences

- An aircraft with PX4's default `NAV_DLL_ACT = 0` cannot be armed by an operator. The
  SITL fleet sets `NAV_DLL_ACT = 2` (ADR 0023), and the runbooks list the parameters.
- Arming reads eight parameters per aircraft, taking seconds on a slow link. With 50
  aircraft armed together, the reads run concurrently.
- A flapping link keeps the aircraft stale, not live, so it cannot be tasked until the link
  holds. The link alert stays until then.
