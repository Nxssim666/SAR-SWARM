import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ServerMessage } from './messages';
import { LiveSocket, PING_INTERVAL_MS, type SocketDeps, type SocketLike } from './socket';

class FakeSocket implements SocketLike {
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  sent: Record<string, unknown>[] = [];
  closedWith: number | null = null;

  send(data: string): void {
    this.sent.push(JSON.parse(data) as Record<string, unknown>);
  }
  close(code?: number): void {
    this.closedWith = code ?? 1000;
  }
  open(): void {
    this.onopen?.(new Event('open'));
  }
  receive(message: object): void {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(message) }));
  }
  drop(code: number, reason = ''): void {
    this.onclose?.({ code, reason } as CloseEvent);
  }
}

function welcome(seq = 1) {
  return {
    type: 'welcome',
    seq,
    ts: '2026-09-30T00:00:00Z',
    user: { user_id: 'u', username: 'op', display_name: 'Op' },
    role: 'operator',
    permissions: ['fleet.view'],
    session_expires_at: '2026-09-30T04:00:00Z',
    simulation: true,
  };
}

function snapshot(seq: number) {
  return {
    type: 'snapshot',
    topic: 'alerts',
    seq,
    ts: '2026-09-30T00:00:00Z',
    data: { alerts: [] },
  };
}

describe('LiveSocket', () => {
  let sockets: FakeSocket[];
  let deps: SocketDeps;
  let messages: ServerMessage[];
  let states: string[];
  let ended: string[];

  beforeEach(() => {
    vi.useFakeTimers();
    sockets = [];
    messages = [];
    states = [];
    ended = [];
    deps = {
      url: 'ws://test/api/v1/ws',
      create: () => {
        const socket = new FakeSocket();
        sockets.push(socket);
        return socket;
      },
      setTimeout: (callback, ms) => setTimeout(callback, ms),
      clearTimeout: (handle) => {
        clearTimeout(handle as ReturnType<typeof setTimeout>);
      },
    };
  });

  function at(index: number): FakeSocket {
    const socket = sockets[index];
    if (!socket) throw new Error(`no socket ${String(index)}`);
    return socket;
  }

  function start(): LiveSocket {
    const live = new LiveSocket(
      'sgcs_token',
      {
        message: (m) => messages.push(m),
        connection: (s) => states.push(s),
        sessionEnded: (r) => ended.push(r),
      },
      deps,
    );
    live.start();
    return live;
  }

  it('authenticates in the first message and subscribes after the welcome', () => {
    start();
    const socket = at(0);
    socket.open();
    expect(socket.sent).toEqual([{ type: 'auth', token: 'sgcs_token' }]);

    socket.receive(welcome());

    expect(socket.sent[1]).toEqual({
      type: 'subscribe',
      topics: ['fleet.telemetry', 'alerts', 'commands', 'control', 'missions', 'pois'],
      telemetry_hz: 10,
    });
    expect(states).toEqual(['connecting', 'online']);
    expect(messages.map((m) => m.type)).toEqual(['welcome']);
  });

  it('keeps the connection alive with pings', () => {
    start();
    at(0).open();
    at(0).receive(welcome());

    vi.advanceTimersByTime(PING_INTERVAL_MS * 2);

    expect(at(0).sent.filter((m) => m.type === 'ping')).toHaveLength(2);
  });

  it('reconnects and resyncs when a message was missed', () => {
    start();
    at(0).open();
    at(0).receive(welcome(1));
    at(0).receive(snapshot(2));

    at(0).receive(snapshot(4)); // seq 3 is missing

    expect(at(0).closedWith).toBe(1000);
    expect(sockets).toHaveLength(2); // a new connection, which resubscribes
    expect(states.at(-2)).toBe('offline');
    expect(messages).toHaveLength(2); // the message after the gap was not applied
  });

  it('reconnects with backoff after a lost connection, and not after stop', () => {
    const live = start();
    at(0).open();
    at(0).receive(welcome());

    at(0).drop(1006);
    expect(states.at(-1)).toBe('offline');
    expect(sockets).toHaveLength(1);
    vi.advanceTimersByTime(500);
    expect(sockets).toHaveLength(2);

    live.stop();
    at(1).drop(1006);
    vi.advanceTimersByTime(60_000);
    expect(sockets).toHaveLength(2);
  });

  it('resyncs at once when the server says it fell behind (4429)', () => {
    start();
    at(0).open();
    at(0).receive(welcome());

    at(0).drop(4429);

    expect(sockets).toHaveLength(2);
  });

  it('ends the session on 4401 or session_ended, without reconnecting', () => {
    start();
    at(0).open();
    at(0).receive(welcome());
    at(0).receive({ type: 'session_ended', seq: 2, ts: '', reason: 'logged out' });

    expect(ended).toEqual(['logged out']);
    at(0).drop(4401, 'session revoked');
    vi.advanceTimersByTime(60_000);
    expect(sockets).toHaveLength(1);
  });
});
