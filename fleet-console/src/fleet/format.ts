// Display of telemetry values. Unknown is shown as unknown, never as a plausible default
// (ADR 0002, S7): the caller renders UNKNOWN with the title "unknown".
import type { FlightMode, LinkState } from '../api/types';

export const UNKNOWN = '—';

export function number(value: number | null | undefined, unit: string, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return UNKNOWN;
  return `${value.toFixed(digits)} ${unit}`.trim();
}

export function yesNo(value: boolean | null | undefined, yes: string, no: string): string {
  if (value === null || value === undefined) return UNKNOWN;
  return value ? yes : no;
}

export const LINK_LABEL: Record<LinkState, string> = {
  live: 'Live',
  stale: 'Stale',
  lost: 'Lost',
  offline: 'Offline',
};

/** A symbol per link state, so the state never depends on colour alone. */
export const LINK_ICON: Record<LinkState, string> = {
  live: '●',
  stale: '◐',
  lost: '✕',
  offline: '○',
};

export const MODE_LABEL: Record<FlightMode, string> = {
  hold: 'Hold',
  takeoff: 'Takeoff',
  goto: 'Goto',
  mission: 'Mission',
  return: 'Return',
  land: 'Land',
  manual: 'Manual',
  offboard: 'Offboard',
  unknown: UNKNOWN,
};

/** Seconds since `iso` at `now`, for "last seen" displays. */
export function age(iso: string | null, now: number): string {
  if (!iso) return 'never';
  const seconds = Math.max(0, (now - Date.parse(iso)) / 1000);
  if (seconds < 60) return `${seconds.toFixed(0)} s ago`;
  if (seconds < 3600) return `${(seconds / 60).toFixed(0)} min ago`;
  return `${(seconds / 3600).toFixed(1)} h ago`;
}
