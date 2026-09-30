// The operator's selection and the active map tool. Commands go to the selection, so its
// size is always shown (ADR 0027).
import { create } from 'zustand';

export type Tool =
  | 'pan'
  | 'box'
  | 'lasso'
  | 'goto'
  // planning (ADR 0028): draw a search area, add waypoints, pick a datum, mark a point
  | 'area'
  | 'waypoint'
  | 'datum'
  | 'poi';
export type SelectMode = 'replace' | 'add' | 'toggle';

interface SelectionState {
  selected: ReadonlySet<string>;
  tool: Tool;
  select: (ids: Iterable<string>, mode?: SelectMode) => void;
  clear: () => void;
  setTool: (tool: Tool) => void;
  /** Forget aircraft that no longer exist. */
  retain: (existing: ReadonlySet<string>) => void;
}

export const useSelection = create<SelectionState>()((set) => ({
  selected: new Set(),
  tool: 'pan',
  select: (ids, mode = 'replace') => {
    set((state) => {
      const next = mode === 'replace' ? new Set<string>() : new Set(state.selected);
      for (const id of ids) {
        if (mode === 'toggle' && next.has(id)) next.delete(id);
        else next.add(id);
      }
      return { selected: next };
    });
  },
  clear: () => {
    set({ selected: new Set() });
  },
  setTool: (tool) => {
    set({ tool });
  },
  retain: (existing) => {
    set((state) => {
      const kept = [...state.selected].filter((id) => existing.has(id));
      return kept.length === state.selected.size ? state : { selected: new Set(kept) };
    });
  },
}));

/** Click semantics shared by the map and the list: plain replaces, shift adds, ctrl toggles. */
export function modeFor(event: {
  shiftKey: boolean;
  ctrlKey: boolean;
  metaKey: boolean;
}): SelectMode {
  if (event.ctrlKey || event.metaKey) return 'toggle';
  if (event.shiftKey) return 'add';
  return 'replace';
}
