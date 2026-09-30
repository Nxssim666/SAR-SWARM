import { describe, expect, it } from 'vitest';

import { poi } from '../test/fixtures';
import { orderPois } from './order';

describe('points of interest order', () => {
  it('lists new survivor sightings first, then open points, then closed ones, newest first', () => {
    const ordered = orderPois([
      poi('old-open', { created_at: '2026-09-30T00:00:01Z' }),
      poi('closed', { status: 'resolved', created_at: '2026-09-30T00:00:09Z' }),
      poi('sighting', { kind: 'survivor_sighting', reported_at: '2026-09-30T00:00:02Z' }),
      poi('new-open', { status: 'confirmed', created_at: '2026-09-30T00:00:05Z' }),
      poi('seen', {
        kind: 'survivor_sighting',
        status: 'confirmed',
        created_at: '2026-09-30T00:00:03Z',
      }),
    ]);

    expect(ordered.map((p) => p.id)).toEqual([
      'sighting',
      'new-open',
      'seen',
      'old-open',
      'closed',
    ]);
  });
});
