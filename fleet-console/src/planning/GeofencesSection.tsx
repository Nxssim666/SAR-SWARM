// The incident's geofences (M6): exclusion zones (power lines, a helicopter landing site,
// other airspace users) and inclusion zones. Everyone sees them on the map; supervisors draw
// them, switch them on and off. The fleet service enforces them: a goto into an exclusion
// zone is refused, and an aircraft inside one raises a critical geofence_breach alert.
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { api, ProblemError } from '../api/client';
import type { GeofenceCreate, GeofenceOut } from '../api/types';
import { boundsOf, useMapState } from '../map/mapState';
import { useSelection } from '../selection/store';
import { can, useSession } from '../session/session';
import { planningKeys, useGeofences } from './queries';
import { usePlanning } from './store';

export function GeofencesSection({ incidentId }: { incidentId: string }) {
  const session = useSession((s) => s.session);
  const token = session?.token ?? null;
  const fences = useGeofences(incidentId);
  const drawnRing = usePlanning((s) => (s.drawingFor === 'fence' ? s.drawnRing : null));
  const tool = useSelection((s) => s.tool);
  const queryClient = useQueryClient();
  const [name, setName] = useState('');
  const [kind, setKind] = useState<GeofenceOut['kind']>('exclusion');
  const [ceiling, setCeiling] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const manage = can(session, 'geofences.manage');
  const items = fences.data?.items;

  // The map draws the incident's geofences.
  useEffect(() => {
    usePlanning.getState().setFences(items ?? []);
  }, [items]);

  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: planningKeys.fences(incidentId) });

  const discard = () => {
    usePlanning.getState().setDrawnRing(null);
    setName('');
    setCeiling('');
  };

  const save = async () => {
    if (!drawnRing || !name.trim()) return;
    setBusy(true);
    setError(null);
    const body: GeofenceCreate = {
      incident_id: incidentId,
      name: name.trim(),
      kind,
      geometry: { type: 'Polygon', coordinates: [drawnRing] },
      max_altitude_relative_m: ceiling ? Number(ceiling) : null,
      enabled: true,
    };
    try {
      await api<GeofenceOut>('/geofences', { method: 'POST', body, token });
      await refresh();
      discard();
    } catch (e) {
      setError(e instanceof ProblemError ? e.message : 'The geofence could not be saved.');
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (fence: GeofenceOut) => {
    setError(null);
    try {
      await api(`/geofences/${fence.id}`, {
        method: 'PATCH',
        body: { enabled: !fence.enabled },
        token,
      });
      await refresh();
    } catch (e) {
      setError(e instanceof ProblemError ? e.message : 'The geofence could not be changed.');
    }
  };

  return (
    <section className="panel" aria-label="Geofences">
      <h2>Geofences</h2>
      {items?.length === 0 && <p className="muted">No geofence.</p>}
      <ul className="plain-list">
        {items?.map((f) => (
          <li key={f.id} data-enabled={f.enabled}>
            <button
              type="button"
              className="link-button"
              onClick={() => {
                const bounds = boundsOf(f.geometry.coordinates[0] ?? []);
                if (bounds) useMapState.getState().showBounds(bounds);
              }}
            >
              {f.kind === 'exclusion' ? '⛔' : '◻'} {f.name}
            </button>{' '}
            <span className="muted">
              {f.kind}
              {f.max_altitude_relative_m !== null
                ? ` · ceiling ${String(f.max_altitude_relative_m)} m`
                : ''}
              {f.enabled ? '' : ' · off'}
            </span>{' '}
            {manage && (
              <button type="button" onClick={() => void toggle(f)}>
                {f.enabled ? 'Switch off' : 'Switch on'}
              </button>
            )}
          </li>
        ))}
      </ul>
      {manage && (
        <button
          type="button"
          aria-pressed={tool === 'area' && usePlanning.getState().drawingFor === 'fence'}
          title="Click the corners on the map; click the first corner again to close it."
          onClick={() => {
            discard();
            usePlanning.getState().setDrawingFor('fence');
            useSelection.getState().setTool(tool === 'area' ? 'pan' : 'area');
          }}
        >
          Draw geofence
        </button>
      )}
      {drawnRing && (
        <form
          className="form"
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
        >
          <p className="muted">New geofence: {String(drawnRing.length - 1)} corners.</p>
          <label>
            Name
            <input
              value={name}
              maxLength={200}
              onChange={(e) => {
                setName(e.target.value);
              }}
            />
          </label>
          <label>
            Kind{' '}
            <select
              value={kind}
              onChange={(e) => {
                setKind(e.target.value as GeofenceOut['kind']);
              }}
            >
              <option value="exclusion">Exclusion: aircraft must stay out</option>
              <option value="inclusion">Inclusion: aircraft must stay in</option>
            </select>
          </label>
          <label>
            Ceiling (m above home, optional)
            <input
              type="number"
              min={1}
              step={1}
              value={ceiling}
              onChange={(e) => {
                setCeiling(e.target.value);
              }}
            />
          </label>
          <div className="row">
            <button type="submit" disabled={busy || !name.trim()}>
              Save geofence
            </button>
            <button type="button" onClick={discard}>
              Discard
            </button>
          </div>
        </form>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </section>
  );
}
