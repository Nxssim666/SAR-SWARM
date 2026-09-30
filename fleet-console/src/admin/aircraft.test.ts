import { describe, expect, it } from 'vitest';

import { DEFAULT_MAVLINK, registration } from './registration';

describe('aircraft registration', () => {
  it('sends a MAVLink link only with a system id, on the default connection if none', () => {
    expect(
      registration({
        callsign: ' HX-1 ',
        airframe: 'multirotor_hexa',
        connection: '',
        systemId: '12',
        droneId: '',
      }),
    ).toEqual({
      callsign: 'HX-1',
      airframe: 'multirotor_hexa',
      mavlink_system_id: 12,
      mavlink_connection: DEFAULT_MAVLINK,
    });
  });

  it('leaves unset links out rather than guessing them', () => {
    expect(
      registration({
        callsign: 'FW-1',
        airframe: 'fixed_wing',
        connection: 'udpin://0.0.0.0:14550',
        systemId: '',
        droneId: '3',
      }),
    ).toEqual({ callsign: 'FW-1', airframe: 'fixed_wing', swarm_drone_id: 3 });
  });
});
