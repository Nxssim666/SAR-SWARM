// Open alerts, most severe first. Severity shows as icon + word + colour (ADR 0015: alerts
// distinguishable by more than colour). The full alert engine and audible cues are M4.
import { useState } from 'react';

import { api, ProblemError } from '../api/client';
import { openAlerts } from '../live/store';
import { useThrottledLive } from '../live/useThrottled';
import { can, useSession } from '../session/session';
import { SEVERITY } from './severity';

export function AlertsStrip() {
  const alerts = useThrottledLive((s) => s.alerts);
  const aircraft = useThrottledLive((s) => s.aircraft);
  const session = useSession((s) => s.session);
  const [error, setError] = useState<string | null>(null);
  const open = openAlerts(alerts);

  const acknowledge = async (id: string) => {
    if (!session) return;
    try {
      await api(`/alerts/${id}/acknowledge`, { method: 'POST', token: session.token });
      setError(null);
    } catch (e) {
      setError(e instanceof ProblemError ? e.message : String(e));
    }
  };

  return (
    <section className="panel alerts" aria-label="Alerts">
      <h2>
        Alerts <span className="count">{open.length}</span>
      </h2>
      {open.length === 0 && <p className="muted">No open alerts.</p>}
      <ul>
        {open.map((a) => (
          <li key={a.id} className={`alert alert-${a.severity}`} data-state={a.state}>
            <span className="severity">
              <span aria-hidden="true">{SEVERITY[a.severity].icon}</span>{' '}
              {SEVERITY[a.severity].word}
            </span>{' '}
            {a.aircraft_id && aircraft[a.aircraft_id]
              ? `${aircraft[a.aircraft_id]?.callsign ?? ''}: `
              : ''}
            {a.message}
            {a.state === 'active' && can(session, 'alerts.ack') && (
              <button type="button" onClick={() => void acknowledge(a.id)}>
                Acknowledge
              </button>
            )}
            {a.state === 'acknowledged' && <span className="muted"> (acknowledged)</span>}
          </li>
        ))}
      </ul>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </section>
  );
}
