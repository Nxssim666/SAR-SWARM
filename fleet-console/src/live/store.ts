// Live state from the WebSocket (ADR 0005, ADR 0027). Written only by the socket client;
// the map reads it outside React, and React reads it through throttled selectors.
import { create } from 'zustand';

import type {
  AircraftLive,
  AlertView,
  CommandView,
  LeaseView,
  MissionProgressView,
  PoiView,
} from '../api/types';
import type { ServerMessage, WelcomeMessage } from './messages';

export type Connection = 'connecting' | 'online' | 'offline';

const MAX_COMMANDS = 50;

export interface LiveState {
  connection: Connection;
  /** Why the socket is not online (shown in the offline banner). */
  connectionReason: string | null;
  welcome: WelcomeMessage | null;
  aircraft: Record<string, AircraftLive>;
  alerts: Record<string, AlertView>;
  commands: Record<string, CommandView>;
  leases: Record<string, LeaseView>;
  /** Progress of GCS-planned and swarm missions, by mission id (ADR 0028). */
  missions: Record<string, MissionProgressView>;
  /** Points of interest and survivor sightings, by id (ADR 0031). */
  pois: Record<string, PoiView>;
  /** Bumped on every telemetry change (cheap change detection for the map). */
  telemetryVersion: number;
  setConnection: (connection: Connection, reason?: string | null) => void;
  apply: (message: ServerMessage) => void;
  reset: () => void;
}

const empty = {
  connection: 'connecting' as Connection,
  connectionReason: null,
  welcome: null,
  aircraft: {},
  alerts: {},
  commands: {},
  leases: {},
  missions: {},
  pois: {},
  telemetryVersion: 0,
};

function byId<T>(items: T[], id: (item: T) => string): Record<string, T> {
  return Object.fromEntries(items.map((item) => [id(item), item]));
}

function newestCommands(commands: Record<string, CommandView>): Record<string, CommandView> {
  const sorted = Object.values(commands).sort((a, b) => b.created_at.localeCompare(a.created_at));
  return byId(sorted.slice(0, MAX_COMMANDS), (c) => c.id);
}

export const useLive = create<LiveState>()((set) => ({
  ...empty,
  setConnection: (connection, reason = null) => {
    set({ connection, connectionReason: reason });
  },
  reset: () => {
    set({ ...empty });
  },
  apply: (message) => {
    switch (message.type) {
      case 'welcome':
        set({ welcome: message });
        return;
      case 'snapshot':
        switch (message.topic) {
          case 'fleet.telemetry':
            set((s) => ({
              aircraft: byId(message.data.aircraft, (a) => a.aircraft_id),
              telemetryVersion: s.telemetryVersion + 1,
            }));
            return;
          case 'alerts':
            set({ alerts: byId(message.data.alerts, (a) => a.id) });
            return;
          case 'commands':
            set({ commands: newestCommands(byId(message.data.commands, (c) => c.id)) });
            return;
          case 'control':
            set({ leases: byId(message.data.leases, (l) => l.aircraft_id) });
            return;
          case 'missions':
            set({ missions: byId(message.data.missions, (m) => m.mission_id) });
            return;
          case 'pois':
            set({ pois: byId(message.data.pois, (p) => p.id) });
            return;
        }
        return;
      case 'event':
        switch (message.topic) {
          case 'fleet.telemetry':
            set((s) => ({
              aircraft: {
                ...s.aircraft,
                ...byId(message.data.aircraft, (a) => a.aircraft_id),
              },
              telemetryVersion: s.telemetryVersion + 1,
            }));
            return;
          case 'alerts':
            set((s) => ({ alerts: { ...s.alerts, [message.data.id]: message.data } }));
            return;
          case 'commands':
            set((s) => ({
              commands: newestCommands({ ...s.commands, [message.data.id]: message.data }),
            }));
            return;
          case 'control': {
            const { aircraft_id: id, lease } = message.data;
            set((s) => {
              const others = Object.entries(s.leases).filter(([key]) => key !== id);
              return { leases: Object.fromEntries(lease ? [...others, [id, lease]] : others) };
            });
            return;
          }
          case 'missions':
            set((s) => ({
              missions: { ...s.missions, [message.data.mission_id]: message.data },
            }));
            return;
          case 'pois':
            set((s) => ({ pois: { ...s.pois, [message.data.id]: message.data } }));
            return;
        }
        return;
      case 'pong':
      case 'error':
      case 'session_ended':
        return;
    }
  },
}));

/** Alerts that still need attention, most severe and newest first. */
export function openAlerts(alerts: Record<string, AlertView>): AlertView[] {
  const rank = { critical: 0, warning: 1, info: 2 } as const;
  return Object.values(alerts)
    .filter((a) => a.state !== 'cleared')
    .sort((a, b) => rank[a.severity] - rank[b.severity] || b.raised_at.localeCompare(a.raised_at));
}
