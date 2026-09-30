// Map state that React components show: the cursor's position, the goto target being
// chosen, the coordinate format, whether a basemap is loaded, the satellite view, the view's
// centre, and a request to show an area (components ask; the map moves).
import { create } from 'zustand';

import type { ImageryInfo } from './basemap';
import type { CoordFormat } from './coords';

/** `unavailable`: the map itself could not start (no WebGL in this browser). */
export type BasemapStatus = 'loading' | 'loaded' | 'none' | 'unavailable';

/** [west, south, east, north] in degrees. */
export type Bounds = [number, number, number, number];

interface MapState {
  cursor: { latitude: number; longitude: number } | null;
  gotoTarget: { latitude: number; longitude: number } | null;
  format: CoordFormat;
  basemap: BasemapStatus;
  /** Regions with satellite imagery on this station (empty: no satellite view). */
  imagery: ImageryInfo[];
  /** Show the satellite imagery instead of the map's fills and roads. */
  satellite: boolean;
  center: { latitude: number; longitude: number } | null;
  /** An area the map should show; the map clears it once it has moved. */
  focus: Bounds | null;
  setCursor: (cursor: MapState['cursor']) => void;
  setGotoTarget: (target: MapState['gotoTarget']) => void;
  setFormat: (format: CoordFormat) => void;
  setBasemap: (status: BasemapStatus) => void;
  setImagery: (imagery: ImageryInfo[]) => void;
  setSatellite: (satellite: boolean) => void;
  setCenter: (center: MapState['center']) => void;
  showBounds: (bounds: Bounds | null) => void;
}

const FORMAT_KEY = 'sargcs.coordFormat';
const SATELLITE_KEY = 'sargcs.satellite';

/** The operator's last choice; the satellite view by default (shown where there is imagery). */
function storedSatellite(): boolean {
  try {
    return localStorage.getItem(SATELLITE_KEY) !== '0';
  } catch {
    return true;
  }
}

function storedFormat(): CoordFormat {
  try {
    const value = localStorage.getItem(FORMAT_KEY);
    return value === 'ddm' || value === 'mgrs' ? value : 'dd';
  } catch {
    return 'dd';
  }
}

export const useMapState = create<MapState>()((set) => ({
  cursor: null,
  gotoTarget: null,
  format: storedFormat(),
  basemap: 'loading',
  imagery: [],
  satellite: storedSatellite(),
  center: null,
  focus: null,
  setCursor: (cursor) => {
    set({ cursor });
  },
  setGotoTarget: (gotoTarget) => {
    set({ gotoTarget });
  },
  setFormat: (format) => {
    try {
      localStorage.setItem(FORMAT_KEY, format); // a display preference, not a secret
    } catch {
      // storage unavailable: the choice lasts until reload
    }
    set({ format });
  },
  setBasemap: (basemap) => {
    set({ basemap });
  },
  setImagery: (imagery) => {
    set({ imagery });
  },
  setSatellite: (satellite) => {
    try {
      localStorage.setItem(SATELLITE_KEY, satellite ? '1' : '0'); // a display preference
    } catch {
      // storage unavailable: the choice lasts until reload
    }
    set({ satellite });
  },
  setCenter: (center) => {
    set({ center });
  },
  showBounds: (focus) => {
    set({ focus });
  },
}));

/** Bounds of a list of [longitude, latitude] positions, or null when empty. */
export function boundsOf(positions: readonly (readonly [number, number])[]): Bounds | null {
  if (positions.length === 0) return null;
  let [west, south] = positions[0] ?? [0, 0];
  let [east, north] = [west, south];
  for (const [lon, lat] of positions) {
    west = Math.min(west, lon);
    east = Math.max(east, lon);
    south = Math.min(south, lat);
    north = Math.max(north, lat);
  }
  return [west, south, east, north];
}
