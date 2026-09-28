import { useEffect, useState } from 'react';

import { fetchHealth } from '../api/system';

export type BackendStatus =
  | { state: 'connecting' }
  | { state: 'online'; clockSkewMs: number }
  | { state: 'offline'; reason: string };

const REQUEST_TIMEOUT_MS = 3000;

/** Poll the fleet service's health endpoint; a request that takes too long counts as offline. */
export function useBackendHealth(intervalMs = 5000): BackendStatus {
  const [status, setStatus] = useState<BackendStatus>({ state: 'connecting' });

  useEffect(() => {
    let active = true;
    let nextPoll: ReturnType<typeof setTimeout> | undefined;
    let inFlight: AbortController | undefined;

    async function poll(): Promise<void> {
      inFlight = new AbortController();
      const timeout = setTimeout(() => {
        inFlight?.abort(new Error('timed out'));
      }, REQUEST_TIMEOUT_MS);
      try {
        const health = await fetchHealth(inFlight.signal);
        if (active) {
          setStatus({ state: 'online', clockSkewMs: Date.parse(health.server_time) - Date.now() });
        }
      } catch (error) {
        if (active) {
          setStatus({ state: 'offline', reason: error instanceof Error ? error.message : 'error' });
        }
      } finally {
        clearTimeout(timeout);
        if (active) {
          nextPoll = setTimeout(() => void poll(), intervalMs);
        }
      }
    }

    void poll();
    return () => {
      active = false;
      clearTimeout(nextPoll);
      inFlight?.abort();
    };
  }, [intervalMs]);

  return status;
}
