import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { App } from './App';

function healthResponse(serverTime: Date): Response {
  return new Response(JSON.stringify({ status: 'ok', server_time: serverTime.toISOString() }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('App shell', () => {
  it('shows the console title', () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise<Response>(() => undefined)),
    );

    render(<App />);

    expect(screen.getByRole('heading', { name: 'SAR Fleet Console' })).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Connecting');
  });

  it('reports connected when the fleet service is healthy', async () => {
    const fetchMock = vi.fn(() => Promise.resolve(healthResponse(new Date())));
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);

    expect(await screen.findByText('Connected')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/health', expect.anything());
  });

  it('warns when the client clock disagrees with the ground station', async () => {
    const serverAhead = new Date(Date.now() + 30_000);
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(healthResponse(serverAhead))),
    );

    render(<App />);

    expect(await screen.findByText(/clock off by 30\.\d s/)).toBeInTheDocument();
  });

  it('reports offline when the fleet service is unreachable', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
    );

    render(<App />);

    expect(await screen.findByText('Fleet service offline')).toBeInTheDocument();
  });

  it('reports offline on an HTTP error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(new Response('', { status: 502 }))),
    );

    render(<App />);

    expect(await screen.findByText('Fleet service offline')).toHaveAttribute(
      'title',
      'health check failed: HTTP 502',
    );
  });
});
