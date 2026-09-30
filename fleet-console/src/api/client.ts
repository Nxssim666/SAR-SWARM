// REST calls to the fleet service: bearer token, JSON bodies, RFC 9457 problems (ADR 0013).
import type { Problem } from './types';

const PROBLEM_TYPE = 'application/problem+json';

/** A problem document the server answered with (4xx/5xx). */
export class ProblemError extends Error {
  readonly status: number;
  readonly problem: Problem & Record<string, unknown>;

  constructor(status: number, problem: Problem & Record<string, unknown>) {
    super(problem.detail ?? problem.title);
    this.name = 'ProblemError';
    this.status = status;
    this.problem = problem;
  }

  /** The stable slug at the end of the problem type (urn:sar-gcs:problem:<slug>). */
  get slug(): string {
    return this.problem.type.split(':').at(-1) ?? this.problem.type;
  }
}

type Listener = () => void;
const unauthorizedListeners = new Set<Listener>();

/** Called whenever the server answers 401: the session is over. */
export function onUnauthorized(listener: Listener): () => void {
  unauthorizedListeners.add(listener);
  return () => unauthorizedListeners.delete(listener);
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  token?: string | null;
  signal?: AbortSignal;
}

/** Call the API; resolve with the parsed JSON (or undefined for 204), reject with ProblemError. */
export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (options.token) headers.Authorization = `Bearer ${options.token}`;
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';
  const init: RequestInit = { method: options.method ?? 'GET', headers, cache: 'no-store' };
  if (options.body !== undefined) init.body = JSON.stringify(options.body);
  if (options.signal) init.signal = options.signal;

  const response = await fetch(`/api/v1${path}`, init);
  if (response.status === 401) {
    for (const listener of unauthorizedListeners) listener();
  }
  if (!response.ok) {
    throw new ProblemError(response.status, await problemOf(response));
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function problemOf(response: Response): Promise<Problem & Record<string, unknown>> {
  const type = response.headers.get('Content-Type') ?? '';
  if (type.includes(PROBLEM_TYPE) || type.includes('application/json')) {
    try {
      return (await response.json()) as Problem & Record<string, unknown>;
    } catch {
      // fall through: an unreadable body is reported like any other failure
    }
  }
  return {
    type: 'about:blank',
    title: response.statusText || 'Request failed',
    status: response.status,
    detail: `HTTP ${String(response.status)}`,
    instance: null,
    errors: null,
  };
}
