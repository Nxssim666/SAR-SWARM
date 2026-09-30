// One mission: its route (waypoint missions), plan, saved plan on the map, start / pause /
// resume, and progress with coverage (ADR 0028). Starting sends mission_start to the planned
// aircraft through the command flow: the server's 428 summary is confirmed with a held
// press, and a plan with issues needs a supervisor's override (ADR 0011, ADR 0029).
import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';

import { api } from '../api/client';
import type { GroupPage, MissionOut } from '../api/types';
import { useCommandFlow } from '../commands/flow';
import { useLive } from '../live/store';
import { boundsOf, useMapState } from '../map/mapState';
import { can, useSession } from '../session/session';
import { percent } from './format';
import { PlanReport } from './PlanReport';
import { PlanSection } from './PlanSection';
import { useProgress, useSavedPlan } from './queries';
import { usePlanning } from './store';
import { WaypointEditor } from './WaypointEditor';

const TASK_STATUS: Record<string, string> = {
  pending: '… pending',
  active: '▶ flying',
  completed: '✔ done',
  failed: '✕ failed',
  cancelled: '⊘ cancelled',
};

export function MissionDetail({ mission, onClose }: { mission: MissionOut; onClose: () => void }) {
  const session = useSession((s) => s.session);
  const live = useLive((s) => s.missions[mission.id]);
  const connection = useLive((s) => s.connection);
  const status = live?.status ?? mission.status;
  const flying = status === 'active' || status === 'paused';
  const saved = useSavedPlan(mission);
  const progress = useProgress(mission, flying);
  const flow = useCommandFlow();
  const groups = useQuery({
    queryKey: ['groups'],
    queryFn: ({ signal }) =>
      api<GroupPage>('/groups?limit=200', { token: session?.token ?? null, signal }),
  });
  const editable = (status === 'draft' || status === 'planned') && can(session, 'missions.plan');
  const plan = saved.data ?? null;
  const tasked = plan?.tasks.map((t) => t.aircraft_id) ?? [];
  const mayCommand = can(session, 'aircraft.command') && connection === 'online';

  // Draw the saved plan's routes and show them.
  useEffect(() => {
    if (!plan) return;
    usePlanning.getState().setRoutes(plan.tasks);
    const bounds = boundsOf(
      plan.tasks.flatMap((t) =>
        t.waypoints.map((w) => [w.longitude, w.latitude] as [number, number]),
      ),
    );
    if (bounds) useMapState.getState().showBounds(bounds);
  }, [plan]);

  // Coverage on the map while the mission flies (and after).
  const coverage = progress.data?.coverage_geometry ?? null;
  useEffect(() => {
    usePlanning.getState().setCoverage(coverage as GeoJSON.Geometry | null);
  }, [coverage]);

  const tasks = live?.tasks ?? progress.data?.tasks ?? [];
  const coverageShare = live?.coverage ?? progress.data?.coverage ?? null;

  return (
    <>
      <section className="panel" aria-label="Mission">
        <div className="row spread">
          <h2>{mission.name}</h2>
          <button type="button" onClick={onClose}>
            ← Missions
          </button>
        </div>
        <p>
          Status: <strong data-testid="mission-status">{status}</strong> · altitude{' '}
          {mission.default_altitude_relative_m} m above home
          {mission.default_speed_mps ? ` · ${String(mission.default_speed_mps)} m/s` : ''}
        </p>
        {mission.kind === 'swarm_area' && (
          <p className="muted">
            A swarm mission is planned on board by the swarm; start it from the command bar.
          </p>
        )}
        {plan && (status === 'planned' || flying) && mayCommand && (
          <div className="row">
            {status === 'planned' && (
              <button
                type="button"
                className="command"
                disabled={flow.busy}
                onClick={() =>
                  void flow.sendTo({ kind: 'mission_start', mission_id: mission.id }, tasked)
                }
              >
                Start mission ({tasked.length})
              </button>
            )}
            {status === 'active' && (
              <button
                type="button"
                className="command"
                disabled={flow.busy}
                onClick={() => void flow.sendTo({ kind: 'mission_pause' }, tasked)}
              >
                Pause
              </button>
            )}
            {status === 'paused' && (
              <button
                type="button"
                className="command"
                disabled={flow.busy}
                onClick={() => void flow.sendTo({ kind: 'resume' }, tasked)}
              >
                Resume
              </button>
            )}
          </div>
        )}
        {status !== 'draft' && (
          <>
            <p>
              Coverage: <strong data-testid="mission-coverage">{percent(coverageShare)}</strong>{' '}
              <span className="muted">(what was flown over, not a probability of detection)</span>
            </p>
            {tasks.length > 0 && (
              <table className="plan-tasks">
                <thead>
                  <tr>
                    <th>Aircraft</th>
                    <th>Task</th>
                    <th>Waypoint</th>
                  </tr>
                </thead>
                <tbody>
                  {tasks.map((t) => (
                    <tr key={t.task_id}>
                      <td>{t.callsign}</td>
                      <td>{TASK_STATUS[t.status] ?? t.status}</td>
                      <td>
                        {t.item !== null && t.items !== null
                          ? `${String(t.item)} / ${String(t.items)}`
                          : '–'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </section>
      {mission.kind === 'waypoint' && <WaypointEditor mission={mission} editable={editable} />}
      {editable && mission.kind !== 'swarm_area' && (
        <PlanSection
          mission={mission}
          groups={groups.data?.items ?? []}
          onSaved={() => undefined}
        />
      )}
      {plan && (
        <section className="panel" aria-label="Saved plan">
          <h2>Saved plan</h2>
          <PlanReport plan={plan} />
        </section>
      )}
    </>
  );
}
