// Points of interest of the incident (ADR 0031): marked by operators, or survivor sightings
// reported by drones. New survivor sightings come first. Operators confirm, dismiss or
// resolve them (nothing is deleted); a sighting is a report to check, never acted on by
// the station itself (ADR 0002).
import { useState } from 'react';

import { api, ProblemError } from '../api/client';
import type { PoiCreate, PoiKind, PoiStatus, PoiView } from '../api/types';
import { useCurrentIncident } from '../incident/queries';
import { useThrottledLive } from '../live/useThrottled';
import { formatCoord } from '../map/coords';
import { useMapState } from '../map/mapState';
import { POI_STYLE, poiOpen } from '../planning/features';
import { usePlanning } from '../planning/store';
import { useSelection } from '../selection/store';
import { can, useSession } from '../session/session';
import { orderPois, POI_SYMBOL } from './order';

const ACTIONS: { status: PoiStatus; label: string }[] = [
  { status: 'confirmed', label: 'Confirm' },
  { status: 'dismissed', label: 'Dismiss' },
  { status: 'resolved', label: 'Resolve' },
];

export function PoisPanel() {
  const session = useSession((s) => s.session);
  const incident = useCurrentIncident();
  const pois = useThrottledLive((s) => s.pois);
  const aircraft = useThrottledLive((s) => s.aircraft);
  const format = useMapState((s) => s.format);
  const tool = useSelection((s) => s.tool);
  const draft = usePlanning((s) => s.poiDraft);
  const [error, setError] = useState<string | null>(null);
  const mayEdit = can(session, 'missions.plan');

  if (!incident) {
    return (
      <section className="panel" aria-label="Points of interest">
        <h2>Points of interest</h2>
        <p className="muted">Choose an incident in the top bar.</p>
      </section>
    );
  }
  const items = orderPois(Object.values(pois).filter((p) => p.incident_id === incident.id));

  const setStatus = async (poi: PoiView, status: PoiStatus) => {
    setError(null);
    try {
      await api(`/pois/${poi.id}`, {
        method: 'PATCH',
        body: { status },
        token: session?.token ?? null,
      });
    } catch (e) {
      setError(e instanceof ProblemError ? e.message : 'The point could not be updated.');
    }
  };

  return (
    <section className="panel" aria-label="Points of interest">
      <h2>
        Points of interest{' '}
        <span className="count">{items.filter((p) => poiOpen(p.status)).length}</span>
      </h2>
      {mayEdit && (
        <button
          type="button"
          aria-pressed={tool === 'poi'}
          title="Click the map where the point is."
          onClick={() => {
            useSelection.getState().setTool(tool === 'poi' ? 'pan' : 'poi');
          }}
        >
          Mark a point
        </button>
      )}
      {draft && (
        <NewPoi
          incidentId={incident.id}
          onDone={(message) => {
            setError(message);
          }}
        />
      )}
      {items.length === 0 && <p className="muted">None yet.</p>}
      <ul className="poi-list">
        {items.map((p) => {
          const style = POI_STYLE[p.kind];
          const reporter = p.aircraft_id ? aircraft[p.aircraft_id]?.callsign : null;
          return (
            <li key={p.id} data-kind={p.kind} data-status={p.status}>
              <div>
                <span className="poi-symbol" style={{ color: style.color }} aria-hidden="true">
                  {POI_SYMBOL[p.kind]}
                </span>{' '}
                <strong>{style.word}</strong> · {p.status}
                {reporter ? ` · reported by ${reporter}` : ''}
              </div>
              <div className="muted">
                <button
                  type="button"
                  className="link-button"
                  title="Show on the map"
                  onClick={() => {
                    const pad = 0.002;
                    useMapState
                      .getState()
                      .showBounds([
                        p.longitude - pad,
                        p.latitude - pad,
                        p.longitude + pad,
                        p.latitude + pad,
                      ]);
                  }}
                >
                  {formatCoord(p.latitude, p.longitude, format)}
                </button>
                {p.uncertainty_m !== null ? ` ± ${p.uncertainty_m.toFixed(0)} m` : ''}
                {p.notes ? ` · ${p.notes}` : ''}
              </div>
              {mayEdit && poiOpen(p.status) && (
                <div className="row">
                  {ACTIONS.filter((a) => a.status !== p.status).map((a) => (
                    <button
                      key={a.status}
                      type="button"
                      onClick={() => void setStatus(p, a.status)}
                    >
                      {a.label}
                    </button>
                  ))}
                </div>
              )}
            </li>
          );
        })}
      </ul>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </section>
  );
}

function NewPoi({
  incidentId,
  onDone,
}: {
  incidentId: string;
  onDone: (error: string | null) => void;
}) {
  const session = useSession((s) => s.session);
  const draft = usePlanning((s) => s.poiDraft);
  const format = useMapState((s) => s.format);
  const [kind, setKind] = useState<PoiKind>('poi');
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  if (!draft) return null;

  const save = async () => {
    setBusy(true);
    const body: PoiCreate = {
      kind,
      position: draft,
      notes: notes.trim() || null,
    };
    try {
      await api(`/incidents/${incidentId}/pois`, {
        method: 'POST',
        body,
        token: session?.token ?? null,
      });
      usePlanning.getState().setPoiDraft(null);
      onDone(null);
    } catch (e) {
      onDone(e instanceof ProblemError ? e.message : 'The point could not be saved.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <form
      className="form"
      aria-label="New point of interest"
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <p>
        At <output>{formatCoord(draft.latitude, draft.longitude, format)}</output>
      </p>
      <label>
        Kind
        <select
          value={kind}
          onChange={(e) => {
            setKind(e.target.value as PoiKind);
          }}
        >
          {(Object.keys(POI_STYLE) as PoiKind[]).map((k) => (
            <option key={k} value={k}>
              {POI_STYLE[k].word}
            </option>
          ))}
        </select>
      </label>
      <label>
        Notes
        <input
          value={notes}
          maxLength={2000}
          onChange={(e) => {
            setNotes(e.target.value);
          }}
        />
      </label>
      <div className="row">
        <button type="submit" disabled={busy}>
          Save point
        </button>
        <button
          type="button"
          onClick={() => {
            usePlanning.getState().setPoiDraft(null);
          }}
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
