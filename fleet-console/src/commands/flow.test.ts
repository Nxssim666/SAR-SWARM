import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useSelection } from '../selection/store';
import { useSession } from '../session/session';
import { command } from '../test/fixtures';
import { useCommandFlow } from './flow';

function json(status: number, body: unknown, type = 'application/json'): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': type } });
}

const CONFIRMATION = {
  type: 'urn:sar-gcs:problem:confirmation-required',
  title: 'Confirmation required',
  status: 428,
  detail: 'Confirm arm for 2 aircraft.',
  instance: '/api/v1/commands',
  command_id: 'c1',
  confirmation_token: 'tok-1',
  expires_at: '2026-09-30T00:00:30Z',
  summary: {
    kind: 'arm',
    params: {},
    reasons: ['arm always needs confirmation'],
    override: false,
    aircraft: [],
    rejected: [],
  },
};

describe('command flow', () => {
  beforeEach(() => {
    useSession.getState().signIn({
      token: 'sgcs_t',
      user: { user_id: 'u', username: 'op', display_name: 'Op' },
      permissions: ['aircraft.hold', 'aircraft.command'],
      expiresAt: '2026-09-30T04:00:00Z',
    });
    useSelection.getState().select(['a1', 'a2']);
    useCommandFlow.setState({ busy: false, pending: null, lastCommandId: null, error: null });
  });

  it('sends the selection with a fresh command id and the bearer token', async () => {
    const fetchMock = vi.fn(() => Promise.resolve(json(200, command('c9', 'completed'))));
    vi.stubGlobal('fetch', fetchMock);

    await useCommandFlow.getState().send({ kind: 'hold' });

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const body = JSON.parse(init.body as string) as Record<string, unknown>;
    expect(url).toBe('/api/v1/commands');
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer sgcs_t');
    expect(body).toMatchObject({
      kind: 'hold',
      aircraft_ids: ['a1', 'a2'],
      confirmation_token: null,
    });
    expect(body.command_id).toMatch(/^[0-9a-f-]{36}$/);
    expect(useCommandFlow.getState().lastCommandId).toBe('c9');
  });

  it('asks for confirmation on 428, then re-sends the identical request with the token', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json(428, CONFIRMATION, 'application/problem+json'))
      .mockResolvedValueOnce(json(200, command('c1', 'completed')));
    vi.stubGlobal('fetch', fetchMock);

    await useCommandFlow.getState().send({ kind: 'arm' });
    expect(useCommandFlow.getState().pending?.problem.confirmation_token).toBe('tok-1');

    await useCommandFlow.getState().confirmPending();

    const first = JSON.parse(
      (fetchMock.mock.calls[0] as [string, RequestInit])[1].body as string,
    ) as Record<string, unknown>;
    const second = JSON.parse(
      (fetchMock.mock.calls[1] as [string, RequestInit])[1].body as string,
    ) as Record<string, unknown>;
    expect(second).toEqual({ ...first, confirmation_token: 'tok-1' });
    expect(useCommandFlow.getState().pending).toBeNull();
    expect(useCommandFlow.getState().lastCommandId).toBe('c1');
  });

  it("shows the server's problem detail when it refuses", async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          json(
            403,
            {
              type: 'urn:sar-gcs:problem:forbidden',
              title: 'Forbidden',
              status: 403,
              detail: 'Not permitted.',
              instance: null,
              errors: null,
            },
            'application/problem+json',
          ),
        ),
      ),
    );

    await useCommandFlow.getState().send({ kind: 'land' });

    expect(useCommandFlow.getState().error).toBe('Not permitted.');
  });

  it('a 401 ends the session', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          json(401, {
            type: 'x',
            title: 'Unauthorized',
            status: 401,
            detail: null,
            instance: null,
            errors: null,
          }),
        ),
      ),
    );

    await useCommandFlow.getState().send({ kind: 'hold' });

    expect(useSession.getState().session).toBeNull();
    expect(useSession.getState().ended).toMatch(/sign in again/);
  });

  it('sends nothing without a selection', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    useSelection.getState().clear();

    await useCommandFlow.getState().send({ kind: 'hold' });

    expect(fetchMock).not.toHaveBeenCalled();
  });
});
