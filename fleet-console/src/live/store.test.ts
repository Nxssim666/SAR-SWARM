import { beforeEach, describe, expect, it } from 'vitest';

import { aircraft, alert, command } from '../test/fixtures';
import { openAlerts, useLive } from './store';

const T = '2026-09-30T00:00:00Z';

describe('live store', () => {
  beforeEach(() => {
    useLive.getState().reset();
  });

  it('replaces the fleet on a snapshot and merges events', () => {
    const { apply } = useLive.getState();
    apply({
      type: 'snapshot',
      topic: 'fleet.telemetry',
      seq: 2,
      ts: T,
      data: { aircraft: [aircraft('a1'), aircraft('a2')] },
    });
    apply({
      type: 'event',
      topic: 'fleet.telemetry',
      seq: 3,
      ts: T,
      data: { aircraft: [aircraft('a2', { link: 'stale' })] },
    });

    const state = useLive.getState();
    expect(Object.keys(state.aircraft)).toEqual(['a1', 'a2']);
    expect(state.aircraft.a2?.link).toBe('stale');
    expect(state.telemetryVersion).toBe(2);
  });

  it('a new snapshot drops aircraft that are gone', () => {
    const { apply } = useLive.getState();
    apply({
      type: 'snapshot',
      topic: 'fleet.telemetry',
      seq: 2,
      ts: T,
      data: { aircraft: [aircraft('a1')] },
    });
    apply({ type: 'snapshot', topic: 'fleet.telemetry', seq: 2, ts: T, data: { aircraft: [] } });

    expect(useLive.getState().aircraft).toEqual({});
  });

  it('tracks leases from control events', () => {
    const { apply } = useLive.getState();
    const lease = {
      aircraft_id: 'a1',
      holder: { user_id: 'u1', username: 'op', display_name: 'Op' },
      state: 'held' as const,
      acquired_at: T,
      pending_request: null,
    };
    apply({
      type: 'event',
      topic: 'control',
      seq: 2,
      ts: T,
      data: { aircraft_id: 'a1', change: 'taken', lease },
    });
    expect(useLive.getState().leases.a1?.holder.username).toBe('op');

    apply({
      type: 'event',
      topic: 'control',
      seq: 3,
      ts: T,
      data: { aircraft_id: 'a1', change: 'released', lease: null },
    });
    expect(useLive.getState().leases.a1).toBeUndefined();
  });

  it('keeps the newest commands and updates them in place', () => {
    const { apply } = useLive.getState();
    apply({ type: 'event', topic: 'commands', seq: 2, ts: T, data: command('c1', 'in_progress') });
    apply({ type: 'event', topic: 'commands', seq: 3, ts: T, data: command('c1', 'completed') });

    expect(useLive.getState().commands.c1?.state).toBe('completed');
  });

  it('orders open alerts by severity, then newest first, and hides cleared ones', () => {
    const alerts = {
      w: alert('w', 'warning', '2026-09-30T00:00:02Z'),
      c: alert('c', 'critical', '2026-09-30T00:00:01Z'),
      i: alert('i', 'info', '2026-09-30T00:00:03Z'),
      gone: { ...alert('gone', 'critical', T), state: 'cleared' as const },
    };

    expect(openAlerts(alerts).map((a) => a.id)).toEqual(['c', 'w', 'i']);
  });
});
