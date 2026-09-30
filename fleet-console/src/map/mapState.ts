// Map state that React components show: the cursor's position, the goto target being
// chosen, the coordinate format, and whether a basemap is loaded.
import { create } from 'zustand';

import type { CoordFormat } from './coords';

export type BasemapStatus = 'loading' | 'loaded' | 'none';

interface MapState {
  cursor: { latitude: number; longitude: number } | null;
  gotoTarget: { latitude: number; longitude: number } | null;
  format: CoordFormat;
  basemap: BasemapStatus;
  setCursor: (cursor: MapState['cursor']) => void;
  setGotoTarget: (target: MapState['gotoTarget']) => void;
  setFormat: (format: CoordFormat) => void;
  setBasemap: (status: BasemapStatus) => void;
}

const FORMAT_KEY = 'sargcs.coordFormat';

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
}));
