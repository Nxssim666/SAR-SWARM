import { act, render } from '@testing-library/react';
import { Profiler } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { AircraftLive } from '../api/types';
import { useLive } from '../live/store';
import { LIST_HZ, useThrottledLive } from '../live/useThrottled';
import { aircraft, telemetry } from '../test/fixtures';
import { filterAircraft, sortAircraft } from './listing';

describe('aircraft list', () => {
  const fleet: AircraftLive[] = [
    aircraft('hx-2', {
      callsign: 'HX-02',
      link: 'live',
      telemetry: telemetry({ battery_pct: 60 }),
    }),
    aircraft('fw-1', {
      callsign: 'FW-01',
      link: 'lost',
      telemetry: telemetry({ battery_pct: 80 }),
    }),
    aircraft('hx-1', { callsign: 'HX-01', link: 'stale', telemetry: null }),
  ];

  it('filters by callsign, link and group', () => {
    const groups = [
      {
        id: 'g',
        name: 'North',
        description: null,
        aircraft_ids: ['hx-1', 'hx-2'],
        created_at: '',
        updated_at: '',
      },
    ];
    const ids = (f: Parameters<typeof filterAircraft>[1]) =>
      filterAircraft(fleet, f, groups).map((a) => a.aircraft_id);

    expect(ids({ text: 'hx', link: 'all', groupId: 'all' })).toEqual(['hx-2', 'hx-1']);
    expect(ids({ text: '', link: 'lost', groupId: 'all' })).toEqual(['fw-1']);
    expect(ids({ text: '', link: 'all', groupId: 'g' })).toEqual(['hx-2', 'hx-1']);
  });

  it('sorts lost links first, and unknown battery as the lowest (look at it first)', () => {
    expect(sortAircraft(fleet, 'link', true).map((a) => a.callsign)).toEqual([
      'FW-01',
      'HX-01',
      'HX-02',
    ]);
    expect(sortAircraft(fleet, 'battery', true).map((a) => a.callsign)).toEqual([
      'HX-01',
      'HX-02',
      'FW-01',
    ]);
    expect(sortAircraft(fleet, 'callsign', false).map((a) => a.callsign)).toEqual([
      'HX-02',
      'HX-01',
      'FW-01',
    ]);
  });
});

describe('render rate under load (ADR 0005)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    useLive.getState().reset();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  function Probe() {
    const count = useThrottledLive((s) => Object.keys(s.aircraft).length);
    return <span>{count}</span>;
  }

  it('re-renders a list at most 4 times a second with 50 aircraft at 10 Hz', () => {
    let renders = 0;
    render(
      <Profiler id="list" onRender={() => (renders += 1)}>
        <Probe />
      </Profiler>,
    );
    const initial = renders;
    const fleet = Array.from({ length: 50 }, (_, i) => aircraft(`a${String(i)}`));

    act(() => {
      for (let tick = 0; tick < 20; tick += 1) {
        // 2 s of telemetry: 10 Hz, one event per aircraft each time
        for (const a of fleet) {
          useLive.getState().apply({
            type: 'event',
            topic: 'fleet.telemetry',
            seq: 1,
            ts: '',
            data: { aircraft: [a] },
          });
        }
        vi.advanceTimersByTime(100);
      }
    });

    const rendersPerSecond = (renders - initial) / 2;
    expect(rendersPerSecond).toBeLessThanOrEqual(LIST_HZ + 1); // +1: the batch at the window's edge
    expect(renders - initial).toBeGreaterThan(0);
  });
});
