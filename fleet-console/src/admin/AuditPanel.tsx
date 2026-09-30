// The audit viewer (M5): search the hash-chained trail by action, entity, actor and time,
// newest first; verify the chain; export the selection (CSV or JSON Lines; the export is
// itself audited by the server).
import { useInfiniteQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { api, ProblemError } from '../api/client';
import { useSession } from '../session/session';
import { auditQuery, type AuditFilterForm, EMPTY_FILTERS, summarize } from './auditFilters';

interface AuditEvent {
  seq: number;
  ts: string;
  actor_username: string | null;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  details: Record<string, unknown>;
}

interface ChainStatus {
  ok: boolean;
  events: number;
  head_seq: number | null;
  head_hash: string | null;
  broken_at_seq: number | null;
  reason: string | null;
  verified_at: string;
}

export function AuditPanel() {
  const token = useSession((s) => s.session?.token ?? null);
  const [form, setForm] = useState<AuditFilterForm>(EMPTY_FILTERS);
  const [applied, setApplied] = useState<AuditFilterForm>(EMPTY_FILTERS);
  const [chain, setChain] = useState<ChainStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const events = useInfiniteQuery({
    queryKey: ['audit', applied],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      api<{ items: AuditEvent[]; next_cursor: string | null }>(
        `/audit?${auditQuery(applied, { limit: '50', ...(pageParam ? { cursor: pageParam } : {}) })}`,
        { token, signal },
      ),
    getNextPageParam: (last) => last.next_cursor,
  });

  const verify = async () => {
    setError(null);
    try {
      setChain(await api<ChainStatus>('/audit/verify', { token }));
    } catch (e) {
      setError(e instanceof ProblemError ? e.message : 'The chain could not be verified.');
    }
  };

  const exportAs = async (format: 'csv' | 'jsonl') => {
    setError(null);
    const response = await fetch(`/api/v1/audit/export?${auditQuery(applied, { format })}`, {
      headers: { Authorization: `Bearer ${token ?? ''}` },
      cache: 'no-store',
    });
    if (!response.ok) {
      setError(`The export failed (HTTP ${String(response.status)}).`);
      return;
    }
    const name =
      /filename="([^"]+)"/.exec(response.headers.get('Content-Disposition') ?? '')?.[1] ??
      `audit.${format}`;
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement('a');
    link.href = url;
    link.download = name;
    link.click();
    URL.revokeObjectURL(url);
  };

  const set = (change: Partial<AuditFilterForm>) => {
    setForm((f) => ({ ...f, ...change }));
  };
  const items = events.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <section aria-label="Audit">
      <div className="row">
        <button type="button" onClick={() => void verify()}>
          Verify chain
        </button>
        {chain && (
          <span role="status" className={chain.ok ? 'ok-text' : 'error'}>
            {chain.ok
              ? `✓ Intact: ${String(chain.events)} events, head #${String(chain.head_seq)} ${chain.head_hash?.slice(0, 16) ?? ''}…`
              : `✕ BROKEN at #${String(chain.broken_at_seq)}: ${chain.reason ?? ''}`}
          </span>
        )}
      </div>
      <form
        className="filters"
        onSubmit={(e) => {
          e.preventDefault();
          setApplied(form);
        }}
      >
        <label>
          Action starts with
          <input
            value={form.action}
            placeholder="e.g. command. or auth."
            onChange={(e) => {
              set({ action: e.target.value });
            }}
          />
        </label>
        <label>
          Entity type
          <input
            value={form.entityType}
            placeholder="e.g. aircraft"
            onChange={(e) => {
              set({ entityType: e.target.value });
            }}
          />
        </label>
        <label>
          Entity id
          <input
            value={form.entityId}
            onChange={(e) => {
              set({ entityId: e.target.value });
            }}
          />
        </label>
        <label>
          From
          <input
            type="datetime-local"
            value={form.since}
            onChange={(e) => {
              set({ since: e.target.value });
            }}
          />
        </label>
        <label>
          To
          <input
            type="datetime-local"
            value={form.until}
            onChange={(e) => {
              set({ until: e.target.value });
            }}
          />
        </label>
        <button type="submit">Search</button>
        <button type="button" onClick={() => void exportAs('csv')}>
          Export CSV
        </button>
        <button type="button" onClick={() => void exportAs('jsonl')}>
          Export JSON Lines
        </button>
      </form>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <table className="admin-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Time</th>
            <th>Who</th>
            <th>Action</th>
            <th>Entity</th>
            <th>Details</th>
          </tr>
        </thead>
        <tbody>
          {items.map((e) => (
            <tr key={e.seq}>
              <td>{e.seq}</td>
              <td>{new Date(e.ts).toLocaleString()}</td>
              <td>{e.actor_username ?? 'system'}</td>
              <td>{e.action}</td>
              <td>{e.entity_type ? `${e.entity_type} ${e.entity_id ?? ''}` : ''}</td>
              <td className="details">{summarize(e.details)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {events.hasNextPage && (
        <button type="button" onClick={() => void events.fetchNextPage()}>
          Older events
        </button>
      )}
    </section>
  );
}
