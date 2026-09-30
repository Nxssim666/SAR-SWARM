// Builders of API objects for tests (typed by the generated schema, so they stay valid).
import type {
  AircraftLive,
  AlertView,
  CommandView,
  LeaseView,
  MissionProgressView,
  PoiView,
  TelemetryView,
} from '../api/types';

export const T0 = '2026-09-30T00:00:00Z';

export function telemetry(overrides: Partial<TelemetryView> = {}): TelemetryView {
  return {
    ts: T0,
    source: 'mock',
    position: { latitude: 47.3977, longitude: 8.5456 },
    altitude_amsl_m: 530,
    altitude_relative_m: 30,
    heading_deg: 90,
    groundspeed_mps: 5,
    climb_rate_mps: 0,
    battery_pct: 80,
    battery_v: 24.1,
    gps_fix: '3d',
    satellites: 14,
    flight_mode: 'hold',
    armed: true,
    in_air: true,
    home: { latitude: 47.3977, longitude: 8.5456 },
    swarm: null,
    ...overrides,
  };
}

export function aircraft(id: string, overrides: Partial<AircraftLive> = {}): AircraftLive {
  return {
    aircraft_id: id,
    callsign: id.toUpperCase(),
    airframe: 'multirotor_hexa',
    link: 'live',
    links: {},
    last_seen_at: T0,
    telemetry: telemetry(),
    controller: null,
    ...overrides,
  };
}

export function lease(aircraftId: string, username = 'op'): LeaseView {
  return {
    aircraft_id: aircraftId,
    holder: { user_id: `u-${username}`, username, display_name: username },
    state: 'held',
    acquired_at: T0,
    pending_request: null,
  };
}

export function alert(id: string, severity: AlertView['severity'], raisedAt = T0): AlertView {
  return {
    id,
    kind: 'link_stale',
    severity,
    state: 'active',
    aircraft_id: 'a1',
    message: `alert ${id}`,
    raised_at: raisedAt,
    acknowledged_by: null,
    acknowledged_at: null,
    cleared_at: null,
  };
}

export function command(id: string, state: CommandView['state']): CommandView {
  return {
    id,
    kind: 'hold',
    params: {},
    issued_by: 'u1',
    state,
    override: false,
    confirmation_required: false,
    created_at: T0,
    confirmed_at: null,
    completed_at: null,
    targets: [],
  };
}

export function missionProgress(
  id: string,
  overrides: Partial<MissionProgressView> = {},
): MissionProgressView {
  return {
    mission_id: id,
    incident_id: 'i1',
    name: `Mission ${id}`,
    kind: 'area_search',
    status: 'active',
    coverage: 0.25,
    tasks: [
      {
        task_id: `${id}-t1`,
        aircraft_id: 'a1',
        callsign: 'A1',
        status: 'active',
        item: 3,
        items: 12,
      },
    ],
    updated_at: T0,
    ...overrides,
  };
}

export function poi(id: string, overrides: Partial<PoiView> = {}): PoiView {
  return {
    id,
    incident_id: 'i1',
    kind: 'poi',
    status: 'new',
    latitude: 47.399,
    longitude: 8.546,
    uncertainty_m: null,
    aircraft_id: null,
    reported_at: null,
    notes: null,
    created_by: 'u1',
    created_at: T0,
    updated_at: T0,
    ...overrides,
  };
}
