// The aircraft's own failsafes (M6, ADR 0035): the last preflight check of its autopilot
// parameters, and a button to read them again. Arm and takeoff run the check on the server
// whatever this shows; blocking findings refuse them unless a supervisor overrides.
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { api, ProblemError } from '../api/client';
import type { PreflightReportView } from '../api/types';
import { can, useSession } from '../session/session';

export function PreflightSection({ aircraftId }: { aircraftId: string }) {
  const session = useSession((s) => s.session);
  const token = session?.token ?? null;
  const queryClient = useQueryClient();
  const key = ['preflight', aircraftId];
  const report = useQuery({
    queryKey: key,
    queryFn: ({ signal }) =>
      api<PreflightReportView>(`/aircraft/${aircraftId}/preflight`, { token, signal }),
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const check = async () => {
    setBusy(true);
    setError(null);
    try {
      const fresh = await api<PreflightReportView>(`/aircraft/${aircraftId}/preflight`, {
        method: 'POST',
        token,
      });
      queryClient.setQueryData(key, fresh);
    } catch (e) {
      setError(e instanceof ProblemError ? e.message : 'The check failed.');
    } finally {
      setBusy(false);
    }
  };

  const data = report.data;
  let status = 'not checked yet';
  if (data?.checked_at) {
    const at = new Date(data.checked_at).toLocaleTimeString();
    status = data.ready ? `ready (checked ${at})` : `blocked (checked ${at})`;
  }
  return (
    <section className="preflight" aria-label="Preflight">
      <h3>
        Preflight <span className={data?.ready ? 'ok' : 'warning'}>{status}</span>
      </h3>
      {data && data.findings.length > 0 && (
        <ul className="summary-list">
          {data.findings.map((f) => (
            <li key={f.parameter} data-severity={f.severity}>
              {f.severity === 'block' ? '⛔' : '⚠'} <code>{f.parameter}</code> {f.message}
            </li>
          ))}
        </ul>
      )}
      {can(session, 'aircraft.command') && (
        <button type="button" onClick={() => void check()} disabled={busy}>
          {busy ? 'Reading parameters…' : 'Check failsafes'}
        </button>
      )}
      {error && <p className="error">{error}</p>}
    </section>
  );
}
