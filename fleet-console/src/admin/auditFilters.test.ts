import { describe, expect, it } from 'vitest';

import { auditQuery, EMPTY_FILTERS, summarize } from './auditFilters';

describe('audit filters', () => {
  it('sends only the filters in use, with times as UTC instants', () => {
    const query = auditQuery(
      { ...EMPTY_FILTERS, action: ' command. ', since: '2026-09-30T10:00' },
      { limit: '50' },
    );
    const params = new URLSearchParams(query);

    expect(params.get('action')).toBe('command.');
    expect(params.get('since')).toBe(new Date('2026-09-30T10:00').toISOString());
    expect(params.has('entity_type')).toBe(false);
    expect(params.get('limit')).toBe('50');
  });

  it('ignores an unreadable time rather than sending it', () => {
    expect(auditQuery({ ...EMPTY_FILTERS, until: 'not a time' })).toBe('');
  });

  it('summarizes details on one line, cut to length', () => {
    expect(summarize({})).toBe('');
    expect(summarize({ a: 1 })).toBe('{"a":1}');
    expect(summarize({ text: 'x'.repeat(200) }, 20)).toHaveLength(20);
  });
});
