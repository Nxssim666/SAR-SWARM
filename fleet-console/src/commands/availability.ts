// Which command buttons the console offers, and why not. Only a guide for the operator: the
// fleet service checks every command again and decides (ADR 0002: the UI is never the safety
// boundary). Pure, and tested row by row. A goto for several aircraft is offered: the server
// gives each its own point and layer and always asks for confirmation (ADR 0029).
import type { AircraftLive, CommandKind, LeaseView, Permission } from '../api/types';
import type { Connection } from '../live/store';

export type ConsoleCommand = Extract<
  CommandKind,
  'hold' | 'resume' | 'return_to_launch' | 'land' | 'arm' | 'disarm' | 'takeoff' | 'goto'
>;

export const COMMANDS: { kind: ConsoleCommand; label: string; key?: string }[] = [
  { kind: 'hold', label: 'Hold', key: 'H' },
  { kind: 'resume', label: 'Resume' },
  { kind: 'return_to_launch', label: 'Return' },
  { kind: 'land', label: 'Land' },
  { kind: 'goto', label: 'Goto', key: 'G' },
  { kind: 'arm', label: 'Arm' },
  { kind: 'disarm', label: 'Disarm' },
  { kind: 'takeoff', label: 'Takeoff' },
];

/** Safe on a degraded link: they only make things safer (the server's rule, ADR 0011). */
const SAFE: ReadonlySet<ConsoleCommand> = new Set(['hold', 'return_to_launch', 'land']);

export interface Context {
  connection: Connection;
  permissions: readonly Permission[];
  userId: string;
  selected: AircraftLive[];
  leases: Readonly<Record<string, LeaseView>>;
}

export type Availability = { enabled: true } | { enabled: false; reason: string };

export function availability(kind: ConsoleCommand, ctx: Context): Availability {
  if (ctx.connection !== 'online') {
    return { enabled: false, reason: 'Offline: the fleet service is not connected.' };
  }
  if (ctx.selected.length === 0) return { enabled: false, reason: 'Select aircraft first.' };
  const permission: Permission = kind === 'hold' ? 'aircraft.hold' : 'aircraft.command';
  if (!ctx.permissions.includes(permission)) {
    return { enabled: false, reason: 'Your role cannot send this command.' };
  }
  if (kind !== 'hold' && !ctx.permissions.includes('control.override')) {
    const controlled = ctx.selected.some(
      (a) => ctx.leases[a.aircraft_id]?.holder.user_id === ctx.userId,
    );
    if (!controlled) return { enabled: false, reason: 'Take control of the aircraft first.' };
  }
  if (!SAFE.has(kind) && ctx.selected.every((a) => a.link !== 'live')) {
    return {
      enabled: false,
      reason: 'No selected aircraft has a live link: only hold, return and land can be tried.',
    };
  }
  return { enabled: true };
}
