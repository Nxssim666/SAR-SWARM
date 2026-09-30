# 0030. Offline region data: basemaps, terrain and imagery

- Status: Accepted
- Date: 2026-09-30
- Refines: [0006](0006-map-and-offline-tiles.md), [0014](0014-geospatial-conventions.md), [0027](0027-console-architecture.md)

## Context

The field station works offline (ADR 0002). M3 shipped an offline basemap sample around the
simulator's site. M4 needs terrain heights for terrain clearance and contour search
(ADR 0028, ADR 0029). A recent image of the ground helps operators orient where the map
is sparse. All of it must be prepared per region while online, and never fetched at run
time.

## Decision

1. **Regions are data.** `fleet-console/scripts/regions.json` lists each region: an id, a
   name, a bounding box, the basemap's maximum zoom, and the pinned imagery scene. Two
   regions are prepared:
   - `zurich`, the simulator's site;
   - `kramatorsk`.

   Adding a region is a data change, not a code change. The regions for the field remain
   the user's decision (PLAN.md).
2. **Basemap.** `fetch-basemap.mjs` extracts each region from the Protomaps OpenStreetMap
   build, pinned by date, into PMTiles, with the fonts and sprites its style needs. The
   console serves them itself. Attribution: © OpenStreetMap contributors (ODbL).
3. **Terrain.**
   - `scripts/fetch_region.py` reads the **Copernicus GLO-30 DEM** (30 m) for the region's
     box only, from the open-data Cloud-Optimized GeoTIFFs. Heights are above the EGM2008
     geoid.
   - It writes a float32 grid (`<id>.npy`, NaN where unknown) with a JSON header, which the
     fleet service reads from `SARGCS_TERRAIN_DIR` (default `<data_dir>/terrain`).
   - `domain/terrain` interpolates heights bilinearly. Outside every grid, or next to an
     unknown cell, the height is **unknown** (`None`), never a guess (ADR 0002, S7).
4. **Imagery.**
   - `fetch_region.py` picks the least-cloudy recent **Sentinel-2 L2A** true-colour scene
     that covers the whole box. It resamples the scene to Web Mercator at about 10 m and
     writes it as a JPEG, which the console can show under the map.
   - The chosen scene is pinned in `regions.json`, so later fetches give the same image.
   - At 10 m per pixel the image is for orientation only: people are never visible in it.
5. **Nothing is committed.** Basemaps, imagery and terrain are gitignored and fetched per
   installation. The M6 offline bundle will carry them with checksums.

## Consequences

- Terrain clearance and contour search work where a grid is installed. Elsewhere the plan
  says the clearance is unchecked, and contour search falls back to perimeter rings,
  labelled as a fallback.
- GLO-30 is a surface model: it includes buildings and forest canopy. Over trees the
  ground reads higher than the bare earth. That errs on the safe side for the minimum
  clearance, but an aircraft kept under the maximum height above that surface can be up to
  the canopy's height higher above the bare ground.
- PX4 altitudes are AMSL from its own geoid model. The difference from EGM2008 is typically
  under a metre, well inside the clearance margins.
- Preparing a region needs the Internet, the `pmtiles` CLI and Python with rasterio. Both
  scripts are idempotent, and their output is pinned by build date and scene id.
- Licences allow free use with attribution: Copernicus DEM © DLR e.V. 2010–2014 and © Airbus
  Defence and Space GmbH 2014–2018, provided under COPERNICUS by the European Union and ESA;
  the imagery contains modified Copernicus Sentinel data.
