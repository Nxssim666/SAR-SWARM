# 0029. Area split, deconfliction and bulk goto

- Status: Accepted
- Date: 2026-09-30
- Refines: [0002](0002-scope-safety-and-assumptions.md), [0011](0011-command-authority.md), [0028](0028-mission-planning-and-gcs-missions.md)

## Context

Several aircraft searching one area, or sent to one datum, must not meet. The swarm
deconflicts itself on board (ADR 0003). For GCS-planned missions and ground commands, the
station must plan the separation and check it. In M3 a goto took exactly one aircraft,
because one target for several would have converged them on it.

## Decision

1. **Splitting an area** (`domain/split`):
   - The area is cut into strips across the sweep direction, one per aircraft.
   - Each strip's area is in proportion to its aircraft's cruise speed × endurance, which
     is what the aircraft can search.
   - Strips keep the full lane length, so lanes stay long and turns few, and strips never
     overlap.
   - Strips are assigned in the order of the aircraft's current positions across the
     sweep, so transits do not cross.
2. **Altitude layers** (`domain/deconfliction`):
   - Multirotors fly the search altitude and a few layers above it. Layers are
     `layer_spacing_m` apart (default 15 m, 3 layers), assigned round-robin in strip order,
     so neighbouring strips differ.
   - Airplanes fly a band at least `airframe_band_m` (30 m) above the highest multirotor
     layer.
   - Layers are consistent in AMSL when the homes' altitudes are known. Otherwise they are
     relative to each home, and the plan says so.
3. **Terrain clearance.**
   - With terrain (ADR 0030), every waypoint must be 30 m to 120 m above the ground
     (`min_terrain_clearance_m`, `max_height_agl_m`).
   - A waypoint over unknown terrain is reported as unchecked.
   - Without terrain, the altitude above home must stay under the station's limit.
4. **4D check.**
   - Each flight is modelled step by step:
     1. hold where it is until its start delay;
     2. climb or descend there to its layer (2.5 m/s);
     3. fly the route at its speed;
     4. for missions, return home on its layer.
   - Two flights conflict where they are closer than 50 m horizontally **and** 15 m
     vertically while at least one of them moves.
   - Between samples the aircraft move in straight lines, so the closest approach is
     computed exactly per interval, not only at the samples.
   - Aircraft already that close before anyone moves (at a launch site) are the present
     situation, which live alerts watch. For them, the plan must not bring them more than
     10 m closer.
5. **Sequencing.**
   - Departures are sequenced `departure_interval_s` (10 s) apart.
   - While conflicts remain, the later-starting aircraft of the earliest conflict waits
     longer, up to `max_start_delay_s` (600 s).
   - The delay is flown on board as a loiter where the aircraft is, so departures stay
     sequenced even if the link drops.
   - What is left is reported, never hidden.
6. **Checked again at the start.**
   - When a mission is started, the 4D check runs again from where the aircraft are then.
   - Aircraft in conflict are rejected unless a supervisor overrides. The override is
     confirmed and audited like every override (ADR 0011).
7. **Bulk goto** (`domain/spread`):
   - Several aircraft sent to one datum each get their own point on a hexagonal lattice
     around it, `goto_spread_m` (60 m) apart: the datum first, then ring after ring.
   - Points go to aircraft shortest-pair first, which avoids crossing paths where it can.
   - Each aircraft also gets its own altitude layer, and the flights are checked in 4D as
     above.
   - A bulk goto is always confirmed.
   - This replaces M3's rule that a goto takes exactly one aircraft. Several aircraft still
     never share one target point.

## Consequences

- Separation between GCS-planned flights is planned and checked before anything flies, and
  checked again at the start. In flight, the collision-risk alert (ADR 0031) watches what
  actually happens.
- The separation minima, layer spacing, bands and delays are station settings, so an
  incident's rules or a regulator's can be applied without code changes.
- The model flies straight legs at constant speed and ignores wind and PX4's turn
  anticipation, which is why the separation minima carry a margin. Real paths can differ by
  tens of metres; live alerts are the second line.
- Swarm missions are deconflicted on board and are not part of this check. A mixed incident
  relies on the incident's airspace plan and live alerts between the two.
