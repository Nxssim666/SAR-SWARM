// Commands for the selected aircraft. Buttons are offered or greyed out with the reason
// (availability.ts); the server decides. Risky or bulk commands open ConfirmDialog. The last
// command's per-aircraft outcome updates live from the `commands` topic.
import { useState } from 'react';

import type { AircraftLive, CommandTargetView } from '../api/types';
import { useLive } from '../live/store';
import { useThrottledLive } from '../live/useThrottled';
import { useMapState } from '../map/mapState';
import { useSelection } from '../selection/store';
import { useSession } from '../session/session';
import { availability, COMMANDS, type ConsoleCommand } from './availability';
import { ConfirmDialog } from './ConfirmDialog';
import { useCommandFlow } from './flow';
import { KIND_LABEL } from './labels';

const STATE_LABEL: Record<CommandTargetView['state'], string> = {
  pending: '… pending',
  dispatched: '→ sent',
  acked: '✓ acknowledged',
  nacked: '✕ refused',
  timeout: '⏱ no answer',
  rejected: '⊘ not sent',
  verified: '✔ done',
  unverified: '? effect not seen',
};

function useAvailability() {
  const session = useSession((s) => s.session);
  const selectedIds = useSelection((s) => s.selected);
  const aircraft = useThrottledLive((s) => s.aircraft);
  const leases = useThrottledLive((s) => s.leases);
  const connection = useLive((s) => s.connection);
  const selected = [...selectedIds].map((id) => aircraft[id]).filter((a): a is AircraftLive => !!a);
  return (kind: ConsoleCommand) =>
    availability(kind, {
      connection,
      permissions: session?.permissions ?? [],
      userId: session?.user.user_id ?? '',
      selected,
      leases,
    });
}

export function CommandBar() {
  const session = useSession((s) => s.session);
  const selectedCount = useSelection((s) => s.selected.size);
  const setTool = useSelection((s) => s.setTool);
  const gotoTarget = useMapState((s) => s.gotoTarget);
  const setGotoTarget = useMapState((s) => s.setGotoTarget);
  const flow = useCommandFlow();
  const commands = useLive((s) => s.commands);
  const available = useAvailability();
  const [altitude, setAltitude] = useState('30');

  if (!session?.permissions.includes('aircraft.hold')) return null; // observers: view only

  const altitudeValue = Number(altitude);
  const altitudeValid = Number.isFinite(altitudeValue) && altitudeValue > 0 && altitudeValue <= 120;
  const last = flow.lastCommandId ? commands[flow.lastCommandId] : undefined;

  const send = (kind: ConsoleCommand) => {
    if (kind === 'takeoff') {
      void flow.send({ kind, altitude_relative_m: altitudeValue });
    } else if (kind === 'goto') {
      if (!gotoTarget) {
        setTool('goto'); // pick the target on the map, then press Goto again
        return;
      }
      void flow.send({ kind, target: gotoTarget, altitude_relative_m: null });
      setGotoTarget(null);
    } else {
      void flow.send({ kind });
    }
  };

  return (
    <section className="command-bar" aria-label="Commands">
      <span className="selection-count" role="status">
        {selectedCount} selected
      </span>
      {COMMANDS.map(({ kind, label, key }) => {
        const state = available(kind);
        return (
          <button
            key={kind}
            type="button"
            className={`command command-${kind}`}
            disabled={!state.enabled || flow.busy || (kind === 'takeoff' && !altitudeValid)}
            title={
              !state.enabled
                ? state.reason
                : kind === 'takeoff' && !altitudeValid
                  ? 'Enter a takeoff altitude of 1 to 120 m.'
                  : key
                    ? `${label} (${key})`
                    : label
            }
            onClick={() => {
              send(kind);
            }}
          >
            {kind === 'goto' && gotoTarget ? 'Goto target' : label}
          </button>
        );
      })}
      <label className="altitude">
        Takeoff alt.
        <input
          type="number"
          min={1}
          max={120}
          value={altitude}
          aria-invalid={!altitudeValid}
          onChange={(e) => {
            setAltitude(e.target.value);
          }}
        />
        m
      </label>
      {flow.error && (
        <p role="alert" className="error">
          {flow.error}
        </p>
      )}
      {last && (
        <div className="last-command" aria-live="polite">
          <strong>{KIND_LABEL[last.kind] ?? last.kind}</strong>{' '}
          <ul>
            {last.targets.map((t) => (
              <li key={t.aircraft_id} data-state={t.state} title={t.reason ?? undefined}>
                {t.callsign ?? t.aircraft_id}: {STATE_LABEL[t.state]}
              </li>
            ))}
          </ul>
        </div>
      )}
      {flow.pending && (
        <ConfirmDialog
          problem={flow.pending.problem}
          busy={flow.busy}
          onConfirm={() => void flow.confirmPending()}
          onCancel={flow.cancelPending}
        />
      )}
    </section>
  );
}
