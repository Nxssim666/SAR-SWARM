// The offline basemap (ADR 0006): a PMTiles extract served by the console itself, with its
// fonts and sprites. Without it the map is a plain background and says so; it never tries
// to load tiles from the Internet.
import { layers, namedFlavor } from '@protomaps/basemaps';
import type { StyleSpecification } from 'maplibre-gl';

export const BASEMAP_ROOT = '/basemap';
export const BACKGROUND = '#1b2229';

export interface Basemap {
  style: StyleSpecification;
  /** False: no basemap on this station (the map shows a notice). */
  available: boolean;
  /** Labels need the basemap's fonts; without them aircraft are drawn without callsigns. */
  glyphs: boolean;
}

interface Manifest {
  file: string;
  attribution: string;
}

function plain(): Basemap {
  return {
    available: false,
    glyphs: false,
    style: {
      version: 8,
      sources: {},
      layers: [{ id: 'background', type: 'background', paint: { 'background-color': BACKGROUND } }],
    },
  };
}

export async function loadBasemap(fetcher: typeof fetch = fetch): Promise<Basemap> {
  let manifest: Manifest;
  try {
    const response = await fetcher(`${BASEMAP_ROOT}/manifest.json`, { cache: 'no-store' });
    if (!response.ok) return plain();
    manifest = (await response.json()) as Manifest;
  } catch {
    return plain();
  }
  const origin = window.location.origin;
  return {
    available: true,
    glyphs: true,
    style: {
      version: 8,
      glyphs: `${origin}${BASEMAP_ROOT}/fonts/{fontstack}/{range}.pbf`,
      sprite: `${origin}${BASEMAP_ROOT}/sprites/dark`,
      sources: {
        protomaps: {
          type: 'vector',
          url: `pmtiles://${origin}${BASEMAP_ROOT}/${manifest.file}`,
          attribution: manifest.attribution,
        },
      },
      layers: layers('protomaps', namedFlavor('dark'), { lang: 'en' }),
    },
  };
}
