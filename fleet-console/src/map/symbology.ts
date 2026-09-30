// How an aircraft is drawn (ADR 0027): the airframe by icon, rotated by heading; the link
// state by colour AND shape, so it reads without colour vision:
//   live: filled; stale: hollow outline; lost/offline: hollow with a cross.
// An unknown heading draws no nose (never a guessed direction).
import type { AircraftLive, Airframe, LinkState } from '../api/types';
import { ownerColor } from '../control/ownership';

export type Shape = 'solid' | 'hollow' | 'crossed';
export type Kind = 'fixed-wing' | 'multirotor';

export const LINK_SHAPE: Record<LinkState, Shape> = {
  live: 'solid',
  stale: 'hollow',
  lost: 'crossed',
  offline: 'crossed',
};

export const LINK_COLOR: Record<LinkState, string> = {
  live: '#3fb950',
  stale: '#d29922',
  lost: '#f85149',
  offline: '#8b98a5',
};

export function kindOf(airframe: Airframe): Kind {
  return airframe === 'fixed_wing' ? 'fixed-wing' : 'multirotor';
}

export function iconId(kind: Kind, shape: Shape, hasHeading: boolean): string {
  return `ac-${kind}-${shape}${hasHeading ? '' : '-nohdg'}`;
}

/** Every icon the map must register. */
export function allIconIds(): string[] {
  const ids: string[] = [];
  for (const kind of ['fixed-wing', 'multirotor'] as const) {
    for (const shape of ['solid', 'hollow', 'crossed'] as const) {
      ids.push(iconId(kind, shape, true), iconId(kind, shape, false));
    }
  }
  return ids;
}

export interface AircraftFeatureProps {
  id: string;
  callsign: string;
  icon: string;
  color: string;
  heading: number;
  selected: boolean;
  link: LinkState;
  /** The controller's colour (M5), or '' when nobody controls it. */
  owner: string;
}

/** Map properties of an aircraft; null when its position is unknown (nothing to draw). */
export function aircraftProps(
  aircraft: AircraftLive,
  selected: boolean,
): { position: [number, number]; props: AircraftFeatureProps } | null {
  const position = aircraft.telemetry?.position;
  if (!position) return null;
  const heading = aircraft.telemetry?.heading_deg ?? null;
  return {
    position: [position.longitude, position.latitude], // GeoJSON order
    props: {
      id: aircraft.aircraft_id,
      callsign: aircraft.callsign,
      icon: iconId(kindOf(aircraft.airframe), LINK_SHAPE[aircraft.link], heading !== null),
      color: LINK_COLOR[aircraft.link],
      heading: heading ?? 0,
      selected,
      link: aircraft.link,
      owner: aircraft.controller ? ownerColor(aircraft.controller.holder.user_id) : '',
    },
  };
}
