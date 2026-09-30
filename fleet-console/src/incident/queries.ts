// The open incidents (TanStack Query), and the one the console works on.
import { useQuery } from '@tanstack/react-query';

import { api } from '../api/client';
import type { IncidentOut, IncidentPage } from '../api/types';
import { useSession } from '../session/session';
import { useIncident } from './store';

export const INCIDENTS_KEY = ['incidents'] as const;

export function useIncidents() {
  const token = useSession((s) => s.session?.token);
  return useQuery({
    queryKey: INCIDENTS_KEY,
    enabled: !!token,
    queryFn: ({ signal }) =>
      api<IncidentPage>('/incidents?status=active&limit=200', { token: token ?? null, signal }),
  });
}

/** The selected incident, if it is still open. */
export function useCurrentIncident(): IncidentOut | null {
  const incidents = useIncidents();
  const incidentId = useIncident((s) => s.incidentId);
  return incidents.data?.items.find((i) => i.id === incidentId) ?? null;
}
