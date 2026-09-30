// The operator's session (ADR 0009, ADR 0027): the token lives in sessionStorage, per tab. It
// survives a reload but not closing the tab, and never goes into localStorage or a URL.
import { create } from 'zustand';

import { api, onUnauthorized } from '../api/client';
import type { LoginResponse, Permission, UserRef } from '../api/types';

const STORAGE_KEY = 'sargcs.session';

export interface Session {
  token: string;
  user: UserRef;
  permissions: Permission[];
  expiresAt: string;
}

interface SessionState {
  session: Session | null;
  /** Why the last session ended (shown on the login page), or null. */
  ended: string | null;
  signIn: (session: Session) => void;
  signOut: (reason: string | null) => void;
  setExpiry: (expiresAt: string) => void;
}

function stored(): Session | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

function store(session: Session | null): void {
  try {
    if (session) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // storage unavailable (private mode): the session lasts until reload
  }
}

export const useSession = create<SessionState>()((set) => ({
  session: stored(),
  ended: null,
  signIn: (session) => {
    store(session);
    set({ session, ended: null });
  },
  signOut: (reason) => {
    store(null);
    set({ session: null, ended: reason });
  },
  setExpiry: (expiresAt) => {
    set((state) => {
      if (!state.session) return state;
      const session = { ...state.session, expiresAt };
      store(session);
      return { session };
    });
  },
}));

onUnauthorized(() => {
  if (useSession.getState().session) {
    useSession.getState().signOut('Your session has ended. Please sign in again.');
  }
});

export function can(session: Session | null, permission: Permission): boolean {
  return session?.permissions.includes(permission) ?? false;
}

/** Sign in; on success the session is stored. Rejects with ProblemError. */
export async function login(username: string, password: string): Promise<void> {
  const response = await api<LoginResponse>('/auth/login', {
    method: 'POST',
    body: { username, password },
  });
  useSession.getState().signIn({
    token: response.token,
    user: {
      user_id: response.user.id,
      username: response.user.username,
      display_name: response.user.display_name,
    },
    permissions: response.permissions,
    expiresAt: response.expires_at,
  });
}

/** End the session on the server (best effort) and here. */
export async function logout(): Promise<void> {
  const token = useSession.getState().session?.token;
  try {
    if (token) await api<undefined>('/auth/logout', { method: 'POST', token });
  } finally {
    useSession.getState().signOut(null);
  }
}
