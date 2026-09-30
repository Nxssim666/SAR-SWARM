// The aircraft registry (M6): list, register and remove aircraft. Everyone with the admin
// dialog sees the list; supervisors (fleet.manage) change it. The fleet service checks the
// links (a MAVLink connection with a system id unique on it, a swarm drone id) and audits it.
// In simulation mode every registered aircraft is simulated.
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { api, ProblemError } from '../api/client';
import type { Airframe } from '../api/types';
import { can, useSession } from '../session/session';
import { DEFAULT_MAVLINK, registration } from './registration';

interface AircraftOut {
  id: string;
  callsign: string;
  airframe: Airframe;
  mavlink_connection: string | null;
  mavlink_system_id: number | null;
  swarm_drone_id: number | null;
}

const AIRFRAMES: { value: Airframe; label: string }[] = [
  { value: 'multirotor_hexa', label: 'Hexacopter' },
  { value: 'multirotor_quad', label: 'Quadcopter' },
  { value: 'fixed_wing', label: 'Fixed-wing' },
];

export function AircraftPanel() {
  const session = useSession((s) => s.session);
  const token = session?.token ?? null;
  const queryClient = useQueryClient();
  const aircraft = useQuery({
    queryKey: ['aircraft-registry'],
    queryFn: ({ signal }) =>
      api<{ items: AircraftOut[] }>('/aircraft?limit=200', { token, signal }),
  });
  const manage = can(session, 'fleet.manage');
  const [callsign, setCallsign] = useState('');
  const [airframe, setAirframe] = useState<Airframe>('multirotor_hexa');
  const [connection, setConnection] = useState(DEFAULT_MAVLINK);
  const [systemId, setSystemId] = useState('');
  const [droneId, setDroneId] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['aircraft-registry'] });

  const register = async () => {
    setBusy(true);
    setError(null);
    try {
      await api('/aircraft', {
        method: 'POST',
        body: registration({ callsign, airframe, connection, systemId, droneId }),
        token,
      });
      setCallsign('');
      setSystemId('');
      setDroneId('');
      await refresh();
    } catch (e) {
      setError(e instanceof ProblemError ? e.message : 'The aircraft could not be registered.');
    } finally {
      setBusy(false);
    }
  };

  const remove = async (a: AircraftOut) => {
    if (!window.confirm(`Remove ${a.callsign} from the registry? Its history is kept.`)) return;
    setError(null);
    try {
      await api(`/aircraft/${a.id}`, { method: 'DELETE', token });
      await refresh();
    } catch (e) {
      setError(e instanceof ProblemError ? e.message : 'The aircraft could not be removed.');
    }
  };

  return (
    <section aria-label="Aircraft registry">
      <table className="admin-table">
        <thead>
          <tr>
            <th>Callsign</th>
            <th>Airframe</th>
            <th>MAVLink</th>
            <th>Swarm</th>
            {manage && <th aria-label="Actions" />}
          </tr>
        </thead>
        <tbody>
          {aircraft.data?.items.map((a) => (
            <tr key={a.id}>
              <td>
                <strong>{a.callsign}</strong>
              </td>
              <td>{AIRFRAMES.find((f) => f.value === a.airframe)?.label ?? a.airframe}</td>
              <td>
                {a.mavlink_system_id !== null
                  ? `${a.mavlink_connection ?? ''} · id ${String(a.mavlink_system_id)}`
                  : '—'}
              </td>
              <td>{a.swarm_drone_id !== null ? `drone ${String(a.swarm_drone_id)}` : '—'}</td>
              {manage && (
                <td>
                  <button type="button" onClick={() => void remove(a)}>
                    Remove
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {aircraft.data?.items.length === 0 && <p className="muted">No aircraft registered.</p>}
      {manage && (
        <form
          className="form"
          aria-label="Register an aircraft"
          onSubmit={(e) => {
            e.preventDefault();
            void register();
          }}
        >
          <h3>Register an aircraft</h3>
          <label>
            Callsign
            <input
              value={callsign}
              maxLength={32}
              onChange={(e) => {
                setCallsign(e.target.value);
              }}
            />
          </label>
          <label>
            Airframe{' '}
            <select
              value={airframe}
              onChange={(e) => {
                setAirframe(e.target.value as Airframe);
              }}
            >
              {AIRFRAMES.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            MAVLink system id (1–255; empty: no MAVLink link)
            <input
              type="number"
              min={1}
              max={255}
              value={systemId}
              onChange={(e) => {
                setSystemId(e.target.value);
              }}
            />
          </label>
          <label>
            MAVLink connection
            <input
              value={connection}
              onChange={(e) => {
                setConnection(e.target.value);
              }}
            />
          </label>
          <label>
            Swarm drone id (onboard swarm_sar companion; optional)
            <input
              type="number"
              min={0}
              value={droneId}
              onChange={(e) => {
                setDroneId(e.target.value);
              }}
            />
          </label>
          <button type="submit" disabled={busy || !callsign.trim()}>
            Register
          </button>
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
