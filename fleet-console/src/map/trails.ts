// Recent track of each aircraft, kept outside React: one point per new sample, at most
// MAX_POINTS (about a minute at 5 Hz).
import type { LonLat } from '../selection/geometry';

export const MAX_POINTS = 300;

export class Trails {
  private readonly points = new Map<string, LonLat[]>();
  private readonly lastStamp = new Map<string, string>();

  /** Add a position if it comes from a sample not seen before. */
  add(id: string, position: LonLat, stamp: string): void {
    if (this.lastStamp.get(id) === stamp) return;
    this.lastStamp.set(id, stamp);
    const trail = this.points.get(id) ?? [];
    trail.push(position);
    if (trail.length > MAX_POINTS) trail.splice(0, trail.length - MAX_POINTS);
    this.points.set(id, trail);
  }

  /** Forget aircraft that are gone. */
  retain(ids: ReadonlySet<string>): void {
    for (const id of [...this.points.keys()]) {
      if (!ids.has(id)) {
        this.points.delete(id);
        this.lastStamp.delete(id);
      }
    }
  }

  size(id: string): number {
    return this.points.get(id)?.length ?? 0;
  }

  collection(color: (id: string) => string): GeoJSON.FeatureCollection {
    const features: GeoJSON.Feature[] = [];
    for (const [id, trail] of this.points) {
      if (trail.length < 2) continue;
      features.push({
        type: 'Feature',
        geometry: { type: 'LineString', coordinates: trail },
        properties: { id, color: color(id) },
      });
    }
    return { type: 'FeatureCollection', features };
  }
}
