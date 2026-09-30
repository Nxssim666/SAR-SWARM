// The route of a waypoint mission (ADR 0014, ADR 0028): points added by clicking the map,
// each with its altitude **above home** (the reference is in every label), an optional speed
// and loiter time; reordered or removed; checked; saved as the complete route (PUT).
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { api, ProblemError } from '../api/client';
import type { MissionOut, WaypointIn, WaypointsOut } from '../api/types';
import { formatCoord } from '../map/coords';
import { useMapState } from '../map/mapState';
import { useSelection } from '../selection/store';
import { useSession } from '../session/session';
import { checkWaypoints } from './planRequest';
import { planningKeys, useWaypoints } from './queries';
import { usePlanning } from './store';

function optionalNumber(text: string): number | null {
  return text.trim() === '' ? null : Number(text);
}

export function WaypointEditor({ mission, editable }: { mission: MissionOut; editable: boolean }) {
  const session = useSession((s) => s.session);
  const saved = useWaypoints(mission);
  const waypoints = usePlanning((s) => s.waypoints);
  const defaultAltitude = usePlanning((s) => s.waypointAltitude);
  const tool = useSelection((s) => s.tool);
  const format = useMapState((s) => s.format);
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const issues = checkWaypoints(waypoints);
  const errors = issues.filter((i) => i.level === 'error');

  // Start from the saved route.
  const loaded = saved.data;
  useEffect(() => {
    if (!loaded) return;
    usePlanning.getState().setWaypoints(
      loaded.waypoints.map((w) => ({
        latitude: w.latitude,
        longitude: w.longitude,
        altitude_relative_m: w.altitude_relative_m,
        speed_mps: w.speed_mps,
        loiter_s: w.loiter_s,
      })),
    );
    usePlanning.getState().setWaypointAltitude(mission.default_altitude_relative_m);
  }, [loaded, mission.default_altitude_relative_m]);

  const update = (index: number, change: Partial<WaypointIn>) => {
    usePlanning
      .getState()
      .setWaypoints(waypoints.map((w, i) => (i === index ? { ...w, ...change } : w)));
  };
  const move = (index: number, by: -1 | 1) => {
    const next = [...waypoints];
    const [item] = next.splice(index, 1);
    if (item) next.splice(index + by, 0, item);
    usePlanning.getState().setWaypoints(next);
  };

  const save = async () => {
    if (errors.length > 0) return;
    setBusy(true);
    setError(null);
    try {
      await api<WaypointsOut>(`/missions/${mission.id}/waypoints`, {
        method: 'PUT',
        body: { waypoints },
        token: session?.token ?? null,
      });
      await queryClient.invalidateQueries({ queryKey: planningKeys.waypoints(mission.id) });
      setSavedAt(new Date().toLocaleTimeString());
    } catch (e) {
      setError(e instanceof ProblemError ? e.message : 'The route could not be saved.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel" aria-label="Route">
      <h2>Route ({waypoints.length} waypoints)</h2>
      {editable && (
        <div className="row">
          <button
            type="button"
            aria-pressed={tool === 'waypoint'}
            title="Each click on the map adds a waypoint; Esc stops."
            onClick={() => {
              useSelection.getState().setTool(tool === 'waypoint' ? 'pan' : 'waypoint');
            }}
          >
            Add on map
          </button>
          <label>
            New at{' '}
            <input
              type="number"
              className="narrow"
              min={1}
              max={1500}
              value={defaultAltitude}
              aria-label="Altitude of new waypoints (m above home)"
              onChange={(e) => {
                usePlanning.getState().setWaypointAltitude(Number(e.target.value));
              }}
            />{' '}
            m above home
          </label>
        </div>
      )}
      {waypoints.length > 0 && (
        <table className="waypoints">
          <thead>
            <tr>
              <th>#</th>
              <th>Position</th>
              <th title="Metres above each aircraft's home">Alt. (m above home)</th>
              <th>Speed (m/s)</th>
              <th>Loiter (s)</th>
              {editable && <th aria-label="Actions" />}
            </tr>
          </thead>
          <tbody>
            {waypoints.map((w, i) => (
              <tr
                key={`${String(i)}-${String(w.latitude)}-${String(w.longitude)}`}
                data-issue={issues.some((x) => x.index === i && x.level === 'error') || undefined}
              >
                <td>{i + 1}</td>
                <td className="coord">{formatCoord(w.latitude, w.longitude, format)}</td>
                <td>
                  <input
                    type="number"
                    className="narrow"
                    aria-label={`Waypoint ${String(i + 1)} altitude above home`}
                    disabled={!editable}
                    value={w.altitude_relative_m}
                    onChange={(e) => {
                      update(i, { altitude_relative_m: Number(e.target.value) });
                    }}
                  />
                </td>
                <td>
                  <input
                    type="number"
                    className="narrow"
                    aria-label={`Waypoint ${String(i + 1)} speed`}
                    disabled={!editable}
                    value={w.speed_mps ?? ''}
                    onChange={(e) => {
                      update(i, { speed_mps: optionalNumber(e.target.value) });
                    }}
                  />
                </td>
                <td>
                  <input
                    type="number"
                    className="narrow"
                    aria-label={`Waypoint ${String(i + 1)} loiter time`}
                    disabled={!editable}
                    value={w.loiter_s ?? ''}
                    onChange={(e) => {
                      update(i, { loiter_s: optionalNumber(e.target.value) });
                    }}
                  />
                </td>
                {editable && (
                  <td className="actions">
                    <button
                      type="button"
                      aria-label={`Move waypoint ${String(i + 1)} up`}
                      disabled={i === 0}
                      onClick={() => {
                        move(i, -1);
                      }}
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      aria-label={`Move waypoint ${String(i + 1)} down`}
                      disabled={i === waypoints.length - 1}
                      onClick={() => {
                        move(i, 1);
                      }}
                    >
                      ↓
                    </button>
                    <button
                      type="button"
                      aria-label={`Remove waypoint ${String(i + 1)}`}
                      onClick={() => {
                        usePlanning.getState().setWaypoints(waypoints.filter((_, j) => j !== i));
                      }}
                    >
                      ✕
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {issues.length > 0 && (
        <ul className="issues">
          {issues.map((issue) => (
            <li key={`${String(issue.index)}-${issue.message}`} data-level={issue.level}>
              {issue.level === 'error' ? '✕' : '⚠'} {issue.message}
            </li>
          ))}
        </ul>
      )}
      {editable && (
        <div className="row">
          <button type="button" disabled={busy || errors.length > 0} onClick={() => void save()}>
            Save route
          </button>
          {savedAt && <span className="muted">Saved at {savedAt}.</span>}
        </div>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </section>
  );
}
