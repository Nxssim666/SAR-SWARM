// What the planning panels show on the map (ADR 0028): the incident's search areas, the
// area or route being drawn, a pattern's datum, a plan preview or the saved plan, and the
// coverage of the mission being watched. Panels write it; the map draws it outside React.
import { create } from 'zustand';

import type { PlannedTask, SearchAreaOut, WaypointIn } from '../api/types';

export type LonLat = [number, number];

export interface PoiDraft {
  latitude: number;
  longitude: number;
}

interface PlanningState {
  areas: SearchAreaOut[];
  /** The area the mission panel works on (highlighted). */
  activeAreaId: string | null;
  /** A polygon just drawn on the map, waiting to be saved as a search area. */
  drawnRing: LonLat[] | null;
  /** The waypoint mission being edited (altitudes above home, ADR 0014). */
  waypoints: WaypointIn[];
  /** Default altitude above home for waypoints added by clicking the map. */
  waypointAltitude: number;
  /** Datum of an expanding-square or sector search. */
  datum: { latitude: number; longitude: number } | null;
  /** Routes of a plan preview or of the saved plan. */
  routes: PlannedTask[];
  /** Where the mission's aircraft have searched (GeoJSON geometry from the progress API). */
  coverage: GeoJSON.Geometry | null;
  /** A point clicked with the POI tool, waiting for its kind and notes. */
  poiDraft: PoiDraft | null;
  setAreas: (areas: SearchAreaOut[]) => void;
  setActiveArea: (id: string | null) => void;
  setDrawnRing: (ring: LonLat[] | null) => void;
  setWaypoints: (waypoints: WaypointIn[]) => void;
  addWaypoint: (latitude: number, longitude: number) => void;
  setWaypointAltitude: (altitude: number) => void;
  setDatum: (datum: PlanningState['datum']) => void;
  setRoutes: (routes: PlannedTask[]) => void;
  setCoverage: (coverage: GeoJSON.Geometry | null) => void;
  setPoiDraft: (draft: PoiDraft | null) => void;
}

export const usePlanning = create<PlanningState>()((set) => ({
  areas: [],
  activeAreaId: null,
  drawnRing: null,
  waypoints: [],
  waypointAltitude: 40,
  datum: null,
  routes: [],
  coverage: null,
  poiDraft: null,
  setAreas: (areas) => {
    set({ areas });
  },
  setActiveArea: (activeAreaId) => {
    set({ activeAreaId });
  },
  setDrawnRing: (drawnRing) => {
    set({ drawnRing });
  },
  setWaypoints: (waypoints) => {
    set({ waypoints });
  },
  addWaypoint: (latitude, longitude) => {
    set((s) => ({
      waypoints: [
        ...s.waypoints,
        { latitude, longitude, altitude_relative_m: s.waypointAltitude, speed_mps: null },
      ],
    }));
  },
  setWaypointAltitude: (waypointAltitude) => {
    set({ waypointAltitude });
  },
  setDatum: (datum) => {
    set({ datum });
  },
  setRoutes: (routes) => {
    set({ routes });
  },
  setCoverage: (coverage) => {
    set({ coverage });
  },
  setPoiDraft: (poiDraft) => {
    set({ poiDraft });
  },
}));

/** Distinct colours for the aircraft of a plan, in task order (with the dashes, below). */
export const ROUTE_COLORS = ['#58a6ff', '#f778ba', '#56d364', '#e3b341', '#a371f7', '#39c5cf'];
