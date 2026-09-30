// Control of aircraft (ADR 0011, M5). Only the controller (or a supervisor, by override) may
// command an aircraft; HOLD is open to every operator.
// - Take control of free aircraft; release your own.
// - Aircraft another operator controls: ask them to hand over (they accept or decline; the
//   request expires unanswered).
// - Supervisors: assign control to someone, or release it by force, always with a reason.
import * as Dialog from '@radix-ui/react-dialog';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { api, ProblemError } from '../api/client';
import type { UserRef } from '../api/types';
import { useLive } from '../live/store';
import { can, useSession } from '../session/session';
import { ownerColor } from './ownership';

export function LeaseControls({ aircraftIds }: { aircraftIds: string[] }) {
  const session = useSession((s) => s.session);
  const leases = useLive((s) => s.leases);
  const connection = useLive((s) => s.connection);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [assigning, setAssigning] = useState(false);

  if (!session || !can(session, 'aircraft.command')) return null;
  const me = session.user.user_id;
  const free = aircraftIds.filter((id) => !leases[id]);
  const mine = aircraftIds.filter((id) => leases[id]?.holder.user_id === me);
  const others = aircraftIds.filter((id) => {
    const lease = leases[id];
    return lease && lease.holder.user_id !== me && !lease.pending_request;
  });
  const offline = connection !== 'online';
  const supervisor = can(session, 'control.override');

  const run = async (ids: string[], path: string, method: 'POST' | 'DELETE') => {
    setBusy(true);
    setError(null);
    const failures: string[] = [];
    for (const id of ids) {
      try {
        await api(`/aircraft/${id}/control${path}`, { method, token: session.token });
      } catch (e) {
        failures.push(e instanceof ProblemError ? e.message : String(e));
      }
    }
    setBusy(false);
    if (failures.length) setError(failures.join(' '));
  };
  const count = (ids: string[]) => (ids.length > 1 ? ` (${String(ids.length)})` : '');

  return (
    <div className="lease-controls">
      <button
        type="button"
        disabled={busy || offline || free.length === 0}
        onClick={() => void run(free, '', 'POST')}
      >
        Take control{count(free)}
      </button>
      <button
        type="button"
        disabled={busy || offline || mine.length === 0}
        onClick={() => void run(mine, '', 'DELETE')}
      >
        Release{count(mine)}
      </button>
      {others.length > 0 && (
        <button
          type="button"
          disabled={busy || offline}
          title="Ask the controlling operator to hand over"
          onClick={() => void run(others, '/handover', 'POST')}
        >
          Request handover{count(others)}
        </button>
      )}
      {supervisor && (
        <button
          type="button"
          disabled={busy || offline || aircraftIds.length === 0}
          onClick={() => {
            setAssigning(true);
          }}
        >
          Assign…
        </button>
      )}
      {assigning && (
        <AssignDialog
          aircraftIds={aircraftIds}
          onClose={(message) => {
            setAssigning(false);
            setError(message);
          }}
        />
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </div>
  );
}

interface PresenceList {
  users: { user: UserRef; role: string; last_seen_at: string }[];
}

/** Supervisor: give control of the aircraft to an operator who is here, or to nobody. */
function AssignDialog({
  aircraftIds,
  onClose,
}: {
  aircraftIds: string[];
  onClose: (error: string | null) => void;
}) {
  const session = useSession((s) => s.session);
  const presence = useQuery({
    queryKey: ['presence'],
    queryFn: ({ signal }) =>
      api<PresenceList>('/presence', { token: session?.token ?? null, signal }),
  });
  const candidates = (presence.data?.users ?? []).filter(
    (p) => p.role === 'operator' || p.role === 'supervisor' || p.role === 'admin',
  );
  const [userId, setUserId] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const valid = reason.trim().length >= 3;

  const assign = async () => {
    setBusy(true);
    const failures: string[] = [];
    for (const id of aircraftIds) {
      try {
        await api(`/aircraft/${id}/control`, {
          method: 'PUT',
          body: { user_id: userId || null, reason: reason.trim() },
          token: session?.token ?? null,
        });
      } catch (e) {
        failures.push(e instanceof ProblemError ? e.message : String(e));
      }
    }
    onClose(failures.length ? failures.join(' ') : null);
  };

  return (
    <Dialog.Root
      open
      onOpenChange={(open) => {
        if (!open) onClose(null);
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog">
          <Dialog.Title>Assign control of {aircraftIds.length} aircraft</Dialog.Title>
          <Dialog.Description>
            This overrides whoever controls them now. It is audited with your reason.
          </Dialog.Description>
          <form
            className="form"
            onSubmit={(e) => {
              e.preventDefault();
              void assign();
            }}
          >
            <label>
              To
              <select
                value={userId}
                onChange={(e) => {
                  setUserId(e.target.value);
                }}
              >
                <option value="">Nobody (release by force)</option>
                {candidates.map((p) => (
                  <option key={p.user.user_id} value={p.user.user_id}>
                    {p.user.display_name} ({p.role})
                  </option>
                ))}
              </select>
            </label>
            {userId && (
              <p>
                <span
                  className="owner-chip"
                  style={{ background: ownerColor(userId) }}
                  aria-hidden="true"
                />{' '}
                Their aircraft are ringed in this colour.
              </p>
            )}
            <label>
              Reason
              <input
                value={reason}
                maxLength={500}
                onChange={(e) => {
                  setReason(e.target.value);
                }}
              />
            </label>
            <div className="dialog-actions">
              <button
                type="button"
                onClick={() => {
                  onClose(null);
                }}
              >
                Cancel
              </button>
              <button type="submit" disabled={busy || !valid}>
                Assign
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
