// The command in progress: sent, awaiting the operator's confirmation, or done. Shared by
// the command bar and the keyboard shortcuts.
import { create } from 'zustand';

import { ProblemError } from '../api/client';
import type { CommandRequest, ConfirmationProblem } from '../api/types';
import { useSelection } from '../selection/store';
import { useSession } from '../session/session';
import { type CommandBody, confirm, newRequest, submit } from './api';

interface FlowState {
  busy: boolean;
  pending: { request: CommandRequest; problem: ConfirmationProblem } | null;
  lastCommandId: string | null;
  error: string | null;
  send: (body: CommandBody) => Promise<void>;
  /** Send to these aircraft rather than the selection (a mission's planned aircraft). */
  sendTo: (body: CommandBody, aircraftIds: readonly string[]) => Promise<void>;
  confirmPending: () => Promise<void>;
  cancelPending: () => void;
}

export const useCommandFlow = create<FlowState>()((set, get) => {
  const run = async (step: (token: string) => ReturnType<typeof submit>) => {
    const token = useSession.getState().session?.token;
    if (!token) return;
    set({ busy: true, error: null });
    try {
      const outcome = await step(token);
      if (outcome.status === 'confirm') {
        set({ busy: false, pending: { request: outcome.request, problem: outcome.problem } });
      } else {
        set({ busy: false, pending: null, lastCommandId: outcome.command.id });
      }
    } catch (error) {
      set({
        busy: false,
        pending: null,
        error: error instanceof ProblemError ? error.message : 'The command could not be sent.',
      });
    }
  };

  return {
    busy: false,
    pending: null,
    lastCommandId: null,
    error: null,
    send: async (body) => {
      const ids = [...useSelection.getState().selected];
      if (ids.length === 0 || get().busy) return;
      await run((token) => submit(newRequest(body, ids), token));
    },
    sendTo: async (body, aircraftIds) => {
      if (aircraftIds.length === 0 || get().busy) return;
      await run((token) => submit(newRequest(body, [...aircraftIds]), token));
    },
    confirmPending: async () => {
      const pending = get().pending;
      if (!pending) return;
      await run((token) => confirm(pending.request, pending.problem, token));
    },
    cancelPending: () => {
      set({ pending: null });
    },
  };
});
