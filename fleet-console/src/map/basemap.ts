// The offline basemap (ADR 0006, ADR 0030): per region, a PMTiles extract with its fonts and
// sprites, and a Sentinel-2 image for the satellite view. All are served by the console itself,
// as listed in `basemap/index.json` (written by scripts/fetch-basemap.mjs and
// scripts/fetch_region.py). Without them the map is a plain background and says so; it never
// loads tiles from the Internet.
import { layers, namedFlavor } from '@protomaps/basemaps';
import type { LayerSpecification, StyleSpecification } from 'maplibre-gl';

export const BASEMAP_ROOT = '/basemap';
export const BACKGROUND = '#1b2229';
/** Satellite image layers are named `imagery-<region id>`; hidden until the view is chosen. */
export const IMAGERY_PREFIX = 'imagery-';

export interface ImageryInfo {
  region: string;
  name: string;
  /** The day the scene was taken (YYYY-MM-DD). */
  date: string;
  attribution: string;
}

export interface Basemap {
  style: StyleSpecification;
  /** False: no basemap on this station (the map shows a notice). */
  available: boolean;
  /** Labels need the basemap's fonts; without them aircraft are drawn without callsigns. */
  glyphs: boolean;
  /** Regions with a satellite image (the satellite view is offered when there is one). */
  imagery: ImageryInfo[];
}

type Corners = [[number, number], [number, number], [number, number], [number, number]];

interface RegionEntry {
  id: string;
  name: string;
  file?: string;
  attribution?: string;
  imagery?: { file: string; coordinates: Corners; date: string; attribution: string };
}

function plain(): Basemap {
  return {
    available: false,
    glyphs: false,
    imagery: [],
    style: {
      version: 8,
      sources: {},
      layers: [background()],
    },
  };
}

function background(): LayerSpecification {
  return { id: 'background', type: 'background', paint: { 'background-color': BACKGROUND } };
}

export async function loadBasemap(fetcher: typeof fetch = fetch): Promise<Basemap> {
  let regions: RegionEntry[];
  try {
    const response = await fetcher(`${BASEMAP_ROOT}/index.json`, { cache: 'no-store' });
    if (!response.ok) return plain();
    regions = ((await response.json()) as { regions?: RegionEntry[] }).regions ?? [];
  } catch {
    return plain();
  }
  const vector = regions.filter((r) => r.file);
  const imaged = regions.filter((r) => r.imagery);
  if (vector.length === 0 && imaged.length === 0) return plain();

  const origin = window.location.origin;
  const sources: StyleSpecification['sources'] = {};
  const below: LayerSpecification[] = [background()];
  const labels: LayerSpecification[] = [];
  for (const region of vector) {
    const source = `basemap-${region.id}`;
    sources[source] = {
      type: 'vector',
      url: `pmtiles://${origin}${BASEMAP_ROOT}/${region.file ?? ''}`,
      ...(region.attribution ? { attribution: region.attribution } : {}),
    };
    for (const layer of layers(source, namedFlavor('dark'), { lang: 'en' })) {
      if (layer.type === 'background') continue;
      const renamed = { ...layer, id: `${region.id}-${layer.id}` } as LayerSpecification;
      (layer.type === 'symbol' ? labels : below).push(renamed);
    }
  }
  const images: LayerSpecification[] = [];
  for (const region of imaged) {
    if (!region.imagery) continue;
    const id = `${IMAGERY_PREFIX}${region.id}`;
    sources[id] = {
      type: 'image',
      url: `${origin}${BASEMAP_ROOT}/${region.imagery.file}`,
      coordinates: region.imagery.coordinates,
    };
    images.push({ id, type: 'raster', source: id, layout: { visibility: 'none' } });
  }
  return {
    available: true,
    glyphs: vector.length > 0,
    imagery: imaged.map((r) => ({
      region: r.id,
      name: r.name,
      date: r.imagery?.date ?? '',
      attribution: r.imagery?.attribution ?? 'Contains modified Copernicus Sentinel data',
    })),
    style: {
      version: 8,
      ...(vector.length > 0
        ? {
            glyphs: `${origin}${BASEMAP_ROOT}/fonts/{fontstack}/{range}.pbf`,
            sprite: `${origin}${BASEMAP_ROOT}/sprites/dark`,
          }
        : {}),
      sources,
      // The satellite image covers the map's fills and roads, not its labels.
      layers: [...below, ...images, ...labels],
    },
  };
}
