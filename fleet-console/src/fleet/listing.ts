// Filtering and sorting of the aircraft list (pure; tested).
import type { AircraftLive, GroupOut, LinkState } from '../api/types';

export type SortKey = 'callsign' | 'link' | 'battery' | 'mode';

const LINK_ORDER: Record<LinkState, number> = { lost: 0, stale: 1, offline: 2, live: 3 };

export interface ListFilter {
  text: string;
  link: LinkState | 'all';
  groupId: string; // a group id, or 'all'
}

export function filterAircraft(
  aircraft: AircraftLive[],
  filter: ListFilter,
  groups: GroupOut[],
): AircraftLive[] {
  const text = filter.text.trim().toUpperCase();
  const group = groups.find((g) => g.id === filter.groupId);
  const members = group ? new Set(group.aircraft_ids) : null;
  return aircraft.filter(
    (a) =>
      (!text || a.callsign.includes(text)) &&
      (filter.link === 'all' || a.link === filter.link) &&
      (!members || members.has(a.aircraft_id)),
  );
}

export function sortAircraft(
  aircraft: AircraftLive[],
  key: SortKey,
  ascending: boolean,
): AircraftLive[] {
  const value = (a: AircraftLive): string | number => {
    switch (key) {
      case 'callsign':
        return a.callsign;
      case 'link':
        return LINK_ORDER[a.link];
      case 'battery':
        return a.telemetry?.battery_pct ?? -1; // unknown sorts as the lowest: look at it first
      case 'mode':
        return a.telemetry?.flight_mode ?? 'unknown';
    }
  };
  const sorted = [...aircraft].sort((x, y) => {
    const a = value(x);
    const b = value(y);
    const order =
      typeof a === 'number' && typeof b === 'number' ? a - b : String(a).localeCompare(String(b));
    return order || x.callsign.localeCompare(y.callsign);
  });
  return ascending ? sorted : sorted.reverse();
}
