// Which incident the console works on (top bar). Supervisors can open a new one, based where
// the map is centred; the fleet service checks the base, radius and permission. Those who
// read the audit trail can export the incident's bundle (M6).
import * as Dialog from '@radix-ui/react-dialog';
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { api, ProblemError } from '../api/client';
import { download } from '../api/download';
import type { IncidentCreate, IncidentOut } from '../api/types';
import { formatCoord } from '../map/coords';
import { useMapState } from '../map/mapState';
import { can, useSession } from '../session/session';
import { INCIDENTS_KEY, useIncidents } from './queries';
import { useIncident } from './store';

export function IncidentPicker() {
  const session = useSession((s) => s.session);
  const incidents = useIncidents();
  const incidentId = useIncident((s) => s.incidentId);
  const setIncident = useIncident((s) => s.setIncident);
  const [creating, setCreating] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const token = session?.token ?? null;
  const items = incidents.data?.items ?? [];

  // One open incident is the usual case: pick it; forget a choice that has closed.
  useEffect(() => {
    const open = incidents.data?.items;
    if (!open) return;
    const known = open.some((i) => i.id === incidentId);
    if (!known) setIncident(open.length === 1 ? (open[0]?.id ?? null) : null);
  }, [incidents.data, incidentId, setIncident]);

  return (
    <div className="incident-picker">
      <label>
        Incident{' '}
        <select
          aria-label="Incident"
          value={incidentId ?? ''}
          onChange={(e) => {
            setIncident(e.target.value || null);
          }}
        >
          <option value="">{items.length === 0 ? 'None open' : 'Choose…'}</option>
          {items.map((i) => (
            <option key={i.id} value={i.id}>
              {i.name}
            </option>
          ))}
        </select>
      </label>
      {incidentId && can(session, 'audit.read') && (
        <button
          type="button"
          title="Everything about this incident in a zip: areas, missions, POIs, alerts, commands, audit trail, telemetry"
          onClick={() => {
            setExportError(null);
            void download(`/incidents/${incidentId}/export`, token, 'incident.zip').then(
              setExportError,
            );
          }}
        >
          Export
        </button>
      )}
      {exportError && (
        <span role="alert" className="error">
          {exportError}
        </span>
      )}
      {can(session, 'incidents.manage') && (
        <button
          type="button"
          onClick={() => {
            setCreating(true);
          }}
        >
          New incident
        </button>
      )}
      {creating && (
        <NewIncidentDialog
          onClose={(created) => {
            setCreating(false);
            if (created) setIncident(created.id);
          }}
        />
      )}
    </div>
  );
}

function NewIncidentDialog({ onClose }: { onClose: (created: IncidentOut | null) => void }) {
  const token = useSession((s) => s.session?.token ?? null);
  const center = useMapState((s) => s.center);
  const format = useMapState((s) => s.format);
  const queryClient = useQueryClient();
  const [name, setName] = useState('');
  const [radiusKm, setRadiusKm] = useState('5');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const radius = Number(radiusKm);
  const valid = name.trim().length > 0 && center !== null && radius > 0 && radius <= 100;

  const create = async () => {
    if (!valid) return;
    setBusy(true);
    const body: IncidentCreate = {
      name: name.trim(),
      base: center,
      operating_radius_m: radius * 1000,
    };
    try {
      const created = await api<IncidentOut>('/incidents', { method: 'POST', body, token });
      await queryClient.invalidateQueries({ queryKey: INCIDENTS_KEY });
      onClose(created);
    } catch (e) {
      setError(e instanceof ProblemError ? e.message : 'The incident could not be created.');
      setBusy(false);
    }
  };

  return (
    <Dialog.Root
      open
      onOpenChange={(open) => {
        if (!open) onClose(null);
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog">
          <Dialog.Title>New incident</Dialog.Title>
          <Dialog.Description>
            The base is the centre of the map; missions and search areas must lie within the
            operating radius around it.
          </Dialog.Description>
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
            <p>
              Base:{' '}
              <output>
                {center ? formatCoord(center.latitude, center.longitude, format) : 'unknown'}
              </output>
            </p>
            <label>
              Operating radius (km)
              <input
                type="number"
                min={0.1}
                max={100}
                step={0.1}
                value={radiusKm}
                onChange={(e) => {
                  setRadiusKm(e.target.value);
                }}
              />
            </label>
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            <div className="dialog-actions">
              <button
                type="button"
                onClick={() => {
                  onClose(null);
                }}
              >
                Cancel
              </button>
              <button type="submit" disabled={!valid || busy}>
                Create
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
