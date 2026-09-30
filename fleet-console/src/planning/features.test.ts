import { describe, expect, it } from 'vitest';

import type { GeofenceOut, PlannedTask, SearchAreaOut } from '../api/types';
import { poi, T0 } from '../test/fixtures';
import {
  areaFeatures,
  fenceFeatures,
  POI_STYLE,
  poiFeatures,
  ringFeature,
  routeFeatures,
  routeStyle,
  waypointFeatures,
} from './features';

function area(id: string, status: SearchAreaOut['status'] = 'unassigned'): SearchAreaOut {
  return {
    id,
    incident_id: 'i1',
    name: `Area ${id}`,
    geometry: {
      type: 'Polygon',
      coordinates: [
        [
          [8.54, 47.39],
          [8.55, 47.39],
          [8.55, 47.4],
          [8.54, 47.39],
        ],
      ],
    },
    area_m2: 1000,
    priority: 1,
    status,
    notes: null,
    created_at: T0,
    updated_at: T0,
  };
}

function task(id: string, points: number): PlannedTask {
  return {
    aircraft_id: id,
    callsign: id.toUpperCase(),
    airframe: 'multirotor_hexa',
    companion: false,
    layer_m: 40,
    speed_mps: 10,
    start_delay_s: 0,
    strip_area_m2: null,
    length_m: 100,
    duration_s: 10,
    fallback: false,
    infeasible_turns: 0,
    notes: [],
    waypoints: Array.from({ length: points }, (_, i) => ({
      latitude: 47.39 + i * 0.001,
      longitude: 8.54,
      altitude_relative_m: 40,
      speed_mps: null,
      loiter_s: null,
    })),
  };
}

/** A feature's properties, typed for assertions. */
function props(f: GeoJSON.Feature | undefined): Record<string, unknown> {
  return f?.properties ?? {};
}

describe('planning features', () => {
  it('labels areas with their name and status, and marks the active one', () => {
    const features = areaFeatures([area('a'), area('b', 'searched')], 'b').features;

    expect(features.map(props)).toEqual([
      { id: 'a', label: 'Area a (unassigned)', status: 'unassigned', active: false },
      { id: 'b', label: 'Area b (searched)', status: 'searched', active: true },
    ]);
  });

  it('draws one line per planned aircraft, telling them apart by colour and dash', () => {
    const lines = routeFeatures([task('a1', 3), task('a2', 1), task('a3', 2)]).features;

    // a2's single point is not a line; the others keep their task index for their style.
    expect(lines.map((f) => props(f).index)).toEqual([0, 2]);
    expect(routeStyle(0).dash).not.toEqual(routeStyle(1).dash);
    expect(routeStyle(0).color).not.toEqual(routeStyle(1).color);
  });

  it('numbers edited waypoints and shows their height above home', () => {
    const collection = waypointFeatures([
      { latitude: 47.39, longitude: 8.54, altitude_relative_m: 40 },
      { latitude: 47.4, longitude: 8.54, altitude_relative_m: 55 },
    ]);

    expect(collection.features[0]?.geometry.type).toBe('LineString');
    expect(collection.features.slice(1).map((f) => props(f).label)).toEqual([
      '1 · 40 m',
      '2 · 55 m',
    ]);
  });

  it('gives every point-of-interest kind its own shape, and draws closed ones hollow', () => {
    const shapes = new Set(Object.values(POI_STYLE).map((s) => s.shape));
    expect(shapes.size).toBe(Object.keys(POI_STYLE).length);

    const features = poiFeatures(
      [
        poi('p1', { kind: 'survivor_sighting' }),
        poi('p2', { status: 'dismissed' }),
        poi('other', { incident_id: 'i2' }),
      ],
      'i1',
    ).features;

    expect(features.map((f) => props(f).id)).toEqual(['p1', 'p2']);
    expect(props(features[0])).toMatchObject({ icon: 'poi-diamond', critical: true });
    expect(props(features[1])).toMatchObject({ icon: 'poi-circle-hollow', opacity: 0.5 });
  });

  it('draws a ring only once it has three points', () => {
    expect(ringFeature([[8.54, 47.39]]).features).toHaveLength(0);
    expect(
      ringFeature([
        [8.54, 47.39],
        [8.55, 47.39],
        [8.55, 47.4],
      ]).features,
    ).toHaveLength(1);
  });
});

describe('geofences on the map', () => {
  const fence = (name: string, kind: GeofenceOut['kind'], enabled: boolean): GeofenceOut => ({
    id: name,
    incident_id: 'i1',
    name,
    kind,
    geometry: {
      type: 'Polygon',
      coordinates: [
        [
          [8.5, 47.3],
          [8.6, 47.3],
          [8.6, 47.4],
          [8.5, 47.3],
        ],
      ],
    },
    max_altitude_relative_m: null,
    enabled,
    created_at: T0,
    updated_at: T0,
  });

  it('marks exclusion zones and says when a fence is off', () => {
    const features = fenceFeatures([
      fence('Power line', 'exclusion', true),
      fence('Search box', 'inclusion', false),
    ]).features;

    expect(features.map((f) => f.properties)).toEqual([
      { id: 'Power line', kind: 'exclusion', enabled: true, label: '⛔ Power line' },
      { id: 'Search box', kind: 'inclusion', enabled: false, label: 'Search box (off)' },
    ]);
  });
});
