// Sending commands (ADR 0011, ADR 0020). The server decides everything: who may, what the
// aircraft can do now, and what needs a confirmation. A 428 carries the summary the operator
// must see; the identical request plus its token then executes it.
import { api, ProblemError } from '../api/client';
import type { CommandRequest, CommandView, ConfirmationProblem } from '../api/types';

export type Outcome =
  | { status: 'done'; command: CommandView }
  | { status: 'confirm'; request: CommandRequest; problem: ConfirmationProblem };

/** Omit that keeps a union a union (one member per command kind). */
type DistributiveOmit<T, K extends PropertyKey> = T extends unknown ? Omit<T, K> : never;

export type CommandBody = DistributiveOmit<
  CommandRequest,
  'command_id' | 'confirmation_token' | 'aircraft_ids'
>;

export function newRequest(body: CommandBody, aircraftIds: string[]): CommandRequest {
  return {
    ...body,
    command_id: crypto.randomUUID(),
    aircraft_ids: aircraftIds,
    confirmation_token: null,
  };
}

/** Send a command; a 428 comes back as 'confirm' with the server's summary. */
export async function submit(request: CommandRequest, token: string): Promise<Outcome> {
  try {
    const command = await api<CommandView>('/commands', { method: 'POST', body: request, token });
    return { status: 'done', command };
  } catch (error) {
    if (error instanceof ProblemError && error.status === 428) {
      return {
        status: 'confirm',
        request,
        problem: error.problem as unknown as ConfirmationProblem,
      };
    }
    throw error;
  }
}

/** Re-send the identical request with the confirmation token. */
export async function confirm(
  request: CommandRequest,
  problem: ConfirmationProblem,
  token: string,
): Promise<Outcome> {
  return submit({ ...request, confirmation_token: problem.confirmation_token }, token);
}
