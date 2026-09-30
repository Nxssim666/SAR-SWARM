// Which aircraft lie inside a drawn box or lasso. Positions are [longitude, latitude]; over
// the few kilometres an operator draws, a planar test in degrees is accurate enough.

export type LonLat = [number, number];

/** Even-odd ray casting; points on an edge may fall either way. */
export function pointInPolygon(point: LonLat, ring: LonLat[]): boolean {
  const [x, y] = point;
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i, i += 1) {
    const a = ring[i];
    const b = ring[j];
    if (!a || !b) continue;
    const [xi, yi] = a;
    const [xj, yj] = b;
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** The ids of the positions inside the polygon's outer ring. */
export function idsInside(positions: Map<string, LonLat>, ring: LonLat[]): string[] {
  if (ring.length < 3) return [];
  return [...positions].filter(([, p]) => pointInPolygon(p, ring)).map(([id]) => id);
}
