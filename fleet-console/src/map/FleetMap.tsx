// The fleet map (ADR 0006, ADR 0027). MapLibre draws everything as native layers fed by
// GeoJSON sources; live state is read outside React and pushed at most once per animation
// frame, so 50 aircraft at 10 Hz never re-render React.
import 'maplibre-gl/dist/maplibre-gl.css';

import * as maplibregl from 'maplibre-gl';
// MapLibre builds its worker's URL at run time, which the production build cannot see: bundle
// the worker explicitly (with its shared chunk) and tell MapLibre where it is.
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import type { GeoJSONSource, Map as MapLibreMap } from 'maplibre-gl';
import { Protocol } from 'pmtiles';
import { useEffect, useRef } from 'react';
import {
  TerraDraw,
  TerraDrawFreehandMode,
  TerraDrawPolygonMode,
  TerraDrawRectangleMode,
} from 'terra-draw';
import { TerraDrawMapLibreGLAdapter } from 'terra-draw-maplibre-gl-adapter';

import { useIncident } from '../incident/store';
import { useLive } from '../live/store';
import { usePlanning } from '../planning/store';
import { idsInside, type LonLat } from '../selection/geometry';
import { modeFor, useSelection } from '../selection/store';
import { BACKGROUND, loadBasemap } from './basemap';
import { drawIcon, ICON_PIXEL_RATIO } from './icons';
import { useMapState } from './mapState';
import { addPlanningLayers, drawPlanning } from './planningLayers';
import { aircraftProps, iconId, LINK_COLOR } from './symbology';
import { Trails } from './trails';

const START_CENTER: [number, number] = [8.5456, 47.3977]; // the simulator's site
const START_ZOOM = 13;
const TRAIL_UPDATE_MS = 500; // trails change slowly; re-tiling them 10 times a second costs frames
let protocolAdded = false;
maplibregl.setWorkerUrl(maplibreWorkerUrl);

type Collection = GeoJSON.FeatureCollection;
const EMPTY: Collection = { type: 'FeatureCollection', features: [] };

function source(map: MapLibreMap, id: string): GeoJSONSource | undefined {
  return map.getSource<GeoJSONSource>(id);
}

function addLayers(map: MapLibreMap, labels: boolean): void {
  for (const id of ['trails', 'homes', 'aircraft', 'goto']) {
    map.addSource(id, { type: 'geojson', data: EMPTY });
  }
  for (const kind of ['fixed-wing', 'multirotor'] as const) {
    for (const shape of ['solid', 'hollow', 'crossed'] as const) {
      for (const heading of [true, false]) {
        map.addImage(iconId(kind, shape, heading), drawIcon(kind, shape, heading), {
          sdf: true,
          pixelRatio: ICON_PIXEL_RATIO,
        });
      }
    }
  }
  map.addLayer({
    id: 'trails',
    type: 'line',
    source: 'trails',
    paint: { 'line-color': ['get', 'color'], 'line-width': 2, 'line-opacity': 0.55 },
  });
  map.addLayer({
    id: 'homes',
    type: 'circle',
    source: 'homes',
    paint: {
      'circle-radius': 5,
      'circle-color': 'rgba(0,0,0,0)',
      'circle-stroke-color': '#c9d1d9',
      'circle-stroke-width': 2,
    },
  });
  map.addLayer({
    id: 'selection',
    type: 'circle',
    source: 'aircraft',
    filter: ['==', ['get', 'selected'], true],
    paint: {
      'circle-radius': 20,
      'circle-color': 'rgba(88,166,255,0.18)',
      'circle-stroke-color': '#58a6ff',
      'circle-stroke-width': 2,
    },
  });
  map.addLayer({
    id: 'owners',
    type: 'circle',
    source: 'aircraft',
    filter: ['!=', ['get', 'owner'], ''],
    paint: {
      'circle-radius': 15,
      'circle-color': 'rgba(0,0,0,0)',
      'circle-stroke-color': ['get', 'owner'],
      'circle-stroke-width': 2.5,
    },
  });
  map.addLayer({
    id: 'aircraft',
    type: 'symbol',
    source: 'aircraft',
    layout: {
      'icon-image': ['get', 'icon'],
      'icon-rotate': ['get', 'heading'],
      'icon-rotation-alignment': 'map',
      'icon-allow-overlap': true,
      'icon-ignore-placement': true,
    },
    paint: {
      'icon-color': ['get', 'color'],
      'icon-halo-color': '#0d1117',
      'icon-halo-width': 1.5,
    },
  });
  if (labels) {
    map.addLayer({
      id: 'labels',
      type: 'symbol',
      source: 'aircraft',
      layout: {
        'text-field': ['get', 'callsign'],
        'text-font': ['Noto Sans Medium'],
        'text-size': 12,
        'text-offset': [0, 1.6],
        'text-anchor': 'top',
        'text-optional': true, // labels give way when aircraft are close; icons never do
      },
      paint: { 'text-color': '#e6edf3', 'text-halo-color': '#0d1117', 'text-halo-width': 1.5 },
    });
  }
  map.addLayer({
    id: 'goto',
    type: 'circle',
    source: 'goto',
    paint: {
      'circle-radius': 9,
      'circle-color': 'rgba(0,0,0,0)',
      'circle-stroke-color': '#f0f6fc',
      'circle-stroke-width': 3,
    },
  });
}

/** Test hook (E2E): screen position of a coordinate, enabled by localStorage sargcs.test=1. */
function exposeForTests(map: MapLibreMap): void {
  try {
    if (localStorage.getItem('sargcs.test') !== '1') return;
  } catch {
    return;
  }
  (window as unknown as Record<string, unknown>).__sargcsProject = (lon: number, lat: number) => {
    const point = map.project([lon, lat]);
    const box = map.getContainer().getBoundingClientRect();
    return { x: box.left + point.x, y: box.top + point.y };
  };
}

export function FleetMap() {
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = container.current;
    if (!element) return;
    let disposed = false;
    let map: MapLibreMap | null = null;
    let draw: TerraDraw | null = null;
    const cleanups: (() => void)[] = [];

    void loadBasemap().then((basemap) => {
      if (disposed) return;
      if (!protocolAdded) {
        maplibregl.addProtocol('pmtiles', new Protocol().tile);
        protocolAdded = true;
      }
      useMapState.getState().setBasemap(basemap.available ? 'loaded' : 'none');
      const m = new maplibregl.Map({
        container: element,
        style: basemap.style,
        center: START_CENTER,
        zoom: START_ZOOM,
        attributionControl: { compact: false },
        dragRotate: false,
        pitchWithRotate: false,
      });
      map = m;
      m.getCanvas().style.background = BACKGROUND;
      m.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left');
      m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');

      const trails = new Trails();
      let frame = 0;
      let fitted = false;
      const positions = new Map<string, LonLat>();
      // The click that closes a box or lasso also reaches the map: it must not select again.
      let drawingFinishedAt = 0;
      let trailsDrawnAt = 0;

      const redraw = () => {
        frame = 0;
        const { aircraft } = useLive.getState();
        const { selected } = useSelection.getState();
        const features: GeoJSON.Feature[] = [];
        const homes: GeoJSON.Feature[] = [];
        positions.clear();
        for (const a of Object.values(aircraft)) {
          const drawn = aircraftProps(a, selected.has(a.aircraft_id));
          if (drawn) {
            positions.set(a.aircraft_id, drawn.position);
            features.push({
              type: 'Feature',
              geometry: { type: 'Point', coordinates: drawn.position },
              properties: drawn.props,
            });
            trails.add(a.aircraft_id, drawn.position, a.telemetry?.ts ?? '');
          }
          const home = a.telemetry?.home;
          if (home) {
            homes.push({
              type: 'Feature',
              geometry: { type: 'Point', coordinates: [home.longitude, home.latitude] },
              properties: { id: a.aircraft_id },
            });
          }
        }
        trails.retain(new Set(Object.keys(aircraft)));
        void source(m, 'aircraft')?.setData({ type: 'FeatureCollection', features });
        void source(m, 'homes')?.setData({ type: 'FeatureCollection', features: homes });
        const now = performance.now();
        if (now - trailsDrawnAt >= TRAIL_UPDATE_MS) {
          trailsDrawnAt = now;
          void source(m, 'trails')?.setData(
            trails.collection((id) => LINK_COLOR[aircraft[id]?.link ?? 'offline']),
          );
        }
        const target = useMapState.getState().gotoTarget;
        void source(m, 'goto')?.setData(
          target
            ? {
                type: 'FeatureCollection',
                features: [
                  {
                    type: 'Feature',
                    geometry: { type: 'Point', coordinates: [target.longitude, target.latitude] },
                    properties: {},
                  },
                ],
              }
            : EMPTY,
        );
        if (!fitted && positions.size > 0) {
          fitted = true;
          const bounds = new maplibregl.LngLatBounds();
          for (const p of positions.values()) bounds.extend(p);
          m.fitBounds(bounds, { padding: 80, maxZoom: 18, duration: 0 });
        }
      };
      const schedule = () => {
        if (frame === 0) frame = requestAnimationFrame(redraw);
      };

      // POI icons the basemap's sprite lacks: a blank image instead of a warning per tile.
      m.on('styleimagemissing', (event: { id: string }) => {
        if (!m.hasImage(event.id))
          m.addImage(event.id, { width: 1, height: 1, data: new Uint8Array(4) });
      });

      m.on('load', () => {
        addLayers(m, basemap.glyphs);
        addPlanningLayers(m, basemap.glyphs, 'trails');
        exposeForTests(m);
        schedule();
        cleanups.push(useLive.subscribe(schedule));
        cleanups.push(useSelection.subscribe(schedule));
        cleanups.push(useMapState.subscribe(schedule));

        // Planning layers change at human speed: redraw them only when their state changes.
        drawPlanning(m);
        cleanups.push(
          usePlanning.subscribe(() => {
            drawPlanning(m);
          }),
        );
        cleanups.push(
          useIncident.subscribe(() => {
            drawPlanning(m);
          }),
        );
        cleanups.push(
          useLive.subscribe((state, prev) => {
            if (state.pois !== prev.pois) drawPlanning(m);
          }),
        );
        const center = () => {
          const c = m.getCenter();
          useMapState.getState().setCenter({ latitude: c.lat, longitude: c.lng });
        };
        center();
        m.on('moveend', center);
        cleanups.push(
          useMapState.subscribe((state) => {
            if (!state.focus) return;
            const [west, south, east, north] = state.focus;
            fitted = true; // an operator's request wins over the first fit to the fleet
            m.fitBounds(
              [
                [west, south],
                [east, north],
              ],
              { padding: 60, maxZoom: 17, duration: 300 },
            );
            useMapState.getState().showBounds(null);
          }),
        );

        // Box and lasso selection (terra-draw), and picking a goto target.
        const td = new TerraDraw({
          adapter: new TerraDrawMapLibreGLAdapter({ map: m }),
          modes: [
            new TerraDrawRectangleMode(),
            new TerraDrawFreehandMode(),
            new TerraDrawPolygonMode(),
          ],
        });
        draw = td;
        td.start();
        td.on('finish', (id) => {
          drawingFinishedAt = performance.now();
          const feature = td.getSnapshotFeature(id);
          td.clear();
          const geometry = feature?.geometry;
          if (geometry?.type === 'Polygon') {
            const ring = (geometry.coordinates[0] ?? []) as LonLat[];
            if (useSelection.getState().tool === 'area') {
              usePlanning.getState().setDrawnRing(ring);
            } else {
              useSelection.getState().select(idsInside(positions, ring));
            }
          }
          useSelection.getState().setTool('pan');
        });
        const applyTool = () => {
          const { tool } = useSelection.getState();
          const modes: Partial<Record<typeof tool, string>> = {
            box: 'rectangle',
            lasso: 'freehand',
            area: 'polygon',
          };
          td.setMode(modes[tool] ?? 'static');
          m.getCanvas().style.cursor = tool === 'pan' ? '' : 'crosshair';
        };
        applyTool();
        cleanups.push(
          useSelection.subscribe((s, prev) => {
            if (s.tool !== prev.tool) applyTool();
          }),
        );
      });

      m.on('click', 'aircraft', (event) => {
        if (useSelection.getState().tool !== 'pan') return;
        if (performance.now() - drawingFinishedAt < 500) return;
        const id = event.features?.[0]?.properties.id as string | undefined;
        if (id) useSelection.getState().select([id], modeFor(event.originalEvent));
      });
      m.on('click', (event) => {
        const { tool, setTool } = useSelection.getState();
        const point = { latitude: event.lngLat.lat, longitude: event.lngLat.lng };
        const planning = usePlanning.getState();
        switch (tool) {
          case 'goto':
            useMapState.getState().setGotoTarget(point);
            setTool('pan');
            return;
          case 'waypoint': // stays on: click after click adds the route
            planning.addWaypoint(point.latitude, point.longitude);
            return;
          case 'datum':
            planning.setDatum(point);
            setTool('pan');
            return;
          case 'poi':
            planning.setPoiDraft(point);
            setTool('pan');
            return;
          default:
            return;
        }
      });
      m.on('mouseenter', 'aircraft', () => {
        if (useSelection.getState().tool === 'pan') m.getCanvas().style.cursor = 'pointer';
      });
      m.on('mouseleave', 'aircraft', () => {
        if (useSelection.getState().tool === 'pan') m.getCanvas().style.cursor = '';
      });
      m.on('mousemove', (event) => {
        useMapState
          .getState()
          .setCursor({ latitude: event.lngLat.lat, longitude: event.lngLat.lng });
      });
      m.on('mouseout', () => {
        useMapState.getState().setCursor(null);
      });
      cleanups.push(() => {
        if (frame !== 0) cancelAnimationFrame(frame);
      });
    });

    return () => {
      disposed = true;
      for (const cleanup of cleanups) cleanup();
      draw?.stop();
      map?.remove();
    };
  }, []);

  return <div ref={container} className="map" data-testid="fleet-map" aria-label="Fleet map" />;
}
