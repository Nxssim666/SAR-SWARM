import { describe, expect, it, vi } from 'vitest';

import { IMAGERY_PREFIX, loadBasemap } from './basemap';

function index(regions: unknown[]): typeof fetch {
  return vi.fn(() =>
    Promise.resolve(
      new Response(JSON.stringify({ regions }), {
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  );
}

const ZURICH = {
  id: 'zurich',
  name: 'Zurich',
  file: 'zurich.pmtiles',
  attribution: '© OpenStreetMap',
  imagery: {
    file: 'imagery/zurich.jpg',
    coordinates: [
      [8.4, 47.48],
      [8.7, 47.48],
      [8.7, 47.3],
      [8.4, 47.3],
    ],
    date: '2026-07-24',
    attribution: 'Contains modified Copernicus Sentinel data 2026',
  },
};

describe('offline basemap', () => {
  it('reads the regions the fetch scripts list in index.json', async () => {
    const fetcher = index([ZURICH]);

    const basemap = await loadBasemap(fetcher);

    expect(fetcher).toHaveBeenCalledWith('/basemap/index.json', { cache: 'no-store' });
    expect(basemap.available).toBe(true);
    expect(basemap.glyphs).toBe(true);
    expect(Object.keys(basemap.style.sources)).toEqual(['basemap-zurich', 'imagery-zurich']);
    expect(basemap.style.sources['basemap-zurich']).toMatchObject({
      type: 'vector',
      url: expect.stringContaining('pmtiles://') as string,
    });
    expect(basemap.style.sources['imagery-zurich']).toMatchObject({
      type: 'image',
      url: expect.stringContaining('/basemap/imagery/zurich.jpg') as string,
      coordinates: ZURICH.imagery.coordinates,
    });
  });

  it('offers the satellite image hidden, above the fills and below the labels', async () => {
    const basemap = await loadBasemap(index([ZURICH]));
    const layers = basemap.style.layers;
    const image = layers.findIndex((l) => l.id === `${IMAGERY_PREFIX}zurich`);
    const firstLabel = layers.findIndex((l) => l.type === 'symbol');

    expect(basemap.imagery).toEqual([
      {
        region: 'zurich',
        name: 'Zurich',
        date: '2026-07-24',
        attribution: 'Contains modified Copernicus Sentinel data 2026',
      },
    ]);
    expect(layers[image]).toMatchObject({ type: 'raster', layout: { visibility: 'none' } });
    expect(image).toBeGreaterThan(0);
    expect(image).toBeLessThan(firstLabel);
    expect(layers.slice(0, image).every((l) => l.type !== 'symbol')).toBe(true);
  });

  it('shows a plain map, never tiles from the Internet, without region data', async () => {
    const missing = vi.fn(() => Promise.resolve(new Response('', { status: 404 })));

    const basemap = await loadBasemap(missing);

    expect(basemap.available).toBe(false);
    expect(basemap.imagery).toEqual([]);
    expect(basemap.style.sources).toEqual({});
  });

  it('shows imagery alone when a region has no vector basemap', async () => {
    const imageOnly = { id: ZURICH.id, name: ZURICH.name, imagery: ZURICH.imagery };

    const basemap = await loadBasemap(index([imageOnly]));

    expect(basemap.available).toBe(true);
    expect(basemap.glyphs).toBe(false);
    expect(Object.keys(basemap.style.sources)).toEqual(['imagery-zurich']);
  });
});
