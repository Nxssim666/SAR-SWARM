import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { PreflightReportView } from '../api/types';
import { useSession } from '../session/session';
import { PreflightSection } from './PreflightSection';

const NEVER: PreflightReportView = {
  aircraft_id: 'a1',
  checked_at: null,
  values: {},
  findings: [],
  ready: false,
};
const BLOCKED: PreflightReportView = {
  aircraft_id: 'a1',
  checked_at: '2026-09-30T12:00:00Z',
  values: { NAV_DLL_ACT: 0 },
  findings: [
    {
      parameter: 'NAV_DLL_ACT',
      value: 0,
      severity: 'block',
      message: 'Nothing happens when the link is lost.',
    },
  ],
  ready: false,
};

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } });
}

function renderSection() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <PreflightSection aircraftId="a1" />
    </QueryClientProvider>,
  );
}

describe('preflight section', () => {
  beforeEach(() => {
    useSession.getState().signIn({
      token: 't',
      user: { user_id: 'u', username: 'op1', display_name: 'Op One' },
      permissions: ['fleet.view', 'aircraft.command'],
      expiresAt: '2026-10-01T00:00:00Z',
    });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    useSession.getState().signOut(null);
  });

  it('says never checked, and a check shows what blocks the aircraft', async () => {
    const fetch = vi.fn((_url: string, init: RequestInit) =>
      Promise.resolve(json(init.method === 'POST' ? BLOCKED : NEVER)),
    );
    vi.stubGlobal('fetch', fetch);
    renderSection();

    expect(await screen.findByText('not checked yet')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Check failsafes' }));

    expect(await screen.findByText(/^blocked/)).toBeInTheDocument();
    expect(
      screen.getByText('Nothing happens when the link is lost.', { exact: false }),
    ).toBeVisible();
    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/aircraft/a1/preflight',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('offers no check to a role that cannot command', async () => {
    useSession.getState().signIn({
      token: 't',
      user: { user_id: 'u', username: 'obs', display_name: 'Obs' },
      permissions: ['fleet.view'],
      expiresAt: '2026-10-01T00:00:00Z',
    });
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(json(NEVER))),
    );
    renderSection();

    expect(await screen.findByText('not checked yet')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Check failsafes' })).toBeNull();
  });
});
