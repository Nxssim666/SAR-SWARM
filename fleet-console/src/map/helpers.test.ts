import { describe, expect, it } from 'vitest';

import { idsInside, pointInPolygon, type LonLat } from '../selection/geometry';
import { modeFor, useSelection } from '../selection/store';
import { aircraft, telemetry } from '../test/fixtures';
import { formatCoord } from './coords';
import { aircraftProps, allIconIds, iconId, LINK_SHAPE } from './symbology';

describe('coordinates', () => {
  it('formats decimal degrees, latitude first', () => {
    expect(formatCoord(47.3977, 8.5456, 'dd')).toBe('47.397700, 8.545600');
  });

  it('formats degrees and decimal minutes with hemispheres', () => {
    expect(formatCoord(47.3977, 8.5456, 'ddm')).toBe('47° 23.862′ N 8° 32.736′ E');
    expect(formatCoord(-33.5, -70.25, 'ddm')).toBe('33° 30.000′ S 70° 15.000′ W');
  });

  it('formats MGRS with its groups separated', () => {
    // PX4's default home in Zurich, zone 32T.
    expect(formatCoord(47.397742, 8.545594, 'mgrs')).toMatch(/^32T MT \d{5} \d{5}$/);
  });

  it('says so outside the MGRS latitude band', () => {
    expect(formatCoord(85, 0, 'mgrs')).toBe('outside MGRS (polar)');
  });
});

describe('symbology', () => {
  it('shows the link state by shape, not colour alone', () => {
    expect(LINK_SHAPE).toEqual({
      live: 'solid',
      stale: 'hollow',
      lost: 'crossed',
      offline: 'crossed',
    });
    expect(new Set(allIconIds()).size).toBe(12);
  });

  it('draws an aircraft by airframe and link, rotated by its heading', () => {
    const plane = aircraftProps(aircraft('a1', { airframe: 'fixed_wing', link: 'stale' }), true);

    expect(plane?.position).toEqual([8.5456, 47.3977]); // GeoJSON: longitude first
    expect(plane?.props.icon).toBe(iconId('fixed-wing', 'hollow', true));
    expect(plane?.props.heading).toBe(90);
    expect(plane?.props.selected).toBe(true);
  });

  it('draws no nose when the heading is unknown, and nothing without a position', () => {
    const noHeading = aircraftProps(
      aircraft('a1', { telemetry: telemetry({ heading_deg: null }) }),
      false,
    );
    expect(noHeading?.props.icon).toBe('ac-multirotor-solid-nohdg');

    expect(
      aircraftProps(aircraft('a2', { telemetry: telemetry({ position: null }) }), false),
    ).toBeNull();
    expect(aircraftProps(aircraft('a3', { telemetry: null }), false)).toBeNull();
  });
});

describe('selection', () => {
  const square: LonLat[] = [
    [8.0, 47.0],
    [8.1, 47.0],
    [8.1, 47.1],
    [8.0, 47.1],
  ];

  it('finds the positions inside a drawn polygon', () => {
    const positions = new Map<string, LonLat>([
      ['in', [8.05, 47.05]],
      ['out', [8.2, 47.05]],
    ]);

    expect(pointInPolygon([8.05, 47.05], square)).toBe(true);
    expect(idsInside(positions, square)).toEqual(['in']);
    expect(idsInside(positions, square.slice(0, 2))).toEqual([]);
  });

  it('replaces, adds or toggles like the usual click modifiers', () => {
    const { select } = useSelection.getState();
    select(['a', 'b']);
    select(['c'], modeFor({ shiftKey: true, ctrlKey: false, metaKey: false }));
    select(['a'], modeFor({ shiftKey: false, ctrlKey: true, metaKey: false }));

    expect([...useSelection.getState().selected].sort()).toEqual(['b', 'c']);

    useSelection.getState().retain(new Set(['b']));
    expect([...useSelection.getState().selected]).toEqual(['b']);
  });
});
