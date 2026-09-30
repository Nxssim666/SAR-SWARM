// The incident the operator works on. Missions, search areas and points of interest belong
// to an incident; the console shows those of this one. A display preference, so it is kept
// in localStorage (not a secret); the server checks every request anyway.
import { create } from 'zustand';

const KEY = 'sargcs.incident';

function stored(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

interface IncidentState {
  incidentId: string | null;
  setIncident: (id: string | null) => void;
}

export const useIncident = create<IncidentState>()((set) => ({
  incidentId: stored(),
  setIncident: (incidentId) => {
    try {
      if (incidentId) localStorage.setItem(KEY, incidentId);
      else localStorage.removeItem(KEY);
    } catch {
      // storage unavailable: the choice lasts until reload
    }
    set({ incidentId });
  },
}));
