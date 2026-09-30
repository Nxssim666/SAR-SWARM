import { describe, expect, it } from 'vitest';

import { buildPlanRequest, checkWaypoints, DEFAULT_FORM, type PlanForm } from './planRequest';

const DATUM = { latitude: 47.4, longitude: 8.55 };

function build(form: Partial<PlanForm>, selectedIds = ['a1', 'a2'], datum = DATUM) {
  return buildPlanRequest({ ...DEFAULT_FORM, ...form }, { selectedIds, datum });
}

describe('plan request', () => {
  it('builds a lawnmower for the selected aircraft with an explicit spacing', () => {
    expect(build({})).toEqual({
      ok: true,
      request: {
        pattern: 'parallel_track',
        second_pass: false,
        spacing_m: 60,
        aircraft_ids: ['a1', 'a2'],
      },
    });
  });

  it('turns a camera into a footprint (overlap as a fraction), never both', () => {
    const built = build({ spacingMode: 'camera', hfovDeg: '84', overlapPct: '30' });

    expect(built).toEqual({
      ok: true,
      request: {
        pattern: 'parallel_track',
        second_pass: false,
        footprint: { hfov_deg: 84, overlap: 0.3, height_agl_m: null },
        aircraft_ids: ['a1', 'a2'],
      },
    });
  });

  it('plans for a group instead of the selection', () => {
    const built = build({ aircraftSource: 'group', groupId: 'g1' }, []);

    expect(built.ok && built.request.group_id).toBe('g1');
    expect(built.ok && built.request.aircraft_ids).toBeUndefined();
  });

  it('needs a datum, a radius and one aircraft for a sector search', () => {
    expect(build({ pattern: 'sector' }, ['a1'], DATUM)).toEqual({
      ok: true,
      request: {
        pattern: 'sector',
        second_pass: false,
        spacing_m: 60,
        datum: DATUM,
        radius_m: 500,
        aircraft_ids: ['a1'],
      },
    });
    const bad = buildPlanRequest(
      { ...DEFAULT_FORM, pattern: 'expanding_square', radiusM: '5' },
      { selectedIds: ['a1', 'a2'], datum: null },
    );
    expect(bad.ok ? [] : bad.errors).toEqual([
      'Pick the datum on the map.',
      'The search radius must be 10 m to 50 km.',
      'An expanding square or sector search is flown by one aircraft.',
    ]);
  });

  it('sends a route without spacing, and a contour with its height above ground', () => {
    expect(build({ pattern: 'route', spacingM: '' })).toEqual({
      ok: true,
      request: { pattern: 'route', second_pass: false, aircraft_ids: ['a1', 'a2'] },
    });
    const contour = build({ pattern: 'contour', heightAglM: '80' });
    expect(contour.ok && contour.request.height_agl_m).toBe(80);
  });

  it('refuses what the server would refuse, with the reasons', () => {
    const built = build({ spacingM: '2', bearingDeg: '360' }, []);

    expect(built.ok ? [] : built.errors).toEqual([
      'Lane spacing must be 5 to 2000 m.',
      'The bearing must be 0 to 359.9 degrees true.',
      'Select the aircraft to plan for.',
    ]);
  });
});

describe('waypoint checks', () => {
  const wp = (altitude: number, extra: object = {}) => ({
    latitude: 47.4,
    longitude: 8.55,
    altitude_relative_m: altitude,
    ...extra,
  });

  it('needs a waypoint, positive altitudes, sane speeds and loiters', () => {
    expect(checkWaypoints([]).map((i) => i.level)).toEqual(['error']);
    expect(
      checkWaypoints([wp(0), wp(40, { speed_mps: 0 }), wp(40, { loiter_s: -1 })]).map(
        (i) => `${String(i.index)}:${i.level}`,
      ),
    ).toEqual(['0:error', '1:error', '2:error']);
    expect(checkWaypoints([wp(40, { speed_mps: 12, loiter_s: 30 })])).toEqual([]);
  });

  it('warns above the usual ceiling without blocking', () => {
    expect(checkWaypoints([wp(150)])).toEqual([
      {
        index: 0,
        level: 'warning',
        message: 'Waypoint 1: 150 m above home is over the usual 120 m ceiling.',
      },
    ]);
  });
});
