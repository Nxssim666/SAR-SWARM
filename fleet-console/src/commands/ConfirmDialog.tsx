// The confirmation of a risky or bulk command (ADR 0011): it shows the server's own summary,
// names the aircraft count, lists warnings and the aircraft that will be rejected, and flags
// an override. Focus starts on Cancel; confirming takes a held press (HoldToConfirm).
import * as Dialog from '@radix-ui/react-dialog';
import { useRef } from 'react';

import type { ConfirmationProblem } from '../api/types';
import { HoldToConfirm } from './HoldToConfirm';
import { KIND_LABEL } from './labels';

interface Props {
  problem: ConfirmationProblem;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({ problem, busy, onConfirm, onCancel }: Props) {
  const cancel = useRef<HTMLButtonElement>(null);
  const { summary } = problem;
  const count = summary.aircraft.length;
  const kind = KIND_LABEL[summary.kind] ?? summary.kind.toUpperCase();
  const title = `${kind} ${String(count)} aircraft?`;

  return (
    <Dialog.Root
      open
      onOpenChange={(open) => {
        if (!open) onCancel();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content
          className="dialog"
          onOpenAutoFocus={(e) => {
            e.preventDefault();
            cancel.current?.focus();
          }}
        >
          <Dialog.Title>{title}</Dialog.Title>
          <Dialog.Description>
            Confirmation required: {summary.reasons.join('; ')}.
          </Dialog.Description>
          {summary.override && (
            <p className="warning-box" role="note">
              ⚠ Override: this takes command of aircraft another operator controls.
            </p>
          )}
          <h3>
            {count} aircraft {count === 1 ? 'receives' : 'receive'} it
          </h3>
          <ul className="summary-list">
            {summary.aircraft.map((a) => (
              <li key={a.aircraft_id}>
                <strong>{a.callsign}</strong>
                {a.warnings.length > 0 && (
                  <span className="warning"> ⚠ {a.warnings.join(', ')}</span>
                )}
              </li>
            ))}
          </ul>
          {summary.rejected.length > 0 && (
            <>
              <h3>{summary.rejected.length} will not be sent</h3>
              <ul className="summary-list rejected">
                {summary.rejected.map((r) => (
                  <li key={r.aircraft_id}>
                    <strong>{r.callsign ?? r.aircraft_id}</strong>: {r.message}
                  </li>
                ))}
              </ul>
            </>
          )}
          <div className="dialog-actions">
            <button ref={cancel} type="button" onClick={onCancel}>
              Cancel
            </button>
            <HoldToConfirm
              label={`Confirm ${kind} (${String(count)})`}
              onConfirm={onConfirm}
              disabled={busy}
            />
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
