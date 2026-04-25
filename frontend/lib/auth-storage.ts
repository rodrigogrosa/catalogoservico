export type AuthUser = {
  username: string;
  display_name: string;
  role: string;
  provider: string;
  role_label?: string | null;
  permissions: string[];
  status?: string;
};

export type AuthSession = {
  access_token: string;
  token_type: string;
  expires_at: string;
  user: AuthUser;
};

const AUTH_STORAGE_KEY = "snapmaker3d.auth.session";

export function getStoredAuthSession(): AuthSession | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(AUTH_STORAGE_KEY);
  if (!raw) return null;
  try {
    const session = JSON.parse(raw) as AuthSession;
    if (!session.access_token || new Date(session.expires_at).getTime() <= Date.now()) {
      clearStoredAuthSession();
      return null;
    }
    return session;
  } catch {
    clearStoredAuthSession();
    return null;
  }
}

export function getStoredAuthToken(): string | null {
  return getStoredAuthSession()?.access_token ?? null;
}

export function saveStoredAuthSession(session: AuthSession) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(session));
}

export function clearStoredAuthSession() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(AUTH_STORAGE_KEY);
}
