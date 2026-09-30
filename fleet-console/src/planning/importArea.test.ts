import { describe, expect, it } from 'vitest';

import { cleanRing, ImportError, MAX_VERTICES, parseAreaFile, type LonLat } from './importArea';

const SQUARE: LonLat[] = [
  [8.54, 47.39],
  [8.55, 47.39],
  [8.55, 47.4],
  [8.54, 47.4],
  [8.54, 47.39],
];

describe('search area import', () => {
  it('reads a CalTopo-style GeoJSON export: titled polygons, lines and markers', () => {
    const text = JSON.stringify({
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          properties: { title: 'Segment A', class: 'Shape' },
          geometry: { type: 'Polygon', coordinates: [SQUARE.map(([x, y]) => [x, y, 500])] },
        },
        {
          type: 'Feature',
          properties: { title: 'Trail' },
          geometry: {
            type: 'LineString',
            coordinates: [
              [8.5, 47.3],
              [8.51, 47.31],
            ],
          },
        },
        {
          type: 'Feature',
          properties: { title: 'LKP' },
          geometry: { type: 'Point', coordinates: [8.5, 47.3] },
        },
      ],
    });

    const areas = parseAreaFile('export.json', text);

    expect(areas).toHaveLength(1); // the open line and the marker are not areas
    expect(areas[0]?.name).toBe('Segment A');
    expect(areas[0]?.ring).toEqual(SQUARE); // altitudes dropped, [lon, lat] kept
  });

  it('drops holes and says so, and splits a MultiPolygon', () => {
    const hole = [
      [8.545, 47.395],
      [8.546, 47.395],
      [8.546, 47.396],
      [8.545, 47.395],
    ];
    const text = JSON.stringify({
      type: 'Feature',
      properties: { name: 'Valley' },
      geometry: { type: 'MultiPolygon', coordinates: [[SQUARE, hole], [SQUARE]] },
    });

    const areas = parseAreaFile('valley.geojson', text);

    expect(areas.map((a) => a.name)).toEqual(['Valley 1', 'Valley 2']);
    expect(areas[0]?.notes).toContain('holes dropped (a search area has none)');
    expect(areas[1]?.notes).toEqual([]);
  });

  it('reads KML polygons with a name, whatever the namespace', () => {
    const text = `<?xml version="1.0" encoding="UTF-8"?>
      <kml xmlns="http://www.opengis.net/kml/2.2"><Document>
        <Placemark><name>Sector 3</name><Polygon><outerBoundaryIs><LinearRing>
          <coordinates>8.54,47.39,0 8.55,47.39,0 8.55,47.4,0 8.54,47.4,0 8.54,47.39,0</coordinates>
        </LinearRing></outerBoundaryIs></Polygon></Placemark>
      </Document></kml>`;

    const [area] = parseAreaFile('sectors.kml', text);

    expect(area?.name).toBe('Sector 3');
    expect(area?.ring).toEqual(SQUARE);
  });

  it('closes a GPX track into an area, named after the track', () => {
    const text = `<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1"><trk><name>Boundary</name><trkseg>
        <trkpt lat="47.39" lon="8.54"/><trkpt lat="47.39" lon="8.55"/>
        <trkpt lat="47.4" lon="8.55"/><trkpt lat="47.4" lon="8.54"/>
      </trkseg></trk></gpx>`;

    const [area] = parseAreaFile('boundary.gpx', text);

    expect(area?.name).toBe('Boundary');
    expect(area?.ring).toEqual(SQUARE);
    expect(area?.notes).toContain('the track was closed into an area');
  });

  it('names unnamed areas after the file', () => {
    const text = JSON.stringify({ type: 'Polygon', coordinates: [SQUARE] });

    expect(parseAreaFile('north-ridge.geojson', text)[0]?.name).toBe('north-ridge');
  });

  it('refuses files without an area, unknown formats and invalid content, with a reason', () => {
    const point = JSON.stringify({ type: 'Point', coordinates: [8.5, 47.3] });
    expect(() => parseAreaFile('p.geojson', point)).toThrow(/No area found/);
    expect(() => parseAreaFile('notes.txt', 'hello')).toThrow(/Unknown file type/);
    expect(() => parseAreaFile('broken.json', '{')).toThrow(ImportError);
    expect(() => parseAreaFile('broken.kml', '<kml><Placemark>')).toThrow(/not valid KML/);
    const outside = JSON.stringify({
      type: 'Polygon',
      coordinates: [
        [
          [47.39, 190],
          [47.4, 190],
          [47.4, 191],
          [47.39, 190],
        ],
      ],
    });
    expect(() => parseAreaFile('swapped.json', outside)).toThrow(/outside WGS84/);
  });

  it('simplifies a detailed ring to the server limit, within metres', () => {
    // A 600-vertex circle of about 500 m radius.
    const ring: LonLat[] = Array.from({ length: 600 }, (_, i) => {
      const a = (2 * Math.PI * i) / 600;
      return [8.545 + 0.0066 * Math.cos(a), 47.395 + 0.0045 * Math.sin(a)];
    });

    const cleaned = cleanRing([...ring, ring[0] ?? [0, 0]]);

    expect(cleaned).not.toBeNull();
    const vertices = (cleaned?.ring.length ?? 0) - 1;
    expect(vertices).toBeLessThanOrEqual(MAX_VERTICES);
    expect(vertices).toBeGreaterThan(20);
    expect(cleaned?.ring[0]).toEqual(cleaned?.ring.at(-1)); // still closed
    expect(cleaned?.notes[0]).toMatch(/simplified from 600 to \d+ vertices/);
  });

  it('removes repeated points and rejects degenerate rings', () => {
    const repeated: LonLat[] = [
      [8.54, 47.39],
      [8.54, 47.39],
      [8.55, 47.39],
      [8.55, 47.4],
      [8.54, 47.39],
    ];
    expect(cleanRing(repeated)?.ring).toHaveLength(4);
    expect(
      cleanRing([
        [8.54, 47.39],
        [8.55, 47.39],
        [8.54, 47.39],
      ]),
    ).toBeNull();
  });
});
