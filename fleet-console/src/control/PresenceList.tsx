// Who is connected (M5): each user with their role, their ownership colour and how many
// aircraft they control. A disclosure in the top bar, refreshed every 10 seconds.
import { useQuery } from '@tanstack/react-query';

import { api } from '../api/client';
import type { Role, UserRef } from '../api/types';
import { useThrottledLive } from '../live/useThrottled';
import { useSession } from '../session/session';
import { ownerColor } from './ownership';

interface Presence {
  users: { user: UserRef; role: Role; last_seen_at: string }[];
}

export function PresenceList() {
  const token = useSession((s) => s.session?.token ?? null);
  const leases = useThrottledLive((s) => s.leases);
  const presence = useQuery({
    queryKey: ['presence'],
    enabled: !!token,
    refetchInterval: 10_000,
    queryFn: ({ signal }) => api<Presence>('/presence', { token, signal }),
  });
  const users = presence.data?.users ?? [];
  const controls = (userId: string) =>
    Object.values(leases).filter((l) => l.holder.user_id === userId).length;

  return (
    <details className="presence">
      <summary aria-label="Who is online">👥 {users.length} online</summary>
      <ul>
        {users.map((p) => (
          <li key={p.user.user_id}>
            <span
              className="owner-chip"
              style={{ background: ownerColor(p.user.user_id) }}
              aria-hidden="true"
            />{' '}
            <strong>{p.user.display_name}</strong> · {p.role}
            {controls(p.user.user_id) > 0 && ` · controls ${String(controls(p.user.user_id))}`}
          </li>
        ))}
      </ul>
    </details>
  );
}
