// System endpoints of the fleet service. From M1 these types are generated from openapi.json.

export interface Health {
  status: 'ok';
  /** ISO 8601 UTC time on the ground station, used to detect client clock skew. */
  server_time: string;
}

export async function fetchHealth(signal: AbortSignal): Promise<Health> {
  const response = await fetch('/api/v1/health', {
    signal,
    headers: { Accept: 'application/json' },
    cache: 'no-store',
  });
  if (!response.ok) {
    throw new Error(`health check failed: HTTP ${String(response.status)}`);
  }
  return (await response.json()) as Health;
}
