"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { useAuth } from "@/components/auth-provider";

type NavItem = {
  label: string;
  href: string;
  badge?: string;
};

type Props = {
  children: ReactNode;
  active?: string;
  title?: string;
  subtitle?: string;
};

const navItems: NavItem[] = [
  { label: "Visão geral", href: "/" },
  { label: "Novo projeto", href: "/new-project" },
  { label: "Catálogo", href: "/catalog" },
  { label: "Login social", href: "/social-login" },
  { label: "Lojas", href: "/stores" },
  { label: "Fila", href: "/queue" },
  { label: "Relatórios", href: "/reports" },
];

export function AppShell({ children, active = "Visão geral", title = "SnapMaker3d Studio", subtitle }: Props) {
  const { logout, user } = useAuth();

  return (
    <main className="min-h-screen">
      <div className="flex min-h-screen w-full">
        <aside className="hidden w-72 shrink-0 border-r border-slate-900/10 bg-slate-950 text-white lg:block">
          <div className="sticky top-0 flex h-screen flex-col p-6">
            <Link href="/" className="border-b border-white/10 pb-6">
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-orange-200">Studio</p>
              <h1 className="mt-3 text-2xl font-semibold leading-tight">SnapMaker3d</h1>
              <p className="mt-2 text-base leading-7 text-slate-300">Portal de impressão 3D.</p>
            </Link>

            <nav className="mt-7 space-y-1">
              {navItems.map((item) => {
                const selected = item.label === active;
                return (
                  <Link
                    key={item.label}
                    href={item.href}
                    className={`flex items-center justify-between border-l-4 px-4 py-3.5 text-base font-semibold transition ${
                      selected ? "border-orange-300 bg-white/10 text-white" : "border-transparent text-slate-300 hover:border-white/30 hover:text-white"
                    }`}
                  >
                    <span>{item.label}</span>
                    {item.badge ? <span className="rounded-full bg-orange-400/15 px-2 py-1 text-[0.65rem] uppercase tracking-[0.16em] text-orange-100">{item.badge}</span> : null}
                  </Link>
                );
              })}
            </nav>

            <div className="mt-auto border-t border-white/10 pt-5">
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">Saída local</p>
              <p className="mt-2 break-words font-mono text-xs leading-5 text-slate-200">~/Downloads/Projetos3d/SnapMaker3d</p>
              <div className="mt-4 border-t border-white/10 pt-4">
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Sessão</p>
                <p className="mt-2 truncate text-sm font-semibold text-white">{user?.display_name ?? "Usuário"}</p>
                <p className="text-xs text-slate-400">{user?.role === "master" ? "Acesso master" : "Usuário autenticado"}</p>
                <button
                  type="button"
                  onClick={logout}
                  className="mt-3 w-full rounded-full bg-white px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-orange-100"
                >
                  Sair
                </button>
              </div>
            </div>
          </div>
        </aside>

        <section className="min-w-0 flex-1">
          <header className="border-b border-slate-900/10 bg-white/45 px-5 py-6 backdrop-blur md:px-10 2xl:px-16">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <p className="section-kicker">{active}</p>
                <h2 className="mt-2 text-3xl font-semibold text-slate-950 md:text-4xl">{title}</h2>
                {subtitle ? <p className="mt-3 max-w-3xl text-base leading-7 text-slate-600 md:text-lg">{subtitle}</p> : null}
              </div>
              <nav className="flex gap-2 overflow-x-auto lg:hidden">
                {navItems.map((item) => {
                  const selected = item.label === active;
                  return (
                    <Link
                      key={item.label}
                      href={item.href}
                      className={`shrink-0 rounded-full border px-4 py-2 text-sm font-semibold ${
                        selected ? "border-slate-950 bg-slate-950 text-white" : "border-slate-900/10 bg-white text-slate-700"
                      }`}
                    >
                      {item.label}
                    </Link>
                  );
                })}
              </nav>
              <button
                type="button"
                onClick={logout}
                className="w-fit rounded-full border border-slate-900/10 bg-white px-4 py-2 text-sm font-semibold text-slate-700 lg:hidden"
              >
                Sair
              </button>
            </div>
          </header>

          <div className="portal-shell">{children}</div>
        </section>
      </div>
    </main>
  );
}
