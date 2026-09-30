// Handover requests for aircraft I control (M5): who asks, a countdown, accept or decline.
// Unanswered requests expire on the server; control never changes without the holder's
// answer, except by a supervisor's audited assignment.
import { useEffect, useState } from 'react';

import { api, ProblemError } from '../api/client';
import { useLive } from '../live/store';
import { useSession } from '../session/session';
import { secondsLeft } from './ownership';

export function HandoverPrompts() {
  const session = useSession((s) => s.session);
  const leases = useLive((s) => s.leases);
  const aircraft = useLive((s) => s.aircraft);
  const [now, setNow] = useState(() => Date.now());
  const [error, setError] = useState<string | null>(null);
  const me = session?.user.user_id;
  const asked = Object.values(leases).filter(
    (l) => l.holder.user_id === me && l.pending_request !== null,
  );

  useEffect(() => {
    if (asked.length === 0) return;
    const timer = window.setInterval(() => {
      setNow(Date.now());
    }, 1000);
    return () => {
      window.clearInterval(timer);
    };
  }, [asked.length]);

  if (!session || asked.length === 0) return null;

  const answer = async (aircraftId: string, verb: 'accept' | 'decline') => {
    setError(null);
    try {
      await api(`/aircraft/${aircraftId}/control/handover/${verb}`, {
        method: 'POST',
        token: session.token,
      });
    } catch (e) {
      setError(e instanceof ProblemError ? e.message : String(e));
    }
  };

  return (
    <div className="banner banner-handover" role="alert">
      {asked.map((lease) => {
        const request = lease.pending_request;
        if (!request) return null;
        const callsign = aircraft[lease.aircraft_id]?.callsign ?? lease.aircraft_id;
        return (
          <div key={lease.aircraft_id} className="row">
            <span>
              <strong>{request.requested_by.display_name}</strong> asks for control of{' '}
              <strong>{callsign}</strong> ({secondsLeft(request.expires_at, now)} s left)
            </span>
            <button type="button" onClick={() => void answer(lease.aircraft_id, 'accept')}>
              Hand over {callsign}
            </button>
            <button type="button" onClick={() => void answer(lease.aircraft_id, 'decline')}>
              Keep {callsign}
            </button>
          </div>
        );
      })}
      {error && <p className="error">{error}</p>}
    </div>
  );
}
