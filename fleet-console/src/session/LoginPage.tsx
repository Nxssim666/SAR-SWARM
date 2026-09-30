import { useState } from 'react';

import { ProblemError } from '../api/client';
import { login, useSession } from './session';

export function LoginPage() {
  const ended = useSession((s) => s.ended);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: { preventDefault: () => void }) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
    } catch (e) {
      if (e instanceof ProblemError && e.status === 429) {
        setError('Too many failed sign-ins. Wait a few minutes and try again.');
      } else if (e instanceof ProblemError && e.status === 401) {
        setError('Wrong username or password.');
      } else {
        setError('The fleet service cannot be reached.');
      }
      setPassword('');
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="login">
      <form className="panel" onSubmit={(e) => void submit(e)} aria-label="Sign in">
        <h1>SAR Fleet Console</h1>
        {ended && (
          <p className="notice" role="status">
            {ended}
          </p>
        )}
        <label>
          Username
          <input
            autoComplete="username"
            value={username}
            required
            onChange={(e) => {
              setUsername(e.target.value);
            }}
          />
        </label>
        <label>
          Password
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            required
            onChange={(e) => {
              setPassword(e.target.value);
            }}
          />
        </label>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <button type="submit" disabled={busy}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </main>
  );
}
