// Planning data over REST (TanStack Query): the incident's search areas and missions, a
// mission's waypoints, saved plan and progress. Live progress comes on the `missions` topic;
// the progress endpoint adds the coverage geometry for the map.
import { useQuery } from '@tanstack/react-query';

import { api, ProblemError } from '../api/client';
import type {
  MissionOut,
  MissionPage,
  MissionProgressOut,
  PlanOut,
  SearchAreaPage,
  WaypointsOut,
} from '../api/types';
import { useSession } from '../session/session';

export const planningKeys = {
  areas: (incidentId: string) => ['areas', incidentId] as const,
  missions: (incidentId: string) => ['missions', incidentId] as const,
  waypoints: (missionId: string) => ['waypoints', missionId] as const,
  plan: (missionId: string) => ['plan', missionId] as const,
  progress: (missionId: string) => ['progress', missionId] as const,
};

function useToken(): string | null {
  return useSession((s) => s.session?.token ?? null);
}

export function useSearchAreas(incidentId: string | null) {
  const token = useToken();
  return useQuery({
    queryKey: planningKeys.areas(incidentId ?? ''),
    enabled: !!incidentId && !!token,
    queryFn: ({ signal }) =>
      api<SearchAreaPage>(`/search-areas?incident_id=${incidentId ?? ''}&limit=200`, {
        token,
        signal,
      }),
  });
}

export function useMissions(incidentId: string | null) {
  const token = useToken();
  return useQuery({
    queryKey: planningKeys.missions(incidentId ?? ''),
    enabled: !!incidentId && !!token,
    queryFn: ({ signal }) =>
      api<MissionPage>(`/missions?incident_id=${incidentId ?? ''}&limit=200`, { token, signal }),
  });
}

export function useWaypoints(mission: MissionOut | null) {
  const token = useToken();
  return useQuery({
    queryKey: planningKeys.waypoints(mission?.id ?? ''),
    enabled: !!mission && mission.kind === 'waypoint' && !!token,
    queryFn: ({ signal }) =>
      api<WaypointsOut>(`/missions/${mission?.id ?? ''}/waypoints`, { token, signal }),
  });
}

/** The saved plan, or null when the mission has none yet (404 no-plan). */
export function useSavedPlan(mission: MissionOut | null) {
  const token = useToken();
  return useQuery({
    queryKey: planningKeys.plan(mission?.id ?? ''),
    enabled: !!mission && mission.kind !== 'swarm_area' && !!token,
    queryFn: async ({ signal }) => {
      try {
        return await api<PlanOut>(`/missions/${mission?.id ?? ''}/plan`, { token, signal });
      } catch (error) {
        if (error instanceof ProblemError && error.status === 404) return null;
        throw error;
      }
    },
  });
}

/** Progress with the coverage geometry, refreshed while the mission flies. */
export function useProgress(mission: MissionOut | null, flying: boolean) {
  const token = useToken();
  return useQuery({
    queryKey: planningKeys.progress(mission?.id ?? ''),
    enabled: !!mission && mission.status !== 'draft' && !!token,
    refetchInterval: flying ? 3000 : false,
    queryFn: ({ signal }) =>
      api<MissionProgressOut>(`/missions/${mission?.id ?? ''}/progress`, { token, signal }),
  });
}
