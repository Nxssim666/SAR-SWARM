// What a plan says (ADR 0028, ADR 0029): per aircraft its layer, speed, start delay, length
// and duration; conflicts and clearance issues, which a supervisor must override to start;
// and every note (fallbacks, infeasible turns, companions without avoidance).
import type { PlanOut } from '../api/types';
import { routeStyle } from './features';

function minutes(seconds: number): string {
  return seconds >= 90 ? `${(seconds / 60).toFixed(0)} min` : `${seconds.toFixed(0)} s`;
}

export function PlanReport({ plan }: { plan: PlanOut }) {
  const issues = plan.conflicts.length + plan.clearance.length;
  return (
    <div className="plan-report" aria-label="Plan report">
      <p className={issues > 0 ? 'warning-box' : 'ok-box'} role="status">
        {issues > 0
          ? `⚠ ${String(plan.conflicts.length)} conflict(s) and ${String(plan.clearance.length)} clearance issue(s): starting needs a supervisor's override.`
          : '✓ No conflicts: every pair of flights stays separated.'}
      </p>
      <p>
        {plan.dry_run ? 'Preview' : 'Saved plan'} · {plan.pattern.replace('_', ' ')} · lanes{' '}
        {plan.spacing_m.toFixed(0)} m apart · about {minutes(plan.duration_s)}
        {plan.coverage !== null ? ` · covers ${(plan.coverage * 100).toFixed(0)} %` : ''}
        {plan.unchecked_terrain > 0
          ? ` · ${String(plan.unchecked_terrain)} waypoint(s) over unknown terrain`
          : ''}
      </p>
      <table className="plan-tasks">
        <thead>
          <tr>
            <th>Aircraft</th>
            <th title="Altitude above home">Layer</th>
            <th>Speed</th>
            <th>Starts</th>
            <th>Length</th>
            <th>Takes</th>
          </tr>
        </thead>
        <tbody>
          {plan.tasks.map((t, i) => (
            <tr key={t.aircraft_id}>
              <td>
                <span
                  className="route-swatch"
                  style={{ borderColor: routeStyle(i).color }}
                  aria-hidden="true"
                />{' '}
                {t.callsign}
                {t.companion && <span title="Onboard obstacle avoidance is not active"> ⚠</span>}
              </td>
              <td>{t.layer_m.toFixed(0)} m</td>
              <td>{t.speed_mps.toFixed(0)} m/s</td>
              <td>+{t.start_delay_s.toFixed(0)} s</td>
              <td>{(t.length_m / 1000).toFixed(1)} km</td>
              <td>{minutes(t.duration_s)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {plan.conflicts.length > 0 && (
        <>
          <h3>Conflicts</h3>
          <ul className="issues">
            {plan.conflicts.map((c) => (
              <li key={`${c.aircraft_ids.join('-')}-${String(c.t_s)}`} data-level="error">
                {c.callsigns.join(' and ')} at +{c.t_s.toFixed(0)} s: {c.horizontal_m.toFixed(0)} m
                apart, {c.vertical_m.toFixed(0)} m vertically
              </li>
            ))}
          </ul>
        </>
      )}
      {plan.clearance.length > 0 && (
        <>
          <h3>Terrain clearance</h3>
          <ul className="issues">
            {plan.clearance.map((c) => (
              <li key={`${c.aircraft_id}-${String(c.waypoint)}`} data-level="error">
                {c.callsign}, waypoint {c.waypoint + 1}: {c.kind.replace('_', ' ')} (
                {c.height_m.toFixed(0)} m above ground)
              </li>
            ))}
          </ul>
        </>
      )}
      {(plan.notes.length > 0 || plan.tasks.some((t) => t.notes.length > 0)) && (
        <>
          <h3>Notes</h3>
          <ul className="issues">
            {plan.notes.map((n) => (
              <li key={n} data-level="warning">
                {n}
              </li>
            ))}
            {plan.tasks.flatMap((t) =>
              t.notes.map((n) => (
                <li key={`${t.aircraft_id}-${n}`} data-level="warning">
                  {t.callsign}: {n}
                </li>
              )),
            )}
          </ul>
        </>
      )}
    </div>
  );
}
