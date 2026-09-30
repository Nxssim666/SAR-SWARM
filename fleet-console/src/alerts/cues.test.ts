import { describe, expect, it } from 'vitest';

import { alert } from '../test/fixtures';
import { criticalActive, cueFor } from './cues';

describe('alert cues', () => {
  it('does not replay the backlog of the first snapshot', () => {
    expect(cueFor(null, { c: alert('c', 'critical') })).toBeNull();
  });

  it('cues new warnings and criticals, the most severe first, and never info', () => {
    const before = { w: alert('w', 'warning') };

    expect(cueFor(before, { ...before, i: alert('i', 'info') })).toBeNull();
    expect(cueFor(before, { ...before, w2: alert('w2', 'warning') })).toBe('warning');
    expect(
      cueFor(before, { ...before, w2: alert('w2', 'warning'), c: alert('c', 'critical') }),
    ).toBe('critical');
  });

  it('cues an escalation, and nothing for acknowledging or clearing', () => {
    const before = { w: alert('w', 'warning') };

    expect(cueFor(before, { w: alert('w', 'critical') })).toBe('critical');
    expect(cueFor(before, { w: { ...alert('w', 'warning'), state: 'acknowledged' } })).toBeNull();
    expect(cueFor(before, { w: { ...alert('w', 'warning'), state: 'cleared' } })).toBeNull();
  });

  it('cues an alert raised again after it cleared', () => {
    const before = { w: { ...alert('w', 'warning'), state: 'cleared' as const } };

    expect(cueFor(before, { w: alert('w', 'warning') })).toBe('warning');
  });

  it('keeps reminding while a critical alert is unacknowledged', () => {
    expect(criticalActive({ c: alert('c', 'critical') })).toBe(true);
    expect(criticalActive({ c: { ...alert('c', 'critical'), state: 'acknowledged' } })).toBe(false);
    expect(criticalActive({ w: alert('w', 'warning') })).toBe(false);
  });
});
