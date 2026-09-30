// The console once signed in: banners, map, list, selection, details, alerts, commands.
import { useQuery } from '@tanstack/react-query';
import { useCallback, useEffect, useState } from 'react';

import { AlertsStrip } from '../alerts/AlertsStrip';
import { api } from '../api/client';
import type { GroupPage } from '../api/types';
import { CommandBar } from '../commands/CommandBar';
import { ConnectionBadge } from '../components/ConnectionBadge';
import { AircraftList } from '../fleet/AircraftList';
import type { ListFilter } from '../fleet/listing';
import { TelemetryPanel } from '../fleet/TelemetryPanel';
import { useBackendHealth } from '../hooks/useBackendHealth';
import { LiveSocket } from '../live/socket';
import { useLive } from '../live/store';
import { CoordinateReadout } from '../map/CoordinateReadout';
import { FleetMap } from '../map/FleetMap';
import { SelectionTools } from '../selection/SelectionTools';
import { useSelection } from '../selection/store';
import { logout, type Session, useSession } from '../session/session';
import { Banners } from './Banners';
import { HelpOverlay } from './HelpOverlay';
import { useShortcuts } from './shortcuts';

/** One WebSocket for the session; its state goes to the live store. */
function useLiveConnection(session: Session): void {
  useEffect(() => {
    const live = useLive.getState();
    live.reset();
    const socket = new LiveSocket(session.token, {
      message: (message) => {
        useLive.getState().apply(message);
        if (message.type === 'welcome') useSession.getState().setExpiry(message.session_expires_at);
      },
      connection: (state, reason) => {
        useLive.getState().setConnection(state, reason);
      },
      sessionEnded: (reason) => {
        useSession.getState().signOut(`Your session has ended (${reason}). Please sign in again.`);
      },
    });
    socket.start();
    // Forget selected aircraft that were unregistered.
    const unsubscribe = useLive.subscribe((state, prev) => {
      if (state.aircraft !== prev.aircraft) {
        useSelection.getState().retain(new Set(Object.keys(state.aircraft)));
      }
    });
    return () => {
      unsubscribe();
      socket.stop();
    };
  }, [session.token]);
}

export function Console({ session }: { session: Session }) {
  useLiveConnection(session);
  const health = useBackendHealth();
  const [help, setHelp] = useState(false);
  const toggleHelp = useCallback(() => {
    setHelp((h) => !h);
  }, []);
  useShortcuts(toggleHelp);
  const [filter, setFilter] = useState<ListFilter>({ text: '', link: 'all', groupId: 'all' });
  const [filteredIds, setFilteredIds] = useState<string[]>([]);
  const groups = useQuery({
    queryKey: ['groups'],
    queryFn: ({ signal }) => api<GroupPage>('/groups?limit=200', { token: session.token, signal }),
  });
  const role = useLive((s) => s.welcome?.role);

  return (
    <div className="shell">
      <header className="topbar">
        <h1 className="title">SAR Fleet Console</h1>
        <ConnectionBadge status={health} />
        <span className="user">
          {session.user.display_name}
          {role ? ` · ${role}` : ''}
        </span>
        <button type="button" onClick={toggleHelp} aria-label="Keyboard shortcuts">
          ?
        </button>
        <button type="button" onClick={() => void logout()}>
          Sign out
        </button>
      </header>
      <Banners />
      <main className="workspace">
        <div className="map-pane">
          <FleetMap />
          <div className="map-overlay-top">
            <SelectionTools groups={groups.data?.items ?? []} filteredIds={filteredIds} />
          </div>
          <div className="map-overlay-bottom">
            <CoordinateReadout />
          </div>
        </div>
        <aside className="side">
          <AircraftList
            groups={groups.data?.items ?? []}
            filter={filter}
            onFilter={setFilter}
            onVisible={setFilteredIds}
          />
          <TelemetryPanel />
          <AlertsStrip />
        </aside>
      </main>
      <CommandBar />
      <HelpOverlay
        open={help}
        onClose={() => {
          setHelp(false);
        }}
      />
    </div>
  );
}
