// User administration (M5). Supervisors see the accounts; admins create them, change roles,
// deactivate or reactivate them (users are never deleted: the audit names them), and reset
// passwords. The last admin is protected by the server.
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { api, ProblemError } from '../api/client';
import type { Role } from '../api/types';
import { can, useSession } from '../session/session';

interface UserOut {
  id: string;
  username: string;
  display_name: string;
  role: Role;
  is_active: boolean;
  last_login_at: string | null;
}

const ROLES: Role[] = ['observer', 'operator', 'supervisor', 'admin'];
export const MIN_PASSWORD = 10;

export function UsersPanel() {
  const session = useSession((s) => s.session);
  const token = session?.token ?? null;
  const queryClient = useQueryClient();
  const users = useQuery({
    queryKey: ['users'],
    queryFn: ({ signal }) => api<{ items: UserOut[] }>('/users?limit=200', { token, signal }),
  });
  const [error, setError] = useState<string | null>(null);
  const manage = can(session, 'users.manage');

  const change = async (path: string, method: 'PATCH' | 'POST', body: unknown) => {
    setError(null);
    try {
      await api(path, { method, body, token });
      await queryClient.invalidateQueries({ queryKey: ['users'] });
    } catch (e) {
      setError(e instanceof ProblemError ? e.message : 'The change failed.');
    }
  };

  return (
    <section aria-label="Users">
      <table className="admin-table">
        <thead>
          <tr>
            <th>User</th>
            <th>Role</th>
            <th>Status</th>
            <th>Last sign-in</th>
            {manage && <th aria-label="Actions" />}
          </tr>
        </thead>
        <tbody>
          {users.data?.items.map((u) => (
            <tr key={u.id} data-active={u.is_active}>
              <td>
                <strong>{u.display_name}</strong> <span className="muted">{u.username}</span>
              </td>
              <td>
                {manage ? (
                  <select
                    aria-label={`Role of ${u.username}`}
                    value={u.role}
                    onChange={(e) =>
                      void change(`/users/${u.id}`, 'PATCH', { role: e.target.value })
                    }
                  >
                    {ROLES.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                ) : (
                  u.role
                )}
              </td>
              <td>{u.is_active ? 'active' : 'deactivated'}</td>
              <td>{u.last_login_at ? new Date(u.last_login_at).toLocaleString() : 'never'}</td>
              {manage && (
                <td className="actions">
                  <button
                    type="button"
                    onClick={() =>
                      void change(`/users/${u.id}`, 'PATCH', { is_active: !u.is_active })
                    }
                  >
                    {u.is_active ? 'Deactivate' : 'Reactivate'}
                  </button>
                  <ResetPassword
                    username={u.username}
                    onReset={(password) =>
                      change(`/users/${u.id}/password`, 'POST', { new_password: password })
                    }
                  />
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {manage && <NewUser onCreate={(body) => change('/users', 'POST', body)} />}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </section>
  );
}

function ResetPassword({
  username,
  onReset,
}: {
  username: string;
  onReset: (password: string) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState('');
  if (!open) {
    return (
      <button
        type="button"
        onClick={() => {
          setOpen(true);
        }}
      >
        Reset password
      </button>
    );
  }
  return (
    <form
      className="inline-form"
      onSubmit={(e) => {
        e.preventDefault();
        void onReset(password).then(() => {
          setOpen(false);
          setPassword('');
        });
      }}
    >
      <input
        type="password"
        autoComplete="new-password"
        aria-label={`New password for ${username}`}
        value={password}
        onChange={(e) => {
          setPassword(e.target.value);
        }}
      />
      <button type="submit" disabled={password.length < MIN_PASSWORD}>
        Set
      </button>
    </form>
  );
}

function NewUser({ onCreate }: { onCreate: (body: unknown) => Promise<void> }) {
  const [username, setUsername] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [role, setRole] = useState<Role>('operator');
  const [password, setPassword] = useState('');
  const valid =
    /^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$/.test(username) &&
    displayName.trim().length > 0 &&
    password.length >= MIN_PASSWORD;

  return (
    <details className="new-user">
      <summary>New user</summary>
      <form
        className="form"
        onSubmit={(e) => {
          e.preventDefault();
          void onCreate({
            username,
            display_name: displayName.trim(),
            role,
            password,
          }).then(() => {
            setUsername('');
            setDisplayName('');
            setPassword('');
          });
        }}
      >
        <label>
          Username (3-64: letters, digits, . _ -)
          <input
            value={username}
            onChange={(e) => {
              setUsername(e.target.value);
            }}
          />
        </label>
        <label>
          Display name
          <input
            value={displayName}
            onChange={(e) => {
              setDisplayName(e.target.value);
            }}
          />
        </label>
        <label>
          Role
          <select
            value={role}
            onChange={(e) => {
              setRole(e.target.value as Role);
            }}
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>
        <label>
          Initial password (at least {MIN_PASSWORD} characters)
          <input
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => {
              setPassword(e.target.value);
            }}
          />
        </label>
        <button type="submit" disabled={!valid}>
          Create user
        </button>
      </form>
    </details>
  );
}
