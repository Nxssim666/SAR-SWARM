import type { BackendStatus } from '../hooks/useBackendHealth';

/** Beyond this, timestamps shown to the operator (alerts, ages) would be misleading. */
export const CLOCK_SKEW_WARNING_MS = 2000;

interface Props {
  status: BackendStatus;
}

export function ConnectionBadge({ status }: Props) {
  switch (status.state) {
    case 'connecting':
      return (
        <span className="badge badge-pending" role="status">
          Connecting to fleet service…
        </span>
      );
    case 'offline':
      return (
        <span className="badge badge-danger" role="status" title={status.reason}>
          Fleet service offline
        </span>
      );
    case 'online': {
      const skewSeconds = Math.abs(status.clockSkewMs) / 1000;
      return Math.abs(status.clockSkewMs) > CLOCK_SKEW_WARNING_MS ? (
        <span className="badge badge-warning" role="status">
          Connected · clock off by {skewSeconds.toFixed(1)} s
        </span>
      ) : (
        <span className="badge badge-ok" role="status">
          Connected
        </span>
      );
    }
  }
}
