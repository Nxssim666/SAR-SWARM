# 0006. Map: MapLibre GL JS with offline PMTiles

- Status: Accepted; refined by [0027](0027-console-architecture.md) (symbology, sample basemap)
- Date: 2026-09-28

## Context

The map is the console's primary surface. It must work with **no Internet**, render 50 rotating
aircraft markers with trails at interactive frame rates, and support drawing and editing search
areas, lasso selection and geofences. Licenses must allow self-hosting.

## Decision

- **MapLibre GL JS** (BSD-3) for WebGL vector and raster rendering.
- **Offline basemaps as PMTiles**, a single-file tile archive:
  - A vector basemap for the operating region, extracted from a Protomaps planet build with
    `pmtiles extract --bbox` before deployment, while still online.
  - Optional raster layers (orthophoto or topographic) converted to PMTiles.
  - Fonts (glyphs) and sprites are self-hosted. Nothing loads from a CDN.
  - The gateway serves tiles from local disk. The runbook covers the preparation workflow (M6).
- **terra-draw** (MIT) for polygon, line and point drawing and editing, and for lasso selection.
- Aircraft, trails, search areas, patterns, geofences and POIs are **native MapLibre layers**
  fed by GeoJSON sources, not DOM markers, so they can be updated at rate without re-rendering React.
- Coordinate display: decimal degrees, DDM and MGRS/USNG, selectable (M3/M4). Ground teams
  commonly use grid references.

## Alternatives considered

- **Leaflet:** simple and battle-tested, but raster and DOM oriented. Rotating 50 markers with
  trails at 10 Hz and smooth vector basemaps are harder, and offline vector tiles need plugins.
- **OpenLayers:** strong GIS features and good offline support, a solid alternative. MapLibre
  was chosen for its WebGL performance with dynamic layers and the PMTiles/Protomaps ecosystem.
- **CesiumJS:** 3D terrain is attractive for mountain SAR, but it's heavy, offline terrain and
  imagery preparation is harder, and it's more than 2D tasking needs. It could be added later as
  an optional 3D view.
- **Online tile services:** incompatible with offline field use.

## Consequences

- Basemaps must be prepared per region before deployment. An unprepared region shows a
  plain background with a visible "no basemap" notice, never a silently blank map.
- WebGL is required (ADR 0002, A11).
- Contour search (M4) needs elevation data. An optional DEM (GeoTIFF) is handled by the
  fleet service, not by the map library.
