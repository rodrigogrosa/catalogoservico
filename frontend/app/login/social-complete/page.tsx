"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { saveStoredAuthSession, type AuthSession } from "@/lib/auth-storage";

function decodeBase64Url(value: string): string {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
  return atob(padded);
}

export default function SocialLoginCompletePage() {
  const router = useRouter();
  const [message, setMessage] = useState("Concluindo login social...");

  useEffect(() => {
    try {
      const hash = window.location.hash.replace(/^#/, "");
      const params = new URLSearchParams(hash);
      const encodedSession = params.get("session");

      if (!encodedSession) {
        setMessage("Sessão social não foi recebida. Volte ao login e tente novamente.");
        return;
      }

      const session = JSON.parse(decodeBase64Url(encodedSession)) as AuthSession;
      if (!session.access_token || !session.expires_at || !session.user) {
        setMessage("A sessão retornada pelo provedor está incompleta.");
        return;
      }

      saveStoredAuthSession(session);
      setMessage("Login social concluído. Redirecionando...");
      router.replace("/");
    } catch {
      setMessage("Não foi possível concluir o login social automaticamente.");
    }
  }, [router]);

  return (
    <main className="flex min-h-screen items-center justify-center px-6">
      <section className="portal-card max-w-2xl rounded-[2rem] p-8 text-center">
        <p className="section-kicker">Login social</p>
        <h1 className="mt-3 text-4xl font-semibold text-slate-950">Conectando sua sessão</h1>
        <p className="mt-5 text-lg leading-8 text-slate-600">{message}</p>
      </section>
    </main>
  );
}
