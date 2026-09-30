// Banners an operator must never miss: offline (no commands possible), simulation mode, the
// session about to end, and no basemap.
import { useEffect, useState } from 'react';

import { useLive } from '../live/store';
import { useMapState } from '../map/mapState';
import { useSession } from '../session/session';

export const EXPIRY_WARNING_MS = 5 * 60_000;

export function Banners() {
  const connection = useLive((s) => s.connection);
  const reason = useLive((s) => s.connectionReason);
  const simulation = useLive((s) => s.welcome?.simulation ?? false);
  const expiresAt = useSession((s) => s.session?.expiresAt);
  const basemap = useMapState((s) => s.basemap);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = setInterval(() => {
      setNow(Date.now());
    }, 15_000);
    return () => {
      clearInterval(timer);
    };
  }, []);

  const remaining = expiresAt ? Date.parse(expiresAt) - now : Infinity;

  return (
    <div className="banners">
      {connection !== 'online' && (
        <div className="banner banner-offline" role="alert">
          <strong>⚠ OFFLINE</strong> —{' '}
          {connection === 'connecting'
            ? 'connecting to the fleet service'
            : (reason ?? 'no connection')}
          . Commands are disabled; positions shown may be old.
        </div>
      )}
      {simulation && (
        <div className="banner banner-simulation" role="status">
          <strong>SIMULATION</strong> — every aircraft is simulated. Not for real operations.
        </div>
      )}
      {remaining < EXPIRY_WARNING_MS && (
        <div className="banner banner-expiry" role="status">
          Your session ends in {Math.max(0, Math.round(remaining / 60_000))} min: save your work and
          sign in again.
        </div>
      )}
      {basemap === 'none' && (
        <div className="banner banner-basemap" role="status">
          No basemap on this station: aircraft are shown on a plain background.
        </div>
      )}
    </div>
  );
}
