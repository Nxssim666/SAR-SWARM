// GeoJSON for the planning layers of the map. Pure, so the symbology is tested without a map.
// Like the aircraft (ADR 0027), nothing is told by colour alone: areas carry their name and
// status as text, routes a dash pattern per aircraft, points of interest a shape per kind.
import type {
  PlannedTask,
  PoiKind,
  PoiStatus,
  PoiView,
  SearchAreaOut,
  WaypointIn,
} from '../api/types';
import { ROUTE_COLORS } from './store';

type Collection = GeoJSON.FeatureCollection;

export const EMPTY: Collection = { type: 'FeatureCollection', features: [] };

const AREA_STATUS_LABEL: Record<SearchAreaOut['status'], string> = {
  unassigned: 'unassigned',
  assigned: 'assigned',
  in_progress: 'in progress',
  searched: 'searched',
};

export function areaFeatures(areas: readonly SearchAreaOut[], activeId: string | null): Collection {
  return {
    type: 'FeatureCollection',
    features: areas.map((a) => ({
      type: 'Feature',
      geometry: a.geometry,
      properties: {
        id: a.id,
        label: `${a.name} (${AREA_STATUS_LABEL[a.status]})`,
        status: a.status,
        active: a.id === activeId,
      },
    })),
  };
}

/** Dash patterns, one per aircraft (after the colours): lines differ without colour too. */
const DASHES = [
  [1, 0],
  [4, 2],
  [1, 1.5],
  [6, 2, 1, 2],
];

export function routeStyle(index: number): { color: string; dash: number[] } {
  return {
    color: ROUTE_COLORS[index % ROUTE_COLORS.length] ?? '#58a6ff',
    dash: DASHES[index % DASHES.length] ?? [1, 0],
  };
}

export function routeFeatures(tasks: readonly PlannedTask[]): Collection {
  const features: GeoJSON.Feature[] = [];
  tasks.forEach((task, index) => {
    const coordinates = task.waypoints.map((w) => [w.longitude, w.latitude]);
    if (coordinates.length < 2) return;
    const { color } = routeStyle(index);
    features.push({
      type: 'Feature',
      geometry: { type: 'LineString', coordinates },
      properties: { id: task.aircraft_id, callsign: task.callsign, color, index },
    });
  });
  return { type: 'FeatureCollection', features };
}

/** The waypoint route being edited: the line, and each point with its number and height. */
export function waypointFeatures(waypoints: readonly WaypointIn[]): Collection {
  const features: GeoJSON.Feature[] = waypoints.map((w, i) => ({
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [w.longitude, w.latitude] },
    properties: { seq: i + 1, label: `${String(i + 1)} · ${String(w.altitude_relative_m)} m` },
  }));
  if (waypoints.length >= 2) {
    features.unshift({
      type: 'Feature',
      geometry: {
        type: 'LineString',
        coordinates: waypoints.map((w) => [w.longitude, w.latitude]),
      },
      properties: {},
    });
  }
  return { type: 'FeatureCollection', features };
}

export type PoiShape = 'diamond' | 'circle' | 'square' | 'triangle';

/** Each kind its own shape and colour; a survivor sighting stands out most. */
export const POI_STYLE: Record<PoiKind, { shape: PoiShape; color: string; word: string }> = {
  survivor_sighting: { shape: 'diamond', color: '#ff5f56', word: 'Survivor sighting' },
  poi: { shape: 'circle', color: '#58a6ff', word: 'Point of interest' },
  clue: { shape: 'square', color: '#e3b341', word: 'Clue' },
  hazard: { shape: 'triangle', color: '#f0883e', word: 'Hazard' },
};

/** Closed points (dismissed, resolved) are drawn hollow and faded: still on record. */
export function poiOpen(status: PoiStatus): boolean {
  return status === 'new' || status === 'confirmed';
}

export function poiIconId(shape: PoiShape, filled: boolean): string {
  return `poi-${shape}${filled ? '' : '-hollow'}`;
}

export function poiFeatures(pois: readonly PoiView[], incidentId: string | null): Collection {
  return {
    type: 'FeatureCollection',
    features: pois
      .filter((p) => incidentId === null || p.incident_id === incidentId)
      .map((p) => {
        const style = POI_STYLE[p.kind];
        const open = poiOpen(p.status);
        return {
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [p.longitude, p.latitude] },
          properties: {
            id: p.id,
            icon: poiIconId(style.shape, open),
            color: style.color,
            opacity: open ? 1 : 0.5,
            label: `${style.word} (${p.status})`,
            critical: p.kind === 'survivor_sighting' && p.status === 'new',
          },
        };
      }),
  };
}

export function pointFeature(point: { latitude: number; longitude: number } | null): Collection {
  if (!point) return EMPTY;
  return {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [point.longitude, point.latitude] },
        properties: {},
      },
    ],
  };
}

export function ringFeature(ring: readonly [number, number][] | null): Collection {
  if (!ring || ring.length < 3) return EMPTY;
  return {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        geometry: { type: 'Polygon', coordinates: [ring.map(([x, y]) => [x, y])] },
        properties: {},
      },
    ],
  };
}

export function geometryFeature(geometry: GeoJSON.Geometry | null): Collection {
  if (!geometry) return EMPTY;
  return { type: 'FeatureCollection', features: [{ type: 'Feature', geometry, properties: {} }] };
}
