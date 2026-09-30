// Take or release control of aircraft (ADR 0011). Only the controller (or a supervisor, by
// override) may command an aircraft; HOLD is open to every operator. Handover requests and
// supervisor assignment come in M5.
import { useState } from 'react';

import { api, ProblemError } from '../api/client';
import { useLive } from '../live/store';
import { can, useSession } from '../session/session';

export function LeaseControls({ aircraftIds }: { aircraftIds: string[] }) {
  const session = useSession((s) => s.session);
  const leases = useLive((s) => s.leases);
  const connection = useLive((s) => s.connection);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!session || !can(session, 'aircraft.command')) return null;
  const me = session.user.user_id;
  const free = aircraftIds.filter((id) => !leases[id]);
  const mine = aircraftIds.filter((id) => leases[id]?.holder.user_id === me);
  const offline = connection !== 'online';

  const run = async (ids: string[], method: 'POST' | 'DELETE') => {
    setBusy(true);
    setError(null);
    const failures: string[] = [];
    for (const id of ids) {
      try {
        await api(`/aircraft/${id}/control`, { method, token: session.token });
      } catch (e) {
        failures.push(e instanceof ProblemError ? e.message : String(e));
      }
    }
    setBusy(false);
    if (failures.length) setError(failures.join(' '));
  };

  return (
    <div className="lease-controls">
      <button
        type="button"
        disabled={busy || offline || free.length === 0}
        onClick={() => void run(free, 'POST')}
      >
        Take control{free.length > 1 ? ` (${String(free.length)})` : ''}
      </button>
      <button
        type="button"
        disabled={busy || offline || mine.length === 0}
        onClick={() => void run(mine, 'DELETE')}
      >
        Release{mine.length > 1 ? ` (${String(mine.length)})` : ''}
      </button>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </div>
  );
}
