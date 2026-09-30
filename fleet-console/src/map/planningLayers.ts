// The map's planning layers (ADR 0028, ADR 0031): search areas, the area being drawn,
// coverage, planned routes, the waypoint route being edited, a datum, and points of
// interest. Added beneath the aircraft, so aircraft are never hidden; fed from the planning
// store and the live store's points of interest.
import type { GeoJSONSource, Map as MapLibreMap } from 'maplibre-gl';

import { useIncident } from '../incident/store';
import { useLive } from '../live/store';
import {
  areaFeatures,
  EMPTY,
  geometryFeature,
  POI_STYLE,
  poiFeatures,
  poiIconId,
  pointFeature,
  ringFeature,
  routeFeatures,
  routeStyle,
  waypointFeatures,
} from '../planning/features';
import { usePlanning } from '../planning/store';
import { drawPoiIcon, ICON_PIXEL_RATIO } from './icons';

const SOURCES = ['areas', 'drawn', 'coverage', 'routes', 'waypoints', 'datum', 'pois'] as const;

/** Add the planning layers below `beforeId` (the aircraft's first layer). */
export function addPlanningLayers(map: MapLibreMap, labels: boolean, beforeId: string): void {
  for (const id of SOURCES) map.addSource(id, { type: 'geojson', data: EMPTY });
  for (const { shape } of Object.values(POI_STYLE)) {
    for (const filled of [true, false]) {
      const id = poiIconId(shape, filled);
      if (!map.hasImage(id)) {
        map.addImage(id, drawPoiIcon(shape, filled), { sdf: true, pixelRatio: ICON_PIXEL_RATIO });
      }
    }
  }
  const add = (layer: Parameters<MapLibreMap['addLayer']>[0]) => {
    map.addLayer(layer, beforeId);
  };
  add({
    id: 'areas-fill',
    type: 'fill',
    source: 'areas',
    paint: {
      'fill-color': ['case', ['get', 'active'], '#58a6ff', '#8b98a5'],
      'fill-opacity': ['case', ['get', 'active'], 0.16, 0.07],
    },
  });
  add({
    id: 'areas-line',
    type: 'line',
    source: 'areas',
    paint: {
      'line-color': ['case', ['get', 'active'], '#58a6ff', '#c9d1d9'],
      'line-width': ['case', ['get', 'active'], 3, 1.5],
      'line-dasharray': [
        'case',
        ['==', ['get', 'status'], 'searched'],
        ['literal', [2, 2]],
        ['literal', [1, 0]],
      ],
    },
  });
  add({
    id: 'coverage',
    type: 'fill',
    source: 'coverage',
    paint: { 'fill-color': '#3fb950', 'fill-opacity': 0.28 },
  });
  add({
    id: 'drawn',
    type: 'line',
    source: 'drawn',
    paint: { 'line-color': '#f0f6fc', 'line-width': 2, 'line-dasharray': [3, 2] },
  });
  for (let index = 0; index < 4; index += 1) {
    // One layer per dash pattern: MapLibre cannot take line-dasharray from a feature.
    const { dash } = routeStyle(index);
    add({
      id: `routes-${String(index)}`,
      type: 'line',
      source: 'routes',
      filter: ['==', ['%', ['get', 'index'], 4], index],
      paint: { 'line-color': ['get', 'color'], 'line-width': 2.5, 'line-dasharray': dash },
    });
  }
  add({
    id: 'waypoints-line',
    type: 'line',
    source: 'waypoints',
    filter: ['==', ['geometry-type'], 'LineString'],
    paint: { 'line-color': '#f0f6fc', 'line-width': 2 },
  });
  add({
    id: 'waypoints',
    type: 'circle',
    source: 'waypoints',
    filter: ['==', ['geometry-type'], 'Point'],
    paint: {
      'circle-radius': 6,
      'circle-color': '#0d1117',
      'circle-stroke-color': '#f0f6fc',
      'circle-stroke-width': 2,
    },
  });
  add({
    id: 'datum',
    type: 'circle',
    source: 'datum',
    paint: {
      'circle-radius': 7,
      'circle-color': '#e3b341',
      'circle-stroke-color': '#0d1117',
      'circle-stroke-width': 2,
    },
  });
  add({
    id: 'pois',
    type: 'symbol',
    source: 'pois',
    layout: {
      'icon-image': ['get', 'icon'],
      'icon-size': ['case', ['get', 'critical'], 0.8, 0.6],
      'icon-allow-overlap': true,
      'icon-ignore-placement': true,
    },
    paint: {
      'icon-color': ['get', 'color'],
      'icon-opacity': ['get', 'opacity'],
      'icon-halo-color': '#0d1117',
      'icon-halo-width': 1.5,
    },
  });
  if (labels) {
    add({
      id: 'areas-label',
      type: 'symbol',
      source: 'areas',
      layout: {
        'text-field': ['get', 'label'],
        'text-font': ['Noto Sans Medium'],
        'text-size': 12,
      },
      paint: { 'text-color': '#c9d1d9', 'text-halo-color': '#0d1117', 'text-halo-width': 1.5 },
    });
    add({
      id: 'waypoints-label',
      type: 'symbol',
      source: 'waypoints',
      filter: ['==', ['geometry-type'], 'Point'],
      layout: {
        'text-field': ['get', 'label'],
        'text-font': ['Noto Sans Medium'],
        'text-size': 11,
        'text-offset': [0, 1.3],
        'text-anchor': 'top',
      },
      paint: { 'text-color': '#f0f6fc', 'text-halo-color': '#0d1117', 'text-halo-width': 1.5 },
    });
    add({
      id: 'pois-label',
      type: 'symbol',
      source: 'pois',
      layout: {
        'text-field': ['get', 'label'],
        'text-font': ['Noto Sans Medium'],
        'text-size': 11,
        'text-offset': [0, 1.4],
        'text-anchor': 'top',
        'text-optional': true,
      },
      paint: {
        'text-color': ['get', 'color'],
        'text-halo-color': '#0d1117',
        'text-halo-width': 1.5,
      },
    });
  }
}

/** Push the planning state to the map's sources (cheap: they change at human speed). */
export function drawPlanning(map: MapLibreMap): void {
  const p = usePlanning.getState();
  const set = (id: (typeof SOURCES)[number], data: GeoJSON.FeatureCollection) => {
    void map.getSource<GeoJSONSource>(id)?.setData(data);
  };
  set('areas', areaFeatures(p.areas, p.activeAreaId));
  set('drawn', ringFeature(p.drawnRing));
  set('coverage', geometryFeature(p.coverage));
  set('routes', routeFeatures(p.routes));
  set('waypoints', waypointFeatures(p.waypoints));
  set('datum', pointFeature(p.datum));
  set(
    'pois',
    poiFeatures(Object.values(useLive.getState().pois), useIncident.getState().incidentId),
  );
}
