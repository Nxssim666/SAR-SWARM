import { describe, expect, it } from 'vitest';

import type { Permission } from '../api/types';
import { aircraft, lease } from '../test/fixtures';
import { availability, type ConsoleCommand, type Context } from './availability';

const OPERATOR: Permission[] = ['fleet.view', 'aircraft.hold', 'aircraft.command', 'alerts.ack'];
const SUPERVISOR: Permission[] = [...OPERATOR, 'control.override'];
const OBSERVER: Permission[] = ['fleet.view'];

function ctx(overrides: Partial<Context> = {}): Context {
  return {
    connection: 'online',
    permissions: OPERATOR,
    userId: 'u-op',
    selected: [aircraft('a1')],
    leases: { a1: lease('a1', 'op') },
    ...overrides,
  };
}

function reason(kind: ConsoleCommand, context: Context): string | null {
  const result = availability(kind, context);
  return result.enabled ? null : result.reason;
}

describe('command availability (a guide only: the server decides)', () => {
  it.each<[string, ConsoleCommand, Partial<Context>, RegExp | null]>([
    ['offline', 'hold', { connection: 'offline' }, /Offline/],
    ['nothing selected', 'hold', { selected: [] }, /Select aircraft/],
    ['observer', 'hold', { permissions: OBSERVER }, /role cannot/],
    ['hold needs no control', 'hold', { leases: {} }, null],
    ['others need control', 'land', { leases: {} }, /Take control/],
    ['controlled by someone else', 'arm', { leases: { a1: lease('a1', 'other') } }, /Take control/],
    ['supervisors may override', 'arm', { permissions: SUPERVISOR, leases: {} }, null],
    ['controlled', 'arm', {}, null],
    [
      'lost link: arm refused',
      'arm',
      { selected: [aircraft('a1', { link: 'lost' })] },
      /live link/,
    ],
    [
      'lost link: return still offered',
      'return_to_launch',
      { selected: [aircraft('a1', { link: 'lost' })] },
      null,
    ],
    [
      'stale link: land still offered',
      'land',
      { selected: [aircraft('a1', { link: 'stale' })] },
      null,
    ],
    ['goto one at a time', 'goto', { selected: [aircraft('a1'), aircraft('a2')] }, /one aircraft/],
  ])('%s', (_, kind, overrides, expected) => {
    const got = reason(kind, ctx(overrides));
    if (expected === null) expect(got).toBeNull();
    else expect(got).toMatch(expected);
  });
});
