// Search areas from files (M4): GeoJSON, GPX and KML, as exported by CalTopo, SARTopo and
// most GIS and mapping tools. Pure: text in, candidate areas out; the operator picks one and
// the fleet service validates it (closed ring, 3-256 vertices, inside the operating area).
//
// What counts as an area:
// - GeoJSON: Polygon and MultiPolygon (outer rings; holes are dropped and said so), and a
//   LineString whose ends meet.
// - KML: Polygon outer boundaries (also inside MultiGeometry), and closed LineStrings.
// - GPX: tracks and routes of at least three points, closed if they are not.
//
// Rings are cleaned (repeated points removed, closed) and, above the server's 256-vertex
// limit, simplified (Douglas-Peucker in metres) until they fit; the result says so.

export type LonLat = [number, number];

export interface ImportedArea {
  name: string;
  ring: LonLat[];
  /** What was changed on the way in, for the operator. */
  notes: string[];
}

export class ImportError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ImportError';
  }
}

export const MAX_VERTICES = 256;

type Format = 'geojson' | 'kml' | 'gpx';

function formatOf(fileName: string, text: string): Format {
  const lower = fileName.toLowerCase();
  if (lower.endsWith('.kml')) return 'kml';
  if (lower.endsWith('.gpx')) return 'gpx';
  if (lower.endsWith('.geojson') || lower.endsWith('.json')) return 'geojson';
  const head = text.trimStart().slice(0, 400);
  if (head.startsWith('{')) return 'geojson';
  if (head.includes('<kml')) return 'kml';
  if (head.includes('<gpx')) return 'gpx';
  throw new ImportError(
    'Unknown file type: use GeoJSON (.geojson, .json), KML (.kml) or GPX (.gpx).',
  );
}

/** Parse a file's text into candidate search areas (at least one, or ImportError). */
export function parseAreaFile(fileName: string, text: string): ImportedArea[] {
  const format = formatOf(fileName, text);
  const raw =
    format === 'geojson' ? fromGeoJson(text) : format === 'kml' ? fromKml(text) : fromGpx(text);
  const base = fileName.replace(/\.[^.]+$/, '') || 'Imported area';
  const areas: ImportedArea[] = [];
  raw.forEach((candidate, index) => {
    const cleaned = cleanRing(candidate.ring);
    if (cleaned === null) return;
    const given = candidate.name?.trim() ?? '';
    const name = given !== '' ? given : raw.length > 1 ? `${base} ${String(index + 1)}` : base;
    areas.push({ name, ring: cleaned.ring, notes: [...candidate.notes, ...cleaned.notes] });
  });
  if (areas.length === 0) {
    throw new ImportError(
      `No area found in ${fileName}: it needs a polygon, or a closed line or track of at least three points.`,
    );
  }
  return areas;
}

interface Candidate {
  name: string | null;
  ring: LonLat[];
  notes: string[];
}

// --- GeoJSON -------------------------------------------------------------------------------

type Json = Record<string, unknown>;

function isObject(value: unknown): value is Json {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function positions(value: unknown): LonLat[] {
  if (!Array.isArray(value)) return [];
  const out: LonLat[] = [];
  for (const p of value) {
    if (Array.isArray(p) && typeof p[0] === 'number' && typeof p[1] === 'number') {
      out.push([p[0], p[1]]); // GeoJSON: [longitude, latitude(, altitude)]
    }
  }
  return out;
}

function featureName(properties: unknown): string | null {
  if (!isObject(properties)) return null;
  for (const key of ['title', 'name', 'Name', 'label']) {
    const value = properties[key];
    if (typeof value === 'string' && value.trim()) return value;
  }
  return null;
}

function fromGeometry(geometry: unknown, name: string | null): Candidate[] {
  if (!isObject(geometry)) return [];
  const coordinates = geometry.coordinates;
  switch (geometry.type) {
    case 'Polygon': {
      if (!Array.isArray(coordinates)) return [];
      const notes = coordinates.length > 1 ? ['holes dropped (a search area has none)'] : [];
      return [{ name, ring: positions(coordinates[0]), notes }];
    }
    case 'MultiPolygon':
      if (!Array.isArray(coordinates)) return [];
      return coordinates.flatMap((polygon: unknown, i: number) =>
        fromGeometry(
          { type: 'Polygon', coordinates: polygon },
          name && coordinates.length > 1 ? `${name} ${String(i + 1)}` : name,
        ),
      );
    case 'LineString': {
      const line = positions(coordinates);
      return closedEnough(line) ? [{ name, ring: line, notes: [] }] : [];
    }
    case 'GeometryCollection':
      return Array.isArray(geometry.geometries)
        ? geometry.geometries.flatMap((g: unknown) => fromGeometry(g, name))
        : [];
    default:
      return [];
  }
}

function fromGeoJson(text: string): Candidate[] {
  let doc: unknown;
  try {
    doc = JSON.parse(text);
  } catch {
    throw new ImportError('The file is not valid JSON.');
  }
  if (!isObject(doc)) throw new ImportError('The file is not a GeoJSON object.');
  if (doc.type === 'FeatureCollection' && Array.isArray(doc.features)) {
    return doc.features.flatMap((f: unknown) =>
      isObject(f) ? fromGeometry(f.geometry, featureName(f.properties)) : [],
    );
  }
  if (doc.type === 'Feature') return fromGeometry(doc.geometry, featureName(doc.properties));
  return fromGeometry(doc, null);
}

// --- KML and GPX ---------------------------------------------------------------------------

function xml(text: string, what: string): Document {
  const doc = new DOMParser().parseFromString(text, 'application/xml');
  if (doc.getElementsByTagName('parsererror').length > 0) {
    throw new ImportError(`The file is not valid ${what} (XML).`);
  }
  return doc;
}

/** Elements by local name, whatever the namespace prefix. */
function byName(root: Document | Element, name: string): Element[] {
  return Array.from(root.getElementsByTagNameNS('*', name));
}

function childText(element: Element, name: string): string | null {
  for (const child of Array.from(element.children)) {
    if (child.localName === name) return child.textContent.trim() || null;
  }
  return null;
}

/** KML coordinates: "lon,lat[,alt]" tuples separated by whitespace. */
function kmlCoordinates(text: string | null): LonLat[] {
  if (!text) return [];
  const out: LonLat[] = [];
  for (const tuple of text.trim().split(/\s+/)) {
    const [lon = NaN, lat = NaN] = tuple.split(',').map(Number);
    if (Number.isFinite(lon) && Number.isFinite(lat)) out.push([lon, lat]);
  }
  return out;
}

function fromKml(text: string): Candidate[] {
  const doc = xml(text, 'KML');
  const candidates: Candidate[] = [];
  for (const placemark of byName(doc, 'Placemark')) {
    const name = childText(placemark, 'name');
    for (const polygon of byName(placemark, 'Polygon')) {
      const outer = byName(polygon, 'outerBoundaryIs')[0];
      const ring = outer
        ? kmlCoordinates(byName(outer, 'coordinates')[0]?.textContent ?? null)
        : [];
      const notes =
        byName(polygon, 'innerBoundaryIs').length > 0
          ? ['holes dropped (a search area has none)']
          : [];
      candidates.push({ name, ring, notes });
    }
    for (const line of byName(placemark, 'LineString')) {
      const points = kmlCoordinates(byName(line, 'coordinates')[0]?.textContent ?? null);
      if (closedEnough(points)) candidates.push({ name, ring: points, notes: [] });
    }
  }
  return candidates;
}

function gpxPoints(elements: Element[]): LonLat[] {
  const out: LonLat[] = [];
  for (const e of elements) {
    const lat = Number(e.getAttribute('lat'));
    const lon = Number(e.getAttribute('lon'));
    if (Number.isFinite(lat) && Number.isFinite(lon)) out.push([lon, lat]);
  }
  return out;
}

function fromGpx(text: string): Candidate[] {
  const doc = xml(text, 'GPX');
  const candidates: Candidate[] = [];
  const add = (element: Element, points: LonLat[]) => {
    if (points.length < 3) return;
    const notes = closedEnough(points) ? [] : ['the track was closed into an area'];
    candidates.push({ name: childText(element, 'name'), ring: points, notes });
  };
  for (const track of byName(doc, 'trk')) add(track, gpxPoints(byName(track, 'trkpt')));
  for (const route of byName(doc, 'rte')) add(route, gpxPoints(byName(route, 'rtept')));
  return candidates;
}

// --- rings ---------------------------------------------------------------------------------

/** Ends within about 1 m of each other. */
function closedEnough(points: LonLat[]): boolean {
  const first = points[0];
  const last = points.at(-1);
  if (!first || !last || points.length < 4) return false;
  return Math.abs(first[0] - last[0]) < 1e-5 && Math.abs(first[1] - last[1]) < 1e-5;
}

function same(a: LonLat, b: LonLat): boolean {
  return a[0] === b[0] && a[1] === b[1];
}

/** Metres east and north of `origin` (equirectangular; fine over a search area). */
function local(origin: LonLat, p: LonLat): [number, number] {
  const k = (Math.PI / 180) * 6_371_000;
  return [(p[0] - origin[0]) * k * Math.cos((origin[1] * Math.PI) / 180), (p[1] - origin[1]) * k];
}

function distanceToSegment(p: [number, number], a: [number, number], b: [number, number]): number {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const length2 = dx * dx + dy * dy;
  const t =
    length2 === 0
      ? 0
      : Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2));
  return Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy));
}

/** Douglas-Peucker on an open path; keeps both ends. */
function simplifyPath(points: LonLat[], tolerance_m: number, origin: LonLat): LonLat[] {
  if (points.length <= 2) return points;
  const xy = points.map((p) => local(origin, p));
  const keep = new Array<boolean>(points.length).fill(false);
  keep[0] = true;
  keep[points.length - 1] = true;
  const stack: [number, number][] = [[0, points.length - 1]];
  while (stack.length > 0) {
    const [first, last] = stack.pop() ?? [0, 0];
    let worst = -1;
    let index = -1;
    for (let i = first + 1; i < last; i += 1) {
      const d = distanceToSegment(xy[i] ?? [0, 0], xy[first] ?? [0, 0], xy[last] ?? [0, 0]);
      if (d > worst) {
        worst = d;
        index = i;
      }
    }
    if (index >= 0 && worst > tolerance_m) {
      keep[index] = true;
      stack.push([first, index], [index, last]);
    }
  }
  return points.filter((_, i) => keep[i]);
}

/** Distinct vertices of a closed ring (without the closing repeat). */
function distinct(ring: LonLat[]): LonLat[] {
  const out: LonLat[] = [];
  for (const p of ring) {
    const previous = out.at(-1);
    if (!previous || !same(previous, p)) out.push(p);
  }
  const first = out[0];
  const last = out.at(-1);
  if (out.length > 1 && first && last && same(first, last)) out.pop();
  return out;
}

export function cleanRing(ring: LonLat[]): { ring: LonLat[]; notes: string[] } | null {
  let vertices = distinct(ring);
  if (vertices.length < 3) return null;
  for (const [lon, lat] of vertices) {
    if (lon < -180 || lon > 180 || lat < -90 || lat > 90) {
      throw new ImportError('A position is outside WGS84 longitude/latitude ranges.');
    }
  }
  const notes: string[] = [];
  if (vertices.length > MAX_VERTICES) {
    const before = vertices.length;
    const origin = vertices[0] ?? [0, 0];
    let tolerance = 1;
    let simplified = vertices;
    while (simplified.length > MAX_VERTICES) {
      // Simplify the closed ring as a path that starts and ends at its first vertex.
      simplified = simplifyPath([...vertices, origin], tolerance, origin).slice(0, -1);
      tolerance *= 1.5;
    }
    vertices = simplified;
    notes.push(
      `simplified from ${String(before)} to ${String(vertices.length)} vertices (within ${(tolerance / 1.5).toFixed(0)} m)`,
    );
  }
  const first = vertices[0];
  if (!first) return null;
  return { ring: [...vertices, first], notes };
}
