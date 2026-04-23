"use client";

import Link from "next/link";
import { type FormEvent, useEffect, useState } from "react";

import { BrandMark } from "@/components/brand-mark";
import { useAuth } from "@/components/auth-provider";
import { fetchOAuthProviders, type OAuthProviderStatus } from "@/lib/api";

export default function LoginPage() {
  const { login } = useAuth();
  const [username, setUsername] = useState("rodrigogrosa");
  const [password, setPassword] = useState("");
  const [providers, setProviders] = useState<OAuthProviderStatus[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    void fetchOAuthProviders()
      .then(setProviders)
      .catch(() => setProviders([]));
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(username, password);
    } catch (loginError) {
      setError(loginError instanceof Error ? loginError.message : "Falha ao entrar.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen px-4 py-8 md:px-8">
      <div className="mx-auto grid min-h-[calc(100vh-4rem)] max-w-6xl items-center gap-6 lg:grid-cols-[1.05fr_0.95fr]">
        <section className="clean-hero overflow-hidden rounded-[2rem] p-7 md:p-10">
          <BrandMark href="" />
          <p className="section-kicker mt-8">Portal profissional</p>
          <h1 className="mt-4 text-4xl font-semibold leading-tight text-slate-950 md:text-6xl">
            Controle operação, catálogo e canais num só lugar.
          </h1>
          <p className="mt-5 max-w-2xl text-lg leading-8 text-slate-600">
            Entre com o acesso master ou habilite Google, Apple e Instagram na área administrativa para transformar o sistema em um portal vendável.
          </p>
          <div className="mt-8 grid gap-3 sm:grid-cols-3">
            <InfoCard title="Operação" text="Entrada, fila, catálogo e relatórios." />
            <InfoCard title="Vendas" text="Marketplaces, copy e publicação guiada." />
            <InfoCard title="Acesso" text="Login master e camadas sociais configuráveis." />
          </div>
        </section>

        <section className="portal-card rounded-[2rem] p-5 md:p-7">
          <p className="section-kicker">Login</p>
          <h2 className="mt-2 text-3xl font-semibold text-slate-950">Entrar no portal</h2>

          <form onSubmit={handleSubmit} className="mt-6 space-y-4">
            <label className="block">
              <span className="text-sm font-semibold text-slate-700">Usuário</span>
              <input
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                className="mt-2 w-full rounded-[1.1rem] border border-slate-900/10 bg-white px-4 py-3 text-base outline-none transition focus:border-orange-500"
                autoComplete="username"
              />
            </label>
            <label className="block">
              <span className="text-sm font-semibold text-slate-700">Senha</span>
              <input
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                type="password"
                className="mt-2 w-full rounded-[1.1rem] border border-slate-900/10 bg-white px-4 py-3 text-base outline-none transition focus:border-orange-500"
                autoComplete="current-password"
              />
            </label>
            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-[1.2rem] bg-slate-950 px-5 py-4 text-base font-semibold text-white transition hover:bg-slate-800 disabled:opacity-60"
            >
              {loading ? "Entrando..." : "Entrar como master"}
            </button>
          </form>

          {error ? <p className="mt-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p> : null}

          <div className="my-6 flex items-center gap-3">
            <span className="h-px flex-1 bg-slate-900/10" />
            <span className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">ou</span>
            <span className="h-px flex-1 bg-slate-900/10" />
          </div>

          <div className="space-y-3">
            {providers.map((provider) => (
              <SocialButton key={provider.provider} provider={provider} />
            ))}
            {providers.length === 0 ? (
              <p className="rounded-2xl border border-slate-900/10 bg-white/70 px-4 py-3 text-sm leading-6 text-slate-600">
                Provedores sociais indisponíveis no momento. Use o acesso master.
              </p>
            ) : null}
            <p className="rounded-2xl border border-slate-900/10 bg-white/70 px-4 py-3 text-sm leading-6 text-slate-600">
              A configuração completa de Google, Apple e Instagram fica na área <strong>Login social</strong>, acessível após entrar como master.
            </p>
          </div>
          <div className="mt-5">
            <Link href="/" className="text-sm font-semibold text-orange-700">
              Voltar para a página principal
            </Link>
          </div>
        </section>
      </div>
    </main>
  );
}

function SocialButton({ provider }: { provider: OAuthProviderStatus }) {
  function openProvider() {
    if (provider.enabled && provider.auth_url) window.location.href = provider.auth_url;
  }

  return (
    <button
      type="button"
      onClick={openProvider}
      disabled={!provider.enabled}
      className="flex w-full items-center justify-between rounded-[1.1rem] border border-slate-900/10 bg-white px-4 py-3 text-left transition hover:border-orange-500/40 disabled:cursor-not-allowed disabled:opacity-60"
    >
      <span>
        <span className="block text-sm font-semibold text-slate-950">Entrar com {provider.label}</span>
        <span className="mt-1 block text-xs leading-5 text-slate-500">
          {provider.enabled ? "OAuth configurado." : provider.reason ?? "Configuração pendente."}
        </span>
      </span>
      <span className="rounded-full bg-slate-950 px-3 py-1 text-xs font-semibold text-white">
        {provider.enabled ? "Abrir" : "Configurar"}
      </span>
    </button>
  );
}

function InfoCard({ title, text }: { title: string; text: string }) {
  return (
    <div className="rounded-[1.25rem] border border-slate-900/10 bg-white/72 p-4">
      <h3 className="text-sm font-semibold text-slate-950">{title}</h3>
      <p className="mt-1 text-sm leading-6 text-slate-600">{text}</p>
    </div>
  );
}
