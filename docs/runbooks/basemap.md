# Basemap and region data

The console's map and the fleet service's terrain checks work offline from **region data**
prepared beforehand, with Internet (ADR 0006, ADR 0030):

| Data | Tool | Lands in | Used for |
|---|---|---|---|
| Basemap (OpenStreetMap vector tiles, fonts, sprites) | `fleet-console/scripts/fetch-basemap.mjs` | `fleet-console/public/basemap/` | The map |
| Imagery (Sentinel-2, 10 m, for orientation) | `scripts/fetch_region.py` | `fleet-console/public/basemap/imagery/` | Imagery layer |
| Terrain (Copernicus GLO-30 DEM) | `scripts/fetch_region.py` | `fleet-service/terrain/` | Terrain clearance of planned routes, contour searches |

Without a basemap the map is a plain background and says so. Without terrain, clearance is
not checked, and plans say so. Nothing is ever loaded from the Internet at run time.

## Add a region

1. Add it to `fleet-console/scripts/regions.json`: an `id`, a `name`, the bounding box
   `[west, south, east, north]` in degrees (cover the whole operating area with margin), and
   `maxzoom` (15 is enough for search planning; each level quadruples the size).
2. Fetch (from the repository root, with Internet; `pmtiles` CLI on PATH or in `.tools/pmtiles/`):

   ```bash
   node fleet-console/scripts/fetch-basemap.mjs --region <id>
   python -m uv run scripts/fetch_region.py --region <id>
   ```

   `fetch_region.py` pins the Sentinel-2 scene it picks in `regions.json`, so later fetches
   produce the same imagery; commit that change. `--repick` chooses a newer scene.
3. Build the bundle (`deploy/bundle.sh`): it carries `region/basemap` and `region/terrain`,
   and `install.sh` installs them.

Check the sizes before copying (`du -sh fleet-console/public/basemap fleet-service/terrain`):
they grow with the area and, for the basemap, fourfold per zoom level.

## Update a running station

Copy a new bundle and run `sudo ./deploy/install.sh` (it keeps the databases). To update only
the region data:

```bash
cp -r region/basemap deploy/basemap          # the gateway serves it; reload the console page
docker compose -f deploy/compose.yaml cp region/terrain/. fleet-service:/data/terrain/
docker compose -f deploy/compose.yaml restart fleet-service    # terrain is read at startup
```

## Licences (shown in the console)

Map data © OpenStreetMap contributors (ODbL), tiles by Protomaps. Copernicus DEM
© DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH 2014–2018, provided under
COPERNICUS by the European Union and ESA. Contains modified Copernicus Sentinel data.
