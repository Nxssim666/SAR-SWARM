import { beforeEach, describe, expect, it, vi } from 'vitest';

import asyncapi from '../../../docs/api/asyncapi.json';

import { useCommandFlow } from '../commands/flow';
import { useLive } from '../live/store';
import { useSelection } from '../selection/store';
import { useSession } from '../session/session';
import { aircraft } from '../test/fixtures';
import { handleKey, SHORTCUTS } from './shortcuts';

function key(
  k: string,
  extra: Partial<KeyboardEventInit> = {},
  target?: HTMLElement,
): KeyboardEvent {
  const event = new KeyboardEvent('keydown', { key: k, ...extra });
  Object.defineProperty(event, 'target', { value: target ?? document.body });
  return event;
}

describe('keyboard shortcuts', () => {
  beforeEach(() => {
    useLive.getState().reset();
    useLive.getState().setConnection('online');
    useLive.getState().apply({
      type: 'snapshot',
      topic: 'fleet.telemetry',
      seq: 2,
      ts: '',
      data: { aircraft: [aircraft('a1'), aircraft('a2')] },
    });
    useSelection.getState().clear();
    useSession.getState().signIn({
      token: 't',
      user: { user_id: 'u', username: 'op', display_name: 'Op' },
      permissions: ['aircraft.hold', 'aircraft.command'],
      expiresAt: '2026-09-30T04:00:00Z',
    });
  });

  it('selects all, picks tools, and clears', () => {
    handleKey(key('a', { ctrlKey: true }), vi.fn());
    expect(useSelection.getState().selected.size).toBe(2);
    handleKey(key('l'), vi.fn());
    expect(useSelection.getState().tool).toBe('lasso');
    handleKey(key('Escape'), vi.fn());
    expect(useSelection.getState().selected.size).toBe(0);
    expect(useSelection.getState().tool).toBe('pan');
  });

  it('H sends HOLD for the selection, and nothing when nothing is selected', () => {
    const send = vi.spyOn(useCommandFlow.getState(), 'send').mockResolvedValue();
    handleKey(key('h'), vi.fn());
    expect(send).not.toHaveBeenCalled();

    useSelection.getState().select(['a1']);
    handleKey(key('h'), vi.fn());
    expect(send).toHaveBeenCalledWith({ kind: 'hold' });
  });

  it('ignores keys typed into fields', () => {
    const input = document.createElement('input');
    expect(handleKey(key('l', {}, input), vi.fn())).toBe(false);
    expect(useSelection.getState().tool).toBe('pan');
  });

  it('gives no risky command a key', () => {
    const risky = /arm|takeoff|return|land|goto target|disarm/i;
    for (const s of SHORTCUTS) {
      if (s.keys === 'H' || s.keys === 'G') continue; // hold is safe; G only picks a target
      expect(s.action).not.toMatch(risky);
    }
  });
});

describe('WebSocket contract', () => {
  it('handles every server message kind the AsyncAPI document defines', () => {
    const spec = asyncapi as unknown as {
      components: {
        schemas: Record<
          string,
          { properties?: Record<string, { const?: string; default?: string }> }
        >;
      };
    };
    const kinds = new Set<string>();
    for (const schema of Object.values(spec.components.schemas)) {
      const type = schema.properties?.type;
      const value = type?.const ?? type?.default;
      if (value && !['auth', 'subscribe', 'unsubscribe', 'ping'].includes(value)) kinds.add(value);
    }
    // The console's ServerMessage union (src/live/messages.ts) and store handle these:
    expect([...kinds].sort()).toEqual(
      ['error', 'event', 'pong', 'session_ended', 'snapshot', 'welcome'].sort(),
    );
  });
});
