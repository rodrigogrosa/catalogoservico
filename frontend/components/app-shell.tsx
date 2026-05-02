"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";

import { BrandMark } from "@/components/brand-mark";
import { useAuth } from "@/components/auth-provider";
import { PERMISSIONS } from "@/lib/permissions";

type NavItem = {
  label: string;
  href: string;
  helper: string;
  permission: string;
};

type Props = {
  children: ReactNode;
  active?: string;
  title?: string;
  subtitle?: string;
};

const operationNavItems: NavItem[] = [
  { label: "Visão geral", href: "/", helper: "Comando executivo", permission: PERMISSIONS.dashboardView },
  { label: "Sobre", href: "/about", helper: "Posicionamento e fluxo", permission: PERMISSIONS.dashboardView },
  { label: "Novo projeto", href: "/new-project", helper: "Entrada e importação", permission: PERMISSIONS.projectsCreate },
  { label: "Catálogo", href: "/catalog", helper: "Portfólio e vendas", permission: PERMISSIONS.catalogView },
  { label: "Fila", href: "/queue", helper: "Operação em andamento", permission: PERMISSIONS.queueView },
  { label: "Relatórios", href: "/reports", helper: "Rastreabilidade", permission: PERMISSIONS.reportsView },
];

const configNavItems: NavItem[] = [
  { label: "Lojas", href: "/stores", helper: "Marketplaces e canais", permission: PERMISSIONS.storesView },
  { label: "Login social", href: "/social-login", helper: "Acesso e identidade", permission: PERMISSIONS.socialLoginView },
  { label: "Provedores IA", href: "/ai-settings", helper: "Fallback externo", permission: PERMISSIONS.aiSettingsView },
  { label: "Usuários", href: "/users", helper: "Perfis e acessos", permission: PERMISSIONS.usersView },
  { label: "Revisor", href: "/review", helper: "Saúde e qualidade", permission: PERMISSIONS.usersView },
  { label: "QA Suite", href: "/qa-suite", helper: "Testes automatizados", permission: PERMISSIONS.usersView },
];

export function AppShell({ children, active = "Visão geral", title = "Portal EuAchei3D", subtitle }: Props) {
  const pathname = usePathname();
  const { can, logout, user } = useAuth();
  const visibleOperationItems = operationNavItems.filter((item) => can(item.permission));
  const visibleConfigItems = configNavItems.filter((item) => can(item.permission));
  const [configOpen, setConfigOpen] = useState(false);

  const isConfigRoute = useMemo(
    () =>
      visibleConfigItems.some((item) =>
        item.href === "/" ? pathname === "/" : pathname === item.href || pathname.startsWith(`${item.href}/`)
      ),
    [pathname, visibleConfigItems]
  );

  useEffect(() => {
    if (isConfigRoute) setConfigOpen(true);
  }, [isConfigRoute]);

  function isItemActive(item: NavItem): boolean {
    return item.label === active || pathname === item.href || pathname.startsWith(`${item.href}/`);
  }

  return (
    <main className="min-h-screen">
      <div className="shell-layout relative flex min-h-screen w-full">
        <aside className="shell-sidebar hidden w-[298px] shrink-0 border-r border-white/10 text-white xl:block">
          <div className="sticky top-0 flex h-screen flex-col px-5 py-5">
            <BrandMark />

            <div className="mt-5 rounded-[1.2rem] border border-white/10 bg-white/5 px-4 py-3">
              <p className="brand-kicker">Portal</p>
              <p className="mt-2 text-sm font-semibold leading-6 text-white">
                Operação, catálogo e vendas em um único fluxo.
              </p>
            </div>

            <nav className="mt-5 grid content-start gap-1.5">
              <p className="px-2 text-[0.64rem] font-semibold uppercase tracking-[0.2em] text-slate-400">Operação</p>
              {visibleOperationItems.map((item) => {
                const selected = isItemActive(item);
                return (
                  <Link key={item.label} href={item.href} className={`nav-link ${selected ? "nav-link-active" : ""}`}>
                    <span>
                      <span className="block">{item.label}</span>
                      <span className="mt-0.5 block text-[0.68rem] font-medium tracking-[0.12em] text-slate-400">{item.helper}</span>
                    </span>
                    <span className="text-xs text-slate-500">●</span>
                  </Link>
                );
              })}

              {visibleConfigItems.length > 0 ? (
                <>
                  <p className="mt-3 px-2 text-[0.64rem] font-semibold uppercase tracking-[0.2em] text-slate-400">Plataforma</p>
                  <button
                    type="button"
                    onClick={() => setConfigOpen((current) => !current)}
                    className={`nav-link w-full text-left ${configOpen || isConfigRoute ? "nav-link-active" : ""}`}
                  >
                    <span>
                      <span className="block">Configuração</span>
                      <span className="mt-0.5 block text-[0.68rem] font-medium tracking-[0.12em] text-slate-400">Acessos, integrações e IA</span>
                    </span>
                    <span className="text-xs text-slate-400">{configOpen ? "→" : "→"}</span>
                  </button>
                </>
              ) : null}
            </nav>

            <div className="mt-auto rounded-[1.25rem] border border-white/10 bg-white/5 px-4 py-4">
              <div className="grid gap-3">
                <div>
                  <p className="brand-kicker">Sessão</p>
                  <p className="mt-2 truncate text-sm font-semibold text-white">{user?.display_name ?? "Usuário"}</p>
                  <p className="text-xs text-slate-400">{user?.role_label ?? (user?.role === "master" ? "Administrador master" : "Acesso autenticado")}</p>
                </div>
                <div>
                  <p className="brand-kicker">Pasta</p>
                  <p className="mt-2 break-words font-mono text-[0.68rem] leading-5 text-slate-300">~/Downloads/Projetos3d/SnapMaker3d</p>
                </div>
                <button
                  type="button"
                  onClick={logout}
                  className="w-full rounded-full bg-white px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-orange-100"
                >
                  Encerrar sessão
                </button>
              </div>
            </div>
          </div>
        </aside>

        {configOpen && visibleConfigItems.length > 0 ? (
          <aside className="config-flyout hidden xl:block">
            <div className="config-flyout-inner">
              <p className="px-2 text-[0.64rem] font-semibold uppercase tracking-[0.2em] text-slate-400">Configuração</p>
              <div className="mt-2 grid gap-1.5">
                {visibleConfigItems.map((item) => {
                  const selected = isItemActive(item);
                  return (
                    <Link
                      key={item.label}
                      href={item.href}
                      className={`nav-link ${selected ? "nav-link-active" : ""}`}
                      onClick={() => setConfigOpen(false)}
                    >
                      <span>
                        <span className="block">{item.label}</span>
                        <span className="mt-0.5 block text-[0.66rem] font-medium tracking-[0.1em] text-slate-400">{item.helper}</span>
                      </span>
                      <span className="text-xs text-slate-500">●</span>
                    </Link>
                  );
                })}
              </div>
            </div>
          </aside>
        ) : null}

        <section className="min-w-0 flex-1">
          <header className="shell-topbar px-6 py-5 lg:px-10 2xl:px-16">
            <div className="flex flex-col gap-5 xl:flex-row xl:items-center xl:justify-between">
              <div>
                <p className="section-kicker">{active}</p>
                <h2 className="mt-2 text-3xl font-semibold text-slate-950 md:text-5xl">{title}</h2>
                {subtitle ? <p className="portal-subtitle max-w-4xl">{subtitle}</p> : null}
              </div>

              <div className="flex flex-wrap items-center gap-3">
                {can(PERMISSIONS.projectsCreate) ? (
                  <Link href="/new-project" className="portal-action portal-action-primary">
                    Novo projeto
                  </Link>
                ) : null}
                {can(PERMISSIONS.catalogView) ? (
                  <Link href="/catalog" className="portal-action">
                    Catálogo
                  </Link>
                ) : null}
                <button type="button" onClick={logout} className="portal-action xl:hidden">
                  Sair
                </button>
              </div>
            </div>

            <div className="mt-5 flex gap-2 overflow-x-auto xl:hidden">
              {visibleOperationItems.map((item) => {
                const selected = isItemActive(item);
                return (
                  <Link
                    key={item.label}
                    href={item.href}
                    className={`shrink-0 rounded-full px-4 py-2 text-sm font-semibold transition ${
                      selected ? "bg-slate-950 text-white" : "border border-slate-900/10 bg-white/80 text-slate-700"
                    }`}
                  >
                    {item.label}
                  </Link>
                );
              })}
              {visibleConfigItems.length > 0 ? (
                <button
                  type="button"
                  onClick={() => setConfigOpen((current) => !current)}
                  className={`shrink-0 rounded-full px-4 py-2 text-sm font-semibold transition ${
                    configOpen || isConfigRoute
                      ? "bg-slate-950 text-white"
                      : "border border-slate-900/10 bg-white/80 text-slate-700"
                  }`}
                >
                  Configuração
                </button>
              ) : null}
            </div>
            {configOpen && visibleConfigItems.length > 0 ? (
              <div className="mt-3 flex gap-2 overflow-x-auto xl:hidden">
                {visibleConfigItems.map((item) => {
                  const selected = isItemActive(item);
                  return (
                    <Link
                      key={item.label}
                      href={item.href}
                      className={`shrink-0 rounded-full px-4 py-2 text-sm font-semibold transition ${
                        selected ? "bg-slate-950 text-white" : "border border-slate-900/10 bg-white/80 text-slate-700"
                      }`}
                    >
                      {item.label}
                    </Link>
                  );
                })}
              </div>
            ) : null}
          </header>

          <div className="portal-shell">{children}</div>
        </section>
      </div>
    </main>
  );
}
