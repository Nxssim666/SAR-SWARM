// The console's one WebSocket to the fleet service (ADR 0020, ADR 0027).
//
// The token goes in the first message, never the URL. After `welcome`, the client subscribes
// to every topic and receives one snapshot per topic, then events. `seq` increases by one per
// message: a gap, or close code 4429 (fell behind), means state may be missing, so the
// client reconnects and the new snapshots resync it. Close code 4401 or `session_ended`
// ends the session. Any other loss reconnects with backoff; meanwhile the console shows
// itself offline and offers no commands.
import { CLOSE, TOPICS, type ServerMessage } from './messages';

export const PING_INTERVAL_MS = 10_000;
export const TELEMETRY_HZ = 10;
const BACKOFF_MS = [500, 1_000, 2_000, 4_000, 8_000];

export interface SocketLike {
  onopen: ((event: Event) => void) | null;
  onmessage: ((event: MessageEvent<string>) => void) | null;
  onclose: ((event: CloseEvent) => void) | null;
  onerror: ((event: Event) => void) | null;
  send: (data: string) => void;
  close: (code?: number, reason?: string) => void;
}

export interface SocketHandlers {
  message: (message: ServerMessage) => void;
  connection: (state: 'connecting' | 'online' | 'offline', reason: string | null) => void;
  sessionEnded: (reason: string) => void;
}

export interface SocketDeps {
  url: string;
  create: (url: string) => SocketLike;
  setTimeout: (callback: () => void, ms: number) => unknown;
  clearTimeout: (handle: unknown) => void;
}

export function defaultDeps(): SocketDeps {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return {
    url: `${scheme}://${window.location.host}/api/v1/ws`,
    create: (url) => new WebSocket(url),
    setTimeout: (callback, ms) => window.setTimeout(callback, ms),
    clearTimeout: (handle) => {
      window.clearTimeout(handle as number);
    },
  };
}

export class LiveSocket {
  private socket: SocketLike | null = null;
  private lastSeq = 0;
  private attempt = 0;
  private stopped = false;
  private pingTimer: unknown = null;
  private retryTimer: unknown = null;

  constructor(
    private readonly token: string,
    private readonly handlers: SocketHandlers,
    private readonly deps: SocketDeps = defaultDeps(),
  ) {}

  start(): void {
    this.stopped = false;
    this.connect();
  }

  stop(): void {
    this.stopped = true;
    this.clearTimers();
    const socket = this.socket;
    this.socket = null;
    socket?.close(1000, 'console closed');
  }

  private connect(): void {
    this.lastSeq = 0;
    this.handlers.connection('connecting', null);
    const socket = this.deps.create(this.deps.url);
    this.socket = socket;
    socket.onopen = () => {
      socket.send(JSON.stringify({ type: 'auth', token: this.token }));
    };
    socket.onmessage = (event) => {
      if (this.socket === socket) this.receive(event.data);
    };
    socket.onclose = (event) => {
      if (this.socket === socket) this.closed(event.code, event.reason);
    };
    socket.onerror = () => {
      // a close event always follows; it decides what to do
    };
  }

  private receive(raw: string): void {
    let message: ServerMessage;
    try {
      message = JSON.parse(raw) as ServerMessage;
    } catch {
      this.restart('unreadable message from the fleet service');
      return;
    }
    if (this.lastSeq !== 0 && message.seq !== this.lastSeq + 1) {
      this.restart(`messages missed (seq ${String(this.lastSeq)} → ${String(message.seq)})`);
      return;
    }
    this.lastSeq = message.seq;
    if (message.type === 'welcome') {
      this.attempt = 0;
      this.socket?.send(
        JSON.stringify({ type: 'subscribe', topics: TOPICS, telemetry_hz: TELEMETRY_HZ }),
      );
      this.handlers.connection('online', null);
      this.schedulePing();
    }
    if (message.type === 'session_ended') {
      this.stopped = true;
      this.handlers.sessionEnded(message.reason);
      return;
    }
    this.handlers.message(message);
  }

  private schedulePing(): void {
    this.pingTimer = this.deps.setTimeout(() => {
      this.socket?.send(JSON.stringify({ type: 'ping' }));
      this.schedulePing();
    }, PING_INTERVAL_MS);
  }

  /** Drop this connection and open a new one now: the snapshots resync the state. */
  private restart(reason: string): void {
    const socket = this.socket;
    this.socket = null;
    socket?.close(1000, 'resync');
    this.clearTimers();
    this.handlers.connection('offline', reason);
    if (!this.stopped) this.connect();
  }

  private closed(code: number, reason: string): void {
    this.socket = null;
    this.clearTimers();
    if (code === CLOSE.unauthenticated) {
      this.stopped = true;
      this.handlers.sessionEnded(reason || 'Your session has ended.');
      return;
    }
    if (this.stopped) return;
    if (code === CLOSE.tooSlow) {
      this.handlers.connection('offline', 'fell behind; resynchronizing');
      this.connect();
      return;
    }
    this.handlers.connection('offline', reason || 'connection to the fleet service lost');
    const delay = BACKOFF_MS[Math.min(this.attempt, BACKOFF_MS.length - 1)] ?? 8_000;
    this.attempt += 1;
    this.retryTimer = this.deps.setTimeout(() => {
      if (!this.stopped) this.connect();
    }, delay);
  }

  private clearTimers(): void {
    if (this.pingTimer !== null) this.deps.clearTimeout(this.pingTimer);
    if (this.retryTimer !== null) this.deps.clearTimeout(this.retryTimer);
    this.pingTimer = null;
    this.retryTimer = null;
  }
}
