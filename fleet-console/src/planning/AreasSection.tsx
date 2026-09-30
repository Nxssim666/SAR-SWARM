// The incident's search areas: listed (name, status, size), drawn on the map or imported
// from a file (GeoJSON, KML, GPX), then named and saved. The fleet service checks the ring
// and that it lies in the incident's operating area (which catches swapped coordinates).
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { api, ProblemError } from '../api/client';
import type { SearchAreaCreate, SearchAreaOut } from '../api/types';
import { boundsOf, useMapState } from '../map/mapState';
import { useSelection } from '../selection/store';
import { can, useSession } from '../session/session';
import { type ImportedArea, ImportError, parseAreaFile } from './importArea';
import { planningKeys, useSearchAreas } from './queries';
import { usePlanning } from './store';

function km2(m2: number): string {
  return m2 >= 100_000 ? `${(m2 / 1_000_000).toFixed(2)} km²` : `${Math.round(m2).toString()} m²`;
}

export function AreasSection({ incidentId }: { incidentId: string }) {
  const session = useSession((s) => s.session);
  const areas = useSearchAreas(incidentId);
  const activeAreaId = usePlanning((s) => s.activeAreaId);
  const drawnRing = usePlanning((s) => (s.drawingFor === 'area' ? s.drawnRing : null));
  const tool = useSelection((s) => s.tool);
  const queryClient = useQueryClient();
  const [name, setName] = useState('');
  const [imported, setImported] = useState<ImportedArea[]>([]);
  const [notes, setNotes] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const mayPlan = can(session, 'missions.plan');
  const items = areas.data?.items;

  // The map draws the incident's areas.
  useEffect(() => {
    usePlanning.getState().setAreas(items ?? []);
  }, [items]);

  const show = (area: SearchAreaOut) => {
    usePlanning.getState().setActiveArea(area.id);
    const bounds = boundsOf(area.geometry.coordinates[0] ?? []);
    if (bounds) useMapState.getState().showBounds(bounds);
  };

  const takeCandidate = (candidate: ImportedArea) => {
    usePlanning.getState().setDrawingFor('area');
    usePlanning.getState().setDrawnRing(candidate.ring);
    setName(candidate.name);
    setNotes(candidate.notes);
    const bounds = boundsOf(candidate.ring);
    if (bounds) useMapState.getState().showBounds(bounds);
  };

  const importFile = async (file: File) => {
    setError(null);
    try {
      const candidates = parseAreaFile(file.name, await file.text());
      setImported(candidates.length > 1 ? candidates : []);
      const first = candidates[0];
      if (first) takeCandidate(first);
    } catch (e) {
      setError(e instanceof ImportError ? e.message : 'The file could not be read.');
    }
  };

  const discard = () => {
    usePlanning.getState().setDrawnRing(null);
    setImported([]);
    setNotes([]);
    setName('');
  };

  const save = async () => {
    if (!drawnRing || !name.trim()) return;
    setBusy(true);
    setError(null);
    const body: SearchAreaCreate = {
      incident_id: incidentId,
      name: name.trim(),
      geometry: { type: 'Polygon', coordinates: [drawnRing] },
      priority: 3, // the server's default priority
    };
    try {
      const created = await api<SearchAreaOut>('/search-areas', {
        method: 'POST',
        body,
        token: session?.token ?? null,
      });
      await queryClient.invalidateQueries({ queryKey: planningKeys.areas(incidentId) });
      discard();
      usePlanning.getState().setActiveArea(created.id);
    } catch (e) {
      setError(e instanceof ProblemError ? e.message : 'The area could not be saved.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel" aria-label="Search areas">
      <h2>Search areas</h2>
      {items?.length === 0 && <p className="muted">No search area yet.</p>}
      <ul className="plain-list">
        {items?.map((a) => (
          <li key={a.id}>
            <button
              type="button"
              className="link-button"
              aria-pressed={a.id === activeAreaId}
              onClick={() => {
                show(a);
              }}
            >
              {a.name}
            </button>{' '}
            <span className="muted">
              {km2(a.area_m2)} · {a.status.replace('_', ' ')}
            </span>
          </li>
        ))}
      </ul>
      {mayPlan && (
        <div className="row">
          <button
            type="button"
            aria-pressed={tool === 'area'}
            title="Click the corners on the map; click the first corner again to close it."
            onClick={() => {
              discard();
              usePlanning.getState().setDrawingFor('area');
              useSelection.getState().setTool(tool === 'area' ? 'pan' : 'area');
            }}
          >
            Draw area
          </button>
          <label className="file-button">
            Import file…
            <input
              type="file"
              accept=".geojson,.json,.kml,.gpx"
              aria-label="Import a search area from a file"
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = '';
                if (file) void importFile(file);
              }}
            />
          </label>
        </div>
      )}
      {imported.length > 1 && (
        <label>
          Area in the file{' '}
          <select
            onChange={(e) => {
              const candidate = imported[Number(e.target.value)];
              if (candidate) takeCandidate(candidate);
            }}
          >
            {imported.map((c, i) => (
              <option key={`${c.name}-${String(i)}`} value={i}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
      )}
      {drawnRing && (
        <form
          className="form"
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
        >
          <p className="muted">
            New area: {String(drawnRing.length - 1)} corners.
            {notes.length > 0 && ` Note: ${notes.join('; ')}.`}
          </p>
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
          <div className="row">
            <button type="submit" disabled={busy || !name.trim()}>
              Save area
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
