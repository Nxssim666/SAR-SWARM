// Audible alert cues (ADR 0031). Which cue to play is decided here, purely:
//
// - a warning or critical alert that newly appears active, or an alert whose severity rises
//   (escalation of an unacknowledged warning), cues once, the most severe first;
// - while a critical alert stays active (not acknowledged, not cleared), a reminder cues
//   every REMIND_MS;
// - the first snapshot after connecting does not replay the backlog (the list shows it),
//   except that active criticals still get their reminder.
//
// Sound never replaces the visual alert: every cue has an alert on screen.
import type { AlertView } from '../api/types';

export type Cue = 'critical' | 'warning';

export const REMIND_MS = 30_000;

const RANK: Record<AlertView['severity'], number> = { info: 0, warning: 1, critical: 2 };

function cueOf(severity: AlertView['severity']): Cue | null {
  return severity === 'critical' ? 'critical' : severity === 'warning' ? 'warning' : null;
}

/** The cue for a change of the alert set (null: none). */
export function cueFor(
  previous: Readonly<Record<string, AlertView>> | null,
  next: Readonly<Record<string, AlertView>>,
): Cue | null {
  if (previous === null) return null; // first snapshot: no replay
  let best: Cue | null = null;
  for (const alert of Object.values(next)) {
    if (alert.state !== 'active') continue;
    const before = previous[alert.id];
    const isNew = !before || before.state === 'cleared';
    const escalated = before !== undefined && RANK[alert.severity] > RANK[before.severity];
    if (!isNew && !escalated) continue;
    const cue = cueOf(alert.severity);
    if (cue === 'critical') return 'critical';
    if (cue === 'warning') best = 'warning';
  }
  return best;
}

/** Whether a critical alert is active (the reminder keeps sounding until acknowledged). */
export function criticalActive(alerts: Readonly<Record<string, AlertView>>): boolean {
  return Object.values(alerts).some((a) => a.state === 'active' && a.severity === 'critical');
}

/** Tones of each cue: [frequency Hz, duration ms, pause ms]. Critical: three high beeps. */
export const TONES: Record<Cue, [number, number, number][]> = {
  critical: [
    [1320, 140, 90],
    [1320, 140, 90],
    [1320, 140, 0],
  ],
  warning: [[880, 220, 0]],
};
