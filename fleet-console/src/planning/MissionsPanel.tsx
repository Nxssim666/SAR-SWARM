// Missions of the incident (ADR 0028): search areas, the mission list with live status and
// coverage, a form for a new mission, and the open mission's details.
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { api, ProblemError } from '../api/client';
import type { MissionCreate, MissionKind, MissionOut } from '../api/types';
import { useCurrentIncident } from '../incident/queries';
import { useThrottledLive } from '../live/useThrottled';
import { can, useSession } from '../session/session';
import { AreasSection } from './AreasSection';
import { GeofencesSection } from './GeofencesSection';
import { MissionDetail } from './MissionDetail';
import { percent } from './format';
import { planningKeys, useMissions } from './queries';
import { usePlanning } from './store';

const KIND_LABEL: Record<MissionKind, string> = {
  area_search: 'Area search',
  waypoint: 'Waypoint route',
  swarm_area: 'Swarm area',
};

export function MissionsPanel() {
  const incident = useCurrentIncident();
  const missions = useMissions(incident?.id ?? null);
  const live = useThrottledLive((s) => s.missions);
  const [openId, setOpenId] = useState<string | null>(null);
  const open = missions.data?.items.find((m) => m.id === openId) ?? null;

  if (!incident) {
    return (
      <section className="panel" aria-label="Missions">
        <h2>Missions</h2>
        <p className="muted">Choose an incident in the top bar to plan missions.</p>
      </section>
    );
  }

  if (open) {
    return (
      <MissionDetail
        mission={open}
        onClose={() => {
          setOpenId(null);
          const p = usePlanning.getState();
          p.setRoutes([]);
          p.setCoverage(null);
          p.setWaypoints([]);
          p.setDatum(null);
        }}
      />
    );
  }

  return (
    <>
      <AreasSection incidentId={incident.id} />
      <GeofencesSection incidentId={incident.id} />
      <section className="panel" aria-label="Missions">
        <h2>Missions</h2>
        {missions.data?.items.length === 0 && <p className="muted">No mission yet.</p>}
        <ul className="plain-list">
          {missions.data?.items.map((m) => {
            const progress = live[m.id];
            return (
              <li key={m.id}>
                <button
                  type="button"
                  className="link-button"
                  onClick={() => {
                    setOpenId(m.id);
                  }}
                >
                  {m.name}
                </button>{' '}
                <span className="muted">
                  {KIND_LABEL[m.kind]} · <span data-status>{progress?.status ?? m.status}</span>
                  {progress?.coverage !== undefined && progress.coverage !== null
                    ? ` · ${percent(progress.coverage)} covered`
                    : ''}
                </span>
              </li>
            );
          })}
        </ul>
        <NewMission incidentId={incident.id} onCreated={setOpenId} />
      </section>
    </>
  );
}

function NewMission({
  incidentId,
  onCreated,
}: {
  incidentId: string;
  onCreated: (id: string) => void;
}) {
  const session = useSession((s) => s.session);
  const activeAreaId = usePlanning((s) => s.activeAreaId);
  const areas = usePlanning((s) => s.areas);
  const queryClient = useQueryClient();
  const [name, setName] = useState('');
  const [kind, setKind] = useState<'area_search' | 'waypoint'>('area_search');
  const [altitude, setAltitude] = useState('50');
  const [speed, setSpeed] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (!can(session, 'missions.plan')) return null;

  const area = areas.find((a) => a.id === activeAreaId) ?? null;
  const altitudeValue = Number(altitude);
  const speedValue = speed.trim() === '' ? null : Number(speed);
  const problems: string[] = [];
  if (!name.trim()) problems.push('Name the mission.');
  if (kind === 'area_search' && !area) problems.push('Choose its search area above.');
  if (!(altitudeValue > 0 && altitudeValue <= 1500)) {
    problems.push('The altitude above home must be 1 to 1500 m.');
  }
  if (speedValue !== null && !(speedValue > 0 && speedValue <= 60)) {
    problems.push('The speed must be above 0 and at most 60 m/s.');
  }

  const create = async () => {
    if (problems.length > 0) return;
    setBusy(true);
    setError(null);
    const body: MissionCreate = {
      incident_id: incidentId,
      name: name.trim(),
      kind,
      search_area_id: kind === 'area_search' ? (area?.id ?? null) : null,
      default_altitude_relative_m: altitudeValue,
      default_speed_mps: speedValue,
    };
    try {
      const created = await api<MissionOut>('/missions', {
        method: 'POST',
        body,
        token: session?.token ?? null,
      });
      await queryClient.invalidateQueries({ queryKey: planningKeys.missions(incidentId) });
      setName('');
      onCreated(created.id);
    } catch (e) {
      setError(e instanceof ProblemError ? e.message : 'The mission could not be created.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <details className="new-mission">
      <summary>New mission</summary>
      <form
        className="form"
        onSubmit={(e) => {
          e.preventDefault();
          void create();
        }}
      >
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
          Kind
          <select
            value={kind}
            onChange={(e) => {
              setKind(e.target.value as 'area_search' | 'waypoint');
            }}
          >
            <option value="area_search">Area search (search pattern)</option>
            <option value="waypoint">Waypoint route</option>
          </select>
        </label>
        {kind === 'area_search' && (
          <p className="muted">Search area: {area ? area.name : 'none chosen'}</p>
        )}
        <label>
          Altitude (m above home)
          <input
            type="number"
            min={1}
            max={1500}
            value={altitude}
            onChange={(e) => {
              setAltitude(e.target.value);
            }}
          />
        </label>
        <label>
          Speed (m/s, empty: each aircraft&apos;s own)
          <input
            type="number"
            min={0.1}
            max={60}
            step={0.1}
            value={speed}
            onChange={(e) => {
              setSpeed(e.target.value);
            }}
          />
        </label>
        {problems.length > 0 && name.trim() && <p className="muted">{problems.join(' ')}</p>}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <button type="submit" disabled={busy || problems.length > 0}>
          Create mission
        </button>
      </form>
    </details>
  );
}
