// The audit viewer's filters as a query string, and a one-line summary of an event's
// details. Pure and tested.

export interface AuditFilterForm {
  action: string;
  entityType: string;
  entityId: string;
  /** datetime-local values (the browser's local time); sent as UTC instants. */
  since: string;
  until: string;
}

export const EMPTY_FILTERS: AuditFilterForm = {
  action: '',
  entityType: '',
  entityId: '',
  since: '',
  until: '',
};

/** The filters (and extra parameters) as a URL query; empty fields are left out. */
export function auditQuery(form: AuditFilterForm, extra: Record<string, string> = {}): string {
  const params = new URLSearchParams();
  if (form.action.trim()) params.set('action', form.action.trim());
  if (form.entityType.trim()) params.set('entity_type', form.entityType.trim());
  if (form.entityId.trim()) params.set('entity_id', form.entityId.trim());
  for (const [key, value] of [
    ['since', form.since],
    ['until', form.until],
  ] as const) {
    if (value) {
      const instant = new Date(value);
      if (!Number.isNaN(instant.getTime())) params.set(key, instant.toISOString());
    }
  }
  for (const [key, value] of Object.entries(extra)) params.set(key, value);
  return params.toString();
}

/** A short, readable line for an event's details (the full record is in the export). */
export function summarize(details: Record<string, unknown>, max = 140): string {
  const text = JSON.stringify(details);
  if (text === '{}') return '';
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}
