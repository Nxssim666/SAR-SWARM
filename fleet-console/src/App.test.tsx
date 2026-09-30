import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { App } from './App';
import { ConnectionBadge } from './components/ConnectionBadge';
import { useBackendHealth } from './hooks/useBackendHealth';
import { useSession } from './session/session';

function problem(status: number): Response {
  return new Response(
    JSON.stringify({
      type: 'x',
      title: 'Error',
      status,
      detail: null,
      instance: null,
      errors: null,
    }),
    { status, headers: { 'Content-Type': 'application/problem+json' } },
  );
}

describe('sign-in', () => {
  beforeEach(() => {
    useSession.getState().signOut(null);
  });

  it('shows the sign-in form without a session', () => {
    render(<App />);
    expect(screen.getByRole('form', { name: 'Sign in' })).toBeInTheDocument();
    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password');
  });

  it('says why a sign-in failed, and clears the password', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(problem(401))),
    );
    render(<App />);

    await userEvent.type(screen.getByLabelText('Username'), 'op1');
    await userEvent.type(screen.getByLabelText('Password'), 'wrong-password');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Wrong username or password.');
    expect(screen.getByLabelText('Password')).toHaveValue('');
  });

  it('explains the lockout after too many failures', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(problem(429))),
    );
    render(<App />);

    await userEvent.type(screen.getByLabelText('Username'), 'op1');
    await userEvent.type(screen.getByLabelText('Password'), 'wrong-password');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/Too many failed sign-ins/);
  });

  it('shows why the last session ended', () => {
    useSession.getState().signOut('Your session has ended. Please sign in again.');
    render(<App />);
    expect(screen.getByRole('status')).toHaveTextContent('Your session has ended.');
  });
});

function healthResponse(serverTime: Date): Response {
  return new Response(JSON.stringify({ status: 'ok', server_time: serverTime.toISOString() }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

function Badge() {
  return <ConnectionBadge status={useBackendHealth()} />;
}

describe('connection badge', () => {
  it('reports connected when the fleet service is healthy', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(healthResponse(new Date()))),
    );
    render(<Badge />);
    expect(await screen.findByText('Connected')).toBeInTheDocument();
  });

  it('warns when the client clock disagrees with the ground station', async () => {
    // The server's clock answers 30 s ahead of this one, whenever the request is served.
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(healthResponse(new Date(Date.now() + 30_000)))),
    );
    render(<Badge />);
    expect(await screen.findByText(/clock off by 30\.\d s/)).toBeInTheDocument();
  });

  it('reports offline when the fleet service is unreachable', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
    );
    render(<Badge />);
    expect(await screen.findByText('Fleet service offline')).toBeInTheDocument();
  });
});
