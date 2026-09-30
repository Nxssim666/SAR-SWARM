// Alert severity as icon + word (+ colour in CSS): distinguishable without colour (ADR 0015).
import type { AlertView } from '../api/types';

export const SEVERITY: Record<AlertView['severity'], { icon: string; word: string }> = {
  critical: { icon: '⛔', word: 'CRITICAL' },
  warning: { icon: '⚠', word: 'WARNING' },
  info: { icon: 'ℹ', word: 'INFO' },
};
