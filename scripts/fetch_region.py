# /// script
# requires-python = ">=3.12"
# dependencies = ["rasterio>=1.4", "numpy>=2.2", "shapely>=2.1", "pillow>=11"]
# ///
"""
Fetch a region's terrain and imagery for offline use (ADR 0030).

For each region of ``fleet-console/scripts/regions.json``:

* **Terrain**: the Copernicus GLO-30 DEM (30 m, heights above the EGM2008 geoid), read for
  the region's bounding box only from the Cloud-Optimized GeoTIFFs of the AWS open-data
  bucket, written to ``fleet-service/terrain/<id>.npy`` (float32, NaN where unknown) with a
  ``<id>.json`` header. The fleet service reads them (``SARGCS_TERRAIN_DIR``).
* **Imagery**: the least-cloudy recent Sentinel-2 L2A true-colour scene whose data covers
  the whole box (Earth Search catalogue), resampled to Web Mercator at about 10 m and
  written to ``fleet-console/public/basemap/imagery/<id>.jpg``; its corners go into the
  basemap's ``index.json``. The chosen scene is pinned in ``regions.json`` so later fetches
  are the same image. Sentinel-2's 10 m pixels are for orientation only: people are never
  visible.

Run from the repository root (uv installs the dependencies in a throwaway environment):

    python -m uv run scripts/fetch_region.py [--region ID] [--terrain-only] [--repick]

Licences: Copernicus DEM (c) DLR e.V. 2010-2014 and (c) Airbus Defence and Space GmbH
2014-2018, provided under COPERNICUS by the European Union and ESA; Sentinel-2 imagery
contains modified Copernicus Sentinel data. Both allow free use with attribution.
"""

import argparse
import json
import math
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import from_bounds as window_from_bounds
from shapely.geometry import box, shape

ROOT = Path(__file__).resolve().parents[1]
REGIONS = ROOT / "fleet-console" / "scripts" / "regions.json"
BASEMAP = ROOT / "fleet-console" / "public" / "basemap"
TERRAIN = ROOT / "fleet-service" / "terrain"

DEM_URL = (
    "https://copernicus-dem-30m.s3.amazonaws.com/"
    "Copernicus_DSM_COG_10_{tile}_DEM/Copernicus_DSM_COG_10_{tile}_DEM.tif"
)
DEM_ATTRIBUTION = (
    "Copernicus DEM GLO-30: © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH "
    "2014-2018, provided under COPERNICUS by the European Union and ESA"
)
STAC = "https://earth-search.aws.element84.com/v1"
IMAGERY_GSD_M = 10.0
MERCATOR_RADIUS_M = 6378137.0


def dem_tiles(bbox: list[float]) -> list[str]:
    """The 1°x1° GLO-30 tile names covering ``bbox`` (west, south, east, north)."""
    west, south, east, north = bbox
    tiles = []
    for lat in range(math.floor(south), math.floor(north - 1e-9) + 1):
        for lon in range(math.floor(west), math.floor(east - 1e-9) + 1):
            ns = f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}_00"
            ew = f"{'E' if lon >= 0 else 'W'}{abs(lon):03d}_00"
            tiles.append(f"{ns}_{ew}")
    return tiles


def fetch_terrain(region: dict) -> None:
    """Read the DEM for the region's box and write the grid and its header."""
    bbox = region["bbox"]
    tiles = dem_tiles(bbox)
    if len(tiles) != 1:  # every current region fits one tile; mosaicking is not needed yet
        raise SystemExit(f"{region['id']}: spans DEM tiles {tiles}; add mosaicking first")
    url = DEM_URL.format(tile=tiles[0])
    with rasterio.open(url) as dem:
        window = window_from_bounds(*bbox, transform=dem.transform).round_offsets().round_lengths()
        heights = dem.read(1, window=window, masked=True).astype(np.float32).filled(np.nan)
        transform = dem.window_transform(window)
    rows, cols = heights.shape
    # Centre of the first (north-west) cell, and the cell size in degrees.
    lon0, lat0 = transform * (0.5, 0.5)
    header = {
        "region": region["id"],
        "rows": rows,
        "cols": cols,
        "lat0": lat0,
        "lon0": lon0,
        "lat_step": -transform.e,
        "lon_step": transform.a,
        "vertical_datum": "EGM2008",
        "source": url,
        "attribution": DEM_ATTRIBUTION,
        "fetched_at": datetime.now(UTC).isoformat(),
    }
    TERRAIN.mkdir(parents=True, exist_ok=True)
    np.save(TERRAIN / f"{region['id']}.npy", heights)
    (TERRAIN / f"{region['id']}.json").write_text(json.dumps(header, indent=2) + "\n")
    print(
        f"{region['id']}: terrain {rows}x{cols}, "
        f"{np.nanmin(heights):.0f}-{np.nanmax(heights):.0f} m, "
        f"{int(np.isnan(heights).sum())} unknown cells"
    )


def _post(url: str, body: dict) -> dict:
    request = urllib.request.Request(  # noqa: S310 - the fixed https catalogue URL
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - fixed https URL
        return json.load(response)


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310 - fixed https URL
        return json.load(response)


def choose_scene(region: dict) -> dict:
    """The pinned scene, or the least-cloudy of the last 180 days that covers the box."""
    if region.get("imagery_scene"):
        return _get(f"{STAC}/collections/sentinel-2-l2a/items/{region['imagery_scene']}")
    end = datetime.now(UTC)
    found = _post(
        f"{STAC}/search",
        {
            "collections": ["sentinel-2-l2a"],
            "bbox": region["bbox"],
            "datetime": f"{(end - timedelta(days=180)).isoformat()}/{end.isoformat()}",
            "query": {"eo:cloud_cover": {"lt": 5}},
            "sortby": [{"field": "properties.eo:cloud_cover", "direction": "asc"}],
            "limit": 50,
        },
    )
    area = box(*region["bbox"])
    for item in found["features"]:
        if shape(item["geometry"]).contains(area):
            return item
    raise SystemExit(f"{region['id']}: no clear Sentinel-2 scene covers the whole box")


def mercator(lon: float, lat: float) -> tuple[float, float]:
    """WGS84 -> Web Mercator metres."""
    x = math.radians(lon) * MERCATOR_RADIUS_M
    y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * MERCATOR_RADIUS_M
    return x, y


def fetch_imagery(region: dict) -> dict:
    """Resample the scene to Web Mercator over the box; return the index entry."""
    west, south, east, north = region["bbox"]
    item = choose_scene(region)
    href = item["assets"]["visual"]["href"]
    left, bottom = mercator(west, south)
    right, top = mercator(east, north)
    # About 10 m on the ground: Web Mercator stretches by 1 / cos(latitude).
    pixel = IMAGERY_GSD_M / math.cos(math.radians((south + north) / 2))
    width, height = round((right - left) / pixel), round((top - bottom) / pixel)
    target = np.zeros((3, height, width), dtype=np.uint8)
    with rasterio.open(href) as scene:
        window = window_from_bounds(
            *transform_bounds("EPSG:4326", scene.crs, west, south, east, north, densify_pts=21),
            transform=scene.transform,
        )
        window = window.round_offsets().round_lengths()
        source = scene.read([1, 2, 3], window=window)
        reproject(
            source,
            target,
            src_transform=scene.window_transform(window),
            src_crs=scene.crs,
            src_nodata=0,
            dst_transform=from_bounds(left, bottom, right, top, width, height),
            dst_crs="EPSG:3857",
            dst_nodata=0,
            resampling=Resampling.bilinear,
        )
    empty = float((target.max(axis=0) == 0).mean())
    if empty > 0.005:
        raise SystemExit(f"{region['id']}: {empty:.1%} of the image has no data; pick another")
    out = BASEMAP / "imagery" / f"{region['id']}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.moveaxis(target, 0, -1)).save(out, quality=85, optimize=True)
    taken = item["properties"]["datetime"][:10]
    print(f"{region['id']}: imagery {width}x{height} from {item['id']} ({taken})")
    return {
        "file": f"imagery/{region['id']}.jpg",
        # MapLibre image source order: top-left, top-right, bottom-right, bottom-left.
        "coordinates": [[west, north], [east, north], [east, south], [west, south]],
        "scene": item["id"],
        "date": taken,
        "gsd_m": IMAGERY_GSD_M,
        "attribution": f"Contains modified Copernicus Sentinel data {taken[:4]}",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    parser.add_argument("--region", help="one region id (default: all)")
    parser.add_argument("--terrain-only", action="store_true")
    parser.add_argument("--repick", action="store_true", help="choose a new imagery scene")
    args = parser.parse_args()

    config = json.loads(REGIONS.read_text(encoding="utf-8"))
    regions = [r for r in config["regions"] if args.region in (None, r["id"])]
    if not regions:
        raise SystemExit(f"unknown region {args.region}")
    index_path = BASEMAP / "index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {"regions": []}

    for region in regions:
        fetch_terrain(region)
        if args.terrain_only:
            continue
        if args.repick:
            region["imagery_scene"] = None
        imagery = fetch_imagery(region)
        region["imagery_scene"] = imagery["scene"]
        entry = next((e for e in index["regions"] if e["id"] == region["id"]), None)
        if entry is None:
            print(f"{region['id']}: no basemap yet (fetch-basemap.mjs); imagery kept for it")
            entry = {"id": region["id"], "name": region["name"], "bbox": region["bbox"]}
            index["regions"].append(entry)
        entry["imagery"] = imagery

    if not args.terrain_only:
        REGIONS.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        index["regions"].sort(key=lambda e: e["id"])
        BASEMAP.mkdir(parents=True, exist_ok=True)
        index_path.write_text(json.dumps(index, indent=2) + "\n")


if __name__ == "__main__":
    main()
