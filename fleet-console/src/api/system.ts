// System endpoints of the fleet service. Types come from the generated OpenAPI schema.
import type { components } from './generated/schema';

export type Health = components['schemas']['Health'];

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
