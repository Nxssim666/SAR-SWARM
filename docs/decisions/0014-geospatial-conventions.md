# 0014. Geospatial, altitude and unit conventions

- Status: Accepted
- Date: 2026-09-28

## Context

Coordinate and altitude mistakes are silent and dangerous. The onboard code learned this.
`mission_file.py` rejects bare coordinate pairs because GeoJSON orders them `[lon, lat]` and
most tools order them `[lat, lon]`, and a swapped pair moves an area thousands of kilometres.
Aircraft launch from different home elevations, so "50 m" is ambiguous. Map and GIS tools
expect GeoJSON.

## Decision

### Positions

- Every stored and transmitted position is **WGS84** (EPSG:4326), in decimal degrees.
- **Points** (waypoints, aircraft positions, POIs) are objects with **explicit keys**:
  `{"latitude": 47.3977, "longitude": 8.5456}`. Bare pairs are never used for points.
- **Areas** (search areas, geofences, sectors) are **GeoJSON Polygons** (RFC 7946, `[lon, lat]`,
  exterior ring counter-clockwise), because map and GIS interoperability needs it. They're
  validated on input:
  - The ring is closed and valid, with no self-intersection (shapely `is_valid`).
  - At most 256 vertices, matching the onboard limit, and an area within configured bounds.
  - **Every vertex lies inside the incident's operating area**, a configurable radius around
    the incident base (default 25 km). This is what catches swapped coordinates, which are
    otherwise still valid numbers.

### Altitudes

The **reference is part of the field name**. A bare `altitude` field is never used.

| Field suffix | Meaning |
|---|---|
| `altitude_amsl_m` | Above mean sea level (WGS84 / EGM96 as reported by PX4) |
| `altitude_relative_m` | Above the aircraft's home or takeoff point |
| `height_agl_m` | Above ground level; needs a DEM, so it's only present when known |

- PX4 missions use relative altitude (`MAV_FRAME_GLOBAL_RELATIVE_ALT_INT`). The GCS converts
  per aircraft using that aircraft's home AMSL.
- **Deconfliction always uses AMSL**, because two aircraft with the same relative altitude can
  be at different true altitudes.

### Units and angles

- SI units: metres, metres per second, seconds. Battery is percent (0–100) plus volts.
- **Headings and courses are degrees true, clockwise from north, in [0, 360).** Sources with
  other conventions are converted at the driver or bridge boundary, with a test pinning each
  sign. For example, the onboard `DroneState.heading` is radians counter-clockwise from east.

### Planning and display

- **Planning geometry** (search patterns, lane spacing, buffers) is computed in the **UTM zone
  of the area's centroid** using pyproj, then converted back to WGS84. Planar approximations
  are not used for anything that becomes a flight path.
- **Display formats** are selectable in the console: DD, DDM and MGRS/USNG. Storage is
  always DD.

## Alternatives considered

- **GeoJSON everywhere, points included:** keeps the swap risk on the most frequently typed
  values.
- **Explicit keys everywhere, areas included:** safe, but every map and GIS integration
  would need converters.
- **Single altitude field plus a separate "frame" field:** the frame gets lost in
  transformations and UI code, so suffixed names make the reference impossible to ignore.

## Consequences

- Validation helpers live in one module (`domain/geo.py`, M1) and are property-tested.
- The console converts GeoJSON to and from explicit-key points only at the map layer.
