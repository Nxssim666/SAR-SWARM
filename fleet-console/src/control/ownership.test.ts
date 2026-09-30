import { describe, expect, it } from 'vitest';

import { initials, OWNER_COLORS, ownerColor, secondsLeft } from './ownership';

describe('ownership', () => {
  it('gives each user a stable colour from the palette', () => {
    expect(ownerColor('u-1')).toBe(ownerColor('u-1'));
    expect(OWNER_COLORS).toContain(ownerColor('u-1'));
    const spread = new Set(Array.from({ length: 40 }, (_, i) => ownerColor(`user-${String(i)}`)));
    expect(spread.size).toBeGreaterThan(5); // users rarely share a colour
  });

  it('writes initials', () => {
    expect(initials('Operator One')).toBe('OO');
    expect(initials('chief')).toBe('CH');
    expect(initials('  Ana  Maria Lopez ')).toBe('AM');
  });

  it('counts down a handover request', () => {
    const now = Date.parse('2026-09-30T00:00:00Z');
    expect(secondsLeft('2026-09-30T00:00:12.2Z', now)).toBe(13);
    expect(secondsLeft('2026-09-29T23:59:59Z', now)).toBe(0);
  });
});
