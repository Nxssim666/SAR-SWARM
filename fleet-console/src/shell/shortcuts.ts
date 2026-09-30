// Keyboard shortcuts (ADR 0027). HOLD is the only command with a key: it only makes things
// safer, and a bulk HOLD still asks for confirmation. Risky commands have no key at all.
import { useEffect } from 'react';

import { availability } from '../commands/availability';
import { useCommandFlow } from '../commands/flow';
import { useLive } from '../live/store';
import { useMapState } from '../map/mapState';
import { useSelection } from '../selection/store';
import { useSession } from '../session/session';

export const SHORTCUTS: { keys: string; action: string }[] = [
  { keys: '?', action: 'Show or hide this help' },
  { keys: 'H', action: 'Hold the selected aircraft (several: asks for confirmation)' },
  { keys: 'B', action: 'Box selection on the map' },
  { keys: 'L', action: 'Lasso selection on the map' },
  { keys: 'G', action: 'Pick a goto target on the map' },
  { keys: 'Ctrl+A', action: 'Select all aircraft' },
  { keys: 'Esc', action: 'Clear the selection and the active tool' },
];

function typing(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target.isContentEditable ||
    ['INPUT', 'SELECT', 'TEXTAREA'].includes(target.tagName) ||
    target.closest('[role="dialog"]') !== null
  );
}

/** Handle one key; returns true when it was a shortcut. Exported for tests. */
export function handleKey(event: KeyboardEvent, toggleHelp: () => void): boolean {
  if (typing(event.target) || event.altKey) return false;
  const key = event.key.toLowerCase();
  const selection = useSelection.getState();
  if ((event.ctrlKey || event.metaKey) && key === 'a') {
    selection.select(Object.keys(useLive.getState().aircraft));
    return true;
  }
  if (event.ctrlKey || event.metaKey) return false;
  switch (key) {
    case '?':
      toggleHelp();
      return true;
    case 'escape':
      selection.clear();
      selection.setTool('pan');
      useMapState.getState().setGotoTarget(null);
      return true;
    case 'b':
      selection.setTool('box');
      return true;
    case 'l':
      selection.setTool('lasso');
      return true;
    case 'g':
      selection.setTool('goto');
      return true;
    case 'h': {
      const session = useSession.getState().session;
      const live = useLive.getState();
      const selected = [...selection.selected]
        .map((id) => live.aircraft[id])
        .filter((a) => a !== undefined);
      const state = availability('hold', {
        connection: live.connection,
        permissions: session?.permissions ?? [],
        userId: session?.user.user_id ?? '',
        selected,
        leases: live.leases,
      });
      if (state.enabled) void useCommandFlow.getState().send({ kind: 'hold' });
      return true;
    }
    default:
      return false;
  }
}

export function useShortcuts(toggleHelp: () => void): void {
  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      if (handleKey(event, toggleHelp)) event.preventDefault();
    };
    window.addEventListener('keydown', listener);
    return () => {
      window.removeEventListener('keydown', listener);
    };
  }, [toggleHelp]);
}
