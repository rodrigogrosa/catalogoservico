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

// sessionStorage: tokens não persistem entre abas/janelas e são limpos ao fechar o browser.
// Isso reduz a superfície de ataque de XSS comparado ao localStorage.
function storage(): Storage | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage;
}

export function getStoredAuthSession(): AuthSession | null {
  const store = storage();
  if (!store) return null;
  const raw = store.getItem(AUTH_STORAGE_KEY);
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
  const store = storage();
  if (!store) return;
  store.setItem(AUTH_STORAGE_KEY, JSON.stringify(session));
}

export function clearStoredAuthSession() {
  const store = storage();
  if (!store) return;
  store.removeItem(AUTH_STORAGE_KEY);
}
