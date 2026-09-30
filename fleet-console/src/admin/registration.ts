// The request body of an aircraft registration (M6): empty fields are left out, never
// guessed (ADR 0002, S7), except the usual MAVLink connection once a system id is given.
import type { Airframe } from '../api/types';

export const DEFAULT_MAVLINK = 'udpin://0.0.0.0:14550';

export function registration(form: {
  callsign: string;
  airframe: Airframe;
  connection: string;
  systemId: string;
  droneId: string;
}): Record<string, unknown> {
  const body: Record<string, unknown> = {
    callsign: form.callsign.trim(),
    airframe: form.airframe,
  };
  if (form.systemId.trim()) {
    body.mavlink_system_id = Number(form.systemId);
    body.mavlink_connection = form.connection.trim() || DEFAULT_MAVLINK;
  }
  if (form.droneId.trim()) body.swarm_drone_id = Number(form.droneId);
  return body;
}
