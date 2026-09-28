import { ConnectionBadge } from './components/ConnectionBadge';
import { useBackendHealth } from './hooks/useBackendHealth';

export function App() {
  const status = useBackendHealth();

  return (
    <div className="shell">
      <header className="topbar">
        <h1 className="title">SAR Fleet Console</h1>
        <ConnectionBadge status={status} />
      </header>
      <main className="workspace">
        <p className="placeholder">
          Map, aircraft list and tasking arrive in milestone M3 (see PLAN.md).
        </p>
      </main>
    </div>
  );
}
