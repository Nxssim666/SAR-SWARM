# Operator quick reference

One page, for printing. The console is at `https://<station>/`, in Chrome or Edge.

## Safety first

- **HOLD is always available** to every operator, on every aircraft, on any link state:
  select, then **H** (several aircraft ask for a confirmation).
- **Return** and **Land** work on a degraded link too. Everything else needs a live link.
- The safety pilot's RC always wins. The station never terminates a flight and never
  commands an aircraft because someone disconnected.
- Unknown is shown as **—** (unknown), never as a guess.

## Keys

| Key | Does |
|---|---|
| **H** | Hold the selected aircraft |
| **G** | Pick a goto target on the map |
| **B** / **L** | Box / lasso selection on the map |
| **Ctrl+A** | Select all aircraft |
| **Esc** | Clear the selection and the active tool |
| **?** | All shortcuts |

Arm, takeoff, return, land, goto and mission start have no key: each needs a **held**
confirmation (press and hold the button for 1 s). Enter never confirms.

## Control

- Only the controller of an aircraft (or a supervisor) commands it: **Take control** in the
  aircraft panel. The ring around the aircraft on the map is its controller's colour.
- Someone else controls it: **Request handover**. They accept or decline; unanswered, the
  request expires.
- Leaving: **Release** your aircraft. A disconnected operator's aircraft keep flying their
  task; after a grace period the control is marked orphaned and a supervisor reassigns it
  (**Assign…**).

## Launch

1. Select the aircraft → **Check failsafes** (aircraft panel): *ready*, or fix what it lists.
2. **Arm** → confirm (shows warnings and failed preflight checks; only a supervisor can
   override those, and it is recorded).
3. **Takeoff** → altitude → confirm.

## Search

1. **Search areas**: draw or import (GeoJSON, GPX, KML) inside the incident's operating area.
2. **Missions → New mission**: pattern, lane spacing, altitude; **Plan** for a group.
   Conflicts and terrain issues must be fixed or overridden by a supervisor.
3. **Start mission** → confirm. Progress and coverage show on the map; **Pause** and
   **Resume** at any time.
4. **Points of interest**: **Mark a point**. Survivor sightings from drones come first:
   confirm, dismiss or resolve (never deleted). A sighting is a report to check, never acted
   on by the station.

## Alerts

Critical alerts sound and stay on top until **Acknowledge**d; an unacknowledged warning
turns critical after 60 s. Link alerts clear themselves when the link holds again for 2 s.

| Alert | First action |
|---|---|
| link stale / lost | Watch: the aircraft's own failsafe acts at its `COM_DL_LOSS_T` (return or land). Do not re-send commands; decide from its state when the link is back. |
| battery low / critical, return energy | Return (or land, if critical) |
| GNSS lost | Hold is useless without a position: the aircraft lands itself; clear the area |
| geofence breach | Hold, then goto back inside, or return |
| deconfliction risk | Hold one of the pair |
| command timeout / effect not seen | Check the aircraft's state; send again only if still needed |
| video down | Check the camera and its link; the relay retries |
| disk low | Tell the station lead (runbook: recovery) |

## Command outcomes

✔ done · ✓ acknowledged (effect not yet seen) · → sent · ⏱ no answer · ✕ refused (the
aircraft says why) · ⊘ not sent (the station says why) · ? effect not seen
