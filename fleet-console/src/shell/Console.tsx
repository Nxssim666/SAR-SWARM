// The console once signed in: banners, map, the side pane (fleet, missions, points of
// interest), alerts, commands.
import { useQuery } from '@tanstack/react-query';
import { useCallback, useEffect, useState } from 'react';

import { AdminButton } from '../admin/AdminDialog';
import { AlertsStrip } from '../alerts/AlertsStrip';
import { useAlertCues } from '../alerts/useAlertCues';
import { api } from '../api/client';
import type { GroupPage } from '../api/types';
import { CommandBar } from '../commands/CommandBar';
import { ConnectionBadge } from '../components/ConnectionBadge';
import { HandoverPrompts } from '../control/HandoverPrompts';
import { PresenceList } from '../control/PresenceList';
import { AircraftList } from '../fleet/AircraftList';
import type { ListFilter } from '../fleet/listing';
import { TelemetryPanel } from '../fleet/TelemetryPanel';
import { useBackendHealth } from '../hooks/useBackendHealth';
import { IncidentPicker } from '../incident/IncidentPicker';
import { LiveSocket } from '../live/socket';
import { useLive } from '../live/store';
import { CoordinateReadout } from '../map/CoordinateReadout';
import { FleetMap } from '../map/FleetMap';
import { SelectionTools } from '../selection/SelectionTools';
import { MissionsPanel } from '../planning/MissionsPanel';
import { PoisPanel } from '../pois/PoisPanel';
import { useSelection } from '../selection/store';
import { logout, type Session, useSession } from '../session/session';
import { Banners } from './Banners';
import { HelpOverlay } from './HelpOverlay';
import { VideoPanel } from '../video/VideoPanel';
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

type SideTab = 'fleet' | 'missions' | 'pois';
const SIDE_TABS: { id: SideTab; label: string }[] = [
  { id: 'fleet', label: 'Fleet' },
  { id: 'missions', label: 'Missions' },
  { id: 'pois', label: 'Points' },
];

export function Console({ session }: { session: Session }) {
  useLiveConnection(session);
  useAlertCues();
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
  const [tab, setTab] = useState<SideTab>('fleet');
  const [video, setVideo] = useState(false);
  const sightings = useLive(
    (s) =>
      Object.values(s.pois).filter((p) => p.kind === 'survivor_sighting' && p.status === 'new')
        .length,
  );

  return (
    <div className="shell">
      <header className="topbar">
        <h1 className="title">SAR Fleet Console</h1>
        <IncidentPicker />
        <PresenceList />
        <ConnectionBadge status={health} />
        <span className="user">
          {session.user.display_name}
          {role ? ` · ${role}` : ''}
        </span>
        <button
          type="button"
          aria-pressed={video}
          onClick={() => {
            setVideo((v) => !v);
          }}
        >
          Video
        </button>
        <AdminButton />
        <button type="button" onClick={toggleHelp} aria-label="Keyboard shortcuts">
          ?
        </button>
        <button type="button" onClick={() => void logout()}>
          Sign out
        </button>
      </header>
      <Banners />
      <HandoverPrompts />
      <main className="workspace">
        <div className="map-pane">
          <FleetMap />
          <div className="map-overlay-top">
            <SelectionTools groups={groups.data?.items ?? []} filteredIds={filteredIds} />
          </div>
          <div className="map-overlay-bottom">
            <CoordinateReadout />
          </div>
          {video && (
            <VideoPanel
              onClose={() => {
                setVideo(false);
              }}
            />
          )}
        </div>
        <aside className="side">
          <div className="tabs" role="tablist" aria-label="Side pane">
            {SIDE_TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={tab === t.id}
                onClick={() => {
                  setTab(t.id);
                }}
              >
                {t.label}
                {t.id === 'pois' && sightings > 0 && (
                  <span className="badge" title="New survivor sightings">
                    ◆ {sightings}
                  </span>
                )}
              </button>
            ))}
          </div>
          <div role="tabpanel" className="tab-panel">
            {tab === 'fleet' && (
              <>
                <AircraftList
                  groups={groups.data?.items ?? []}
                  filter={filter}
                  onFilter={setFilter}
                  onVisible={setFilteredIds}
                />
                <TelemetryPanel />
              </>
            )}
            {tab === 'missions' && <MissionsPanel />}
            {tab === 'pois' && <PoisPanel />}
          </div>
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
