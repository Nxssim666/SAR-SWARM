# 0002. Scope, safety boundaries and assumptions

- Status: Accepted
- Date: 2026-09-28

## Context

The system controls real aircraft over populated and remote terrain, is operated under stress,
and handles imagery of people. Its purpose and limits must be unambiguous, and the requirements
leave some questions open that must not block progress.

## Decision

### Scope

Civilian search and rescue only: locating missing persons, surveying search areas, and supporting
incident commanders and ground teams.

**In scope:** waypoint and area-search missions; hold, resume, return-to-launch, land and goto;
telemetry; alerts; video; operator roles; audit; simulation; geofencing; deconfliction.

**Out of scope, permanently:** weapons, targeting, strike, anything military-specific,
offensive payload control, or any function meant to harm people or property.

**Out of scope for now** (each would need its own safety review and ADR): payload release,
even for rescue equipment; flight termination or motor kill from the GCS (this stays with
the safety pilot's RC link); automatic person identification such as face recognition.

**Terminology** in code, UI and docs: *incident, search area, sector, tasking, mission,
point of interest (POI), survivor sighting, ground team, operator, supervisor*. No military
terms. The existing onboard code calls the missing person a "target"; that name is kept
inside `src/swarm_sar` and translated to *survivor sighting* at the bridge (ADR 0003).

### Safety principles

- **S1.** The aircraft's own failsafes are the primary safety layer: PX4 data-link loss,
  RC loss, low battery and geofence actions. The GCS never assumes it will stay reachable.
  In M6 the GCS checks these failsafe parameters before flight and warns if they're unsafe.
- **S2.** The server validates every command: authorization, preconditions and limits.
  The UI is a convenience, not a safety boundary.
- **S3.** Risky or bulk commands need an explicit confirmation that names the aircraft and
  the effect (ADR 0011).
- **S4.** One controlling operator per aircraft. HOLD is available to every operator.
- **S5.** Every command, its outcome, every change of control and every configuration change
  is audited in a tamper-evident log (ADR 0007).
- **S6.** A GCS failure is a non-event for the aircraft: they continue or fail safe on their
  own. A restarted GCS resyncs its state from the aircraft (M6).
- **S7.** No silent fallbacks. A missing value is shown as unknown, never as a default that
  looks like data. For example, an unknown battery level is never shown as 0 % or 100 %.

### Privacy

Video and sightings can show identifiable people, so:

- Access is by role, and video viewing is audited.
- Retention is configurable per data class (telemetry, recordings, sightings, audit), with
  purge jobs (M5/M6).
- Exports are explicit, audited actions.

### Assumptions (revisit if wrong)

| # | Assumption |
|---|---|
| A1 | One ground-station host per incident. Operators connect over its LAN (Wi-Fi or Ethernet). There is no cloud, and linking several stations is out of scope. |
| A2 | Aircraft run PX4 and speak MAVLink 2. Each aircraft on a network has a unique MAVLink system ID (1–254). |
| A3 | Some multicopters run the onboard `swarm_sar` companion (ADR 0003); fixed-wing aircraft do not. |
| A4 | Video reaches the ground network as RTSP, RTP or SRT (H.264/H.265). Onboard encoding is outside this repository. |
| A5 | Survivor detection happens onboard or by a person reviewing video. The GCS records sightings and POIs and does not identify people. |
| A6 | Operators are trained remote pilots, and a safety pilot with RC can take over where regulation requires it. Regulatory approval is the operating organization's responsibility. |
| A7 | The ground station's clock is authoritative (GPS or NTP via chrony). Clients warn when their clock is skewed. |
| A8 | Scale: up to 50 aircraft connected, about 25 managed per operator, 2–6 concurrent console users. |
| A9 | Telemetry arrives at 2–10 Hz per aircraft over lossy radio links. |
| A10 | Metric units, decimal degrees by default (with DDM and MGRS/USNG display options), English UI first. |
| A11 | Consoles run in a current Chromium or Firefox on laptops and tablets with WebGL. |

## Alternatives considered

- **Generic multi-purpose fleet GCS:** rejected. The SAR focus drives the safety and
  privacy defaults and the terminology.

## Consequences

- Feature requests outside the scope list need a new ADR, and the permanent exclusions
  are not negotiable.
- The assumptions are visible, and each milestone report lists any new ones.
