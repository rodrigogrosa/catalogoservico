"use client";

import { createContext, type ReactNode, useContext, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { fetchCurrentUser, loginMaster } from "@/lib/api";
import {
  clearStoredAuthSession,
  getStoredAuthSession,
  saveStoredAuthSession,
  type AuthSession,
  type AuthUser,
} from "@/lib/auth-storage";

type AuthContextValue = {
  session: AuthSession | null;
  user: AuthUser | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [session, setSession] = useState<AuthSession | null>(null);
  const [loading, setLoading] = useState(true);
  const isLoginPage = pathname === "/login";

  useEffect(() => {
    const stored = getStoredAuthSession();
    if (!stored) {
      setSession(null);
      setLoading(false);
      if (!isLoginPage) router.replace("/login");
      return;
    }

    setSession(stored);
    setLoading(false);
    void fetchCurrentUser()
      .then((user) => {
        const refreshed = { ...stored, user };
        saveStoredAuthSession(refreshed);
        setSession(refreshed);
      })
      .catch(() => {
        clearStoredAuthSession();
        setSession(null);
        if (!isLoginPage) router.replace("/login");
      });
  }, [isLoginPage, router]);

  async function login(username: string, password: string) {
    const nextSession = await loginMaster(username, password);
    saveStoredAuthSession(nextSession);
    setSession(nextSession);
    router.replace("/");
  }

  function logout() {
    clearStoredAuthSession();
    setSession(null);
    router.replace("/login");
  }

  const value = useMemo<AuthContextValue>(
    () => ({
      session,
      user: session?.user ?? null,
      loading,
      login,
      logout,
    }),
    [session, loading],
  );

  if (!isLoginPage && loading) {
    return (
      <main className="flex min-h-screen items-center justify-center px-6">
        <section className="panel max-w-lg p-8 text-center">
          <p className="section-kicker">Autenticação</p>
          <h1 className="mt-3 text-3xl font-semibold text-slate-950">Validando sessão...</h1>
        </section>
      </main>
    );
  }

  if (!isLoginPage && !session) {
    return (
      <main className="flex min-h-screen items-center justify-center px-6">
        <section className="panel max-w-lg p-8 text-center">
          <p className="section-kicker">Acesso restrito</p>
          <h1 className="mt-3 text-3xl font-semibold text-slate-950">Redirecionando para login...</h1>
        </section>
      </main>
    );
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth deve ser usado dentro de AuthProvider.");
  return context;
}
