// Planning a mission (ADR 0028, ADR 0029): pattern, lane spacing (explicit or from the
// camera), bearing, datum, and the aircraft (the selection or a group). "Preview" asks the
// fleet service for a dry run and draws the routes; "Save plan" stores it for starting.
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { api, ProblemError } from '../api/client';
import type { GroupOut, MissionOut, PatternKind, PlanOut } from '../api/types';
import { formatCoord } from '../map/coords';
import { useMapState } from '../map/mapState';
import { useSelection } from '../selection/store';
import { useSession } from '../session/session';
import { PlanReport } from './PlanReport';
import {
  buildPlanRequest,
  DATUM_PATTERNS,
  DEFAULT_FORM,
  type PlanForm,
  patternsFor,
} from './planRequest';
import { planningKeys } from './queries';
import { usePlanning } from './store';

interface Props {
  mission: MissionOut;
  groups: GroupOut[];
  onSaved: (plan: PlanOut) => void;
}

export function PlanSection({ mission, groups, onSaved }: Props) {
  const session = useSession((s) => s.session);
  const selected = useSelection((s) => s.selected);
  const tool = useSelection((s) => s.tool);
  const datum = usePlanning((s) => s.datum);
  const format = useMapState((s) => s.format);
  const queryClient = useQueryClient();
  const [form, setForm] = useState<PlanForm>(() => ({
    ...DEFAULT_FORM,
    pattern: mission.kind === 'waypoint' ? 'route' : 'parallel_track',
  }));
  const [preview, setPreview] = useState<PlanOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const built = buildPlanRequest(form, { selectedIds: [...selected], datum });
  const set = (change: Partial<PlanForm>) => {
    setForm((f) => ({ ...f, ...change }));
    setPreview(null);
  };

  const run = async (dryRun: boolean) => {
    if (!built.ok) return;
    setBusy(true);
    setError(null);
    try {
      const plan = await api<PlanOut>(
        `/missions/${mission.id}/plan${dryRun ? '?dry_run=true' : ''}`,
        { method: 'POST', body: built.request, token: session?.token ?? null },
      );
      usePlanning.getState().setRoutes(plan.tasks);
      if (dryRun) {
        setPreview(plan);
      } else {
        setPreview(null);
        await queryClient.invalidateQueries({ queryKey: planningKeys.plan(mission.id) });
        await queryClient.invalidateQueries({
          queryKey: planningKeys.missions(mission.incident_id),
        });
        onSaved(plan);
      }
    } catch (e) {
      setError(e instanceof ProblemError ? e.message : 'The mission could not be planned.');
    } finally {
      setBusy(false);
    }
  };

  const isDatum = DATUM_PATTERNS.has(form.pattern);
  const isRoute = form.pattern === 'route';
  return (
    <section className="panel" aria-label="Plan">
      <h2>Plan</h2>
      <form
        className="form"
        onSubmit={(e) => {
          e.preventDefault();
          void run(true);
        }}
      >
        <label>
          Pattern
          <select
            value={form.pattern}
            onChange={(e) => {
              set({ pattern: e.target.value as PatternKind });
            }}
          >
            {patternsFor(mission.kind).map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </label>
        {!isRoute && (
          <fieldset>
            <legend>Lane spacing</legend>
            <label className="inline">
              <input
                type="radio"
                name="spacing"
                checked={form.spacingMode === 'explicit'}
                onChange={() => {
                  set({ spacingMode: 'explicit' });
                }}
              />{' '}
              Set
            </label>
            <label className="inline">
              <input
                type="radio"
                name="spacing"
                checked={form.spacingMode === 'camera'}
                onChange={() => {
                  set({ spacingMode: 'camera' });
                }}
              />{' '}
              From the camera
            </label>
            {form.spacingMode === 'explicit' ? (
              <label>
                Spacing (m)
                <input
                  type="number"
                  value={form.spacingM}
                  onChange={(e) => {
                    set({ spacingM: e.target.value });
                  }}
                />
              </label>
            ) : (
              <>
                <label>
                  Horizontal field of view (°)
                  <input
                    type="number"
                    value={form.hfovDeg}
                    onChange={(e) => {
                      set({ hfovDeg: e.target.value });
                    }}
                  />
                </label>
                <label>
                  Overlap (%)
                  <input
                    type="number"
                    value={form.overlapPct}
                    onChange={(e) => {
                      set({ overlapPct: e.target.value });
                    }}
                  />
                </label>
                <label>
                  Height above ground (m, empty: the mission&apos;s altitude)
                  <input
                    type="number"
                    value={form.footprintHeightM}
                    onChange={(e) => {
                      set({ footprintHeightM: e.target.value });
                    }}
                  />
                </label>
              </>
            )}
          </fieldset>
        )}
        {!isRoute && (
          <label>
            Bearing (° true, empty: along the area)
            <input
              type="number"
              value={form.bearingDeg}
              onChange={(e) => {
                set({ bearingDeg: e.target.value });
              }}
            />
          </label>
        )}
        {isDatum && (
          <>
            <div className="row">
              <button
                type="button"
                aria-pressed={tool === 'datum'}
                onClick={() => {
                  useSelection.getState().setTool(tool === 'datum' ? 'pan' : 'datum');
                }}
              >
                Pick datum
              </button>
              <output>
                {datum ? formatCoord(datum.latitude, datum.longitude, format) : 'no datum'}
              </output>
            </div>
            <label>
              Radius (m)
              <input
                type="number"
                value={form.radiusM}
                onChange={(e) => {
                  set({ radiusM: e.target.value });
                }}
              />
            </label>
            {form.pattern === 'sector' && (
              <label className="inline">
                <input
                  type="checkbox"
                  checked={form.secondPass}
                  onChange={(e) => {
                    set({ secondPass: e.target.checked });
                  }}
                />{' '}
                Second pass (rotated 30°)
              </label>
            )}
          </>
        )}
        {form.pattern === 'contour' && (
          <label>
            Height above the contours (m)
            <input
              type="number"
              value={form.heightAglM}
              onChange={(e) => {
                set({ heightAglM: e.target.value });
              }}
            />
          </label>
        )}
        <fieldset>
          <legend>Aircraft</legend>
          <label className="inline">
            <input
              type="radio"
              name="aircraft"
              checked={form.aircraftSource === 'selection'}
              onChange={() => {
                set({ aircraftSource: 'selection' });
              }}
            />{' '}
            The selection ({selected.size})
          </label>
          <label className="inline">
            <input
              type="radio"
              name="aircraft"
              checked={form.aircraftSource === 'group'}
              onChange={() => {
                set({ aircraftSource: 'group' });
              }}
            />{' '}
            A group
          </label>
          {form.aircraftSource === 'group' && (
            <select
              aria-label="Group to plan for"
              value={form.groupId}
              onChange={(e) => {
                set({ groupId: e.target.value });
              }}
            >
              <option value="">Choose…</option>
              {groups.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name} ({g.aircraft_ids.length})
                </option>
              ))}
            </select>
          )}
        </fieldset>
        {!built.ok && (
          <ul className="issues">
            {built.errors.map((e) => (
              <li key={e} data-level="warning">
                {e}
              </li>
            ))}
          </ul>
        )}
        <div className="row">
          <button type="submit" disabled={busy || !built.ok}>
            Preview
          </button>
          <button type="button" disabled={busy || !preview} onClick={() => void run(false)}>
            Save plan
          </button>
        </div>
      </form>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {preview && <PlanReport plan={preview} />}
    </section>
  );
}
