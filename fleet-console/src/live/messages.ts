// WebSocket messages of /api/v1/ws (contract: docs/api/asyncapi.json). Payload types are the
// generated REST types; a test checks these message kinds against the AsyncAPI document.
import type {
  AircraftLive,
  AlertView,
  CommandView,
  LeaseView,
  Permission,
  Role,
  UserRef,
} from '../api/types';

export const TOPICS = ['fleet.telemetry', 'alerts', 'commands', 'control'] as const;
export type Topic = (typeof TOPICS)[number];

interface Base {
  seq: number;
  ts: string;
}

export interface WelcomeMessage extends Base {
  type: 'welcome';
  user: UserRef;
  role: Role;
  permissions: Permission[];
  session_expires_at: string;
  simulation: boolean;
}

export interface ControlChange {
  aircraft_id: string;
  change: string;
  lease: LeaseView | null;
}

export type SnapshotMessage = Base & { type: 'snapshot' } & (
    | { topic: 'fleet.telemetry'; data: { aircraft: AircraftLive[] } }
    | { topic: 'alerts'; data: { alerts: AlertView[] } }
    | { topic: 'commands'; data: { commands: CommandView[] } }
    | { topic: 'control'; data: { leases: LeaseView[] } }
  );

export type EventMessage = Base & { type: 'event' } & (
    | { topic: 'fleet.telemetry'; data: { aircraft: AircraftLive[] } }
    | { topic: 'alerts'; data: AlertView }
    | { topic: 'commands'; data: CommandView }
    | { topic: 'control'; data: ControlChange }
  );

export interface PongMessage extends Base {
  type: 'pong';
}

export interface ErrorMessage extends Base {
  type: 'error';
  code: string;
  message: string;
}

export interface SessionEndedMessage extends Base {
  type: 'session_ended';
  reason: string;
}

export type ServerMessage =
  | WelcomeMessage
  | SnapshotMessage
  | EventMessage
  | PongMessage
  | ErrorMessage
  | SessionEndedMessage;

/** Close codes (docs/api/README.md). */
export const CLOSE = {
  badMessage: 4400,
  unauthenticated: 4401,
  forbidden: 4403,
  timeout: 4408,
  tooSlow: 4429,
} as const;
