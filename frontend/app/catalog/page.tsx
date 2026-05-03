"use client";

import { useState, useCallback } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { AccessDeniedPanel } from "@/components/permission-gate";
import { ProjectList } from "@/components/project-list";
import { SalesCatalogPanel } from "@/components/sales-catalog-panel";
import { ProjectStatCard } from "@/components/project-stat-card";
import { useProjects } from "@/hooks/use-projects";
import { backfillCatalog, renameAllProjects } from "@/lib/api";
import { PERMISSIONS } from "@/lib/permissions";
import { buildProjectMetrics } from "@/lib/project-metrics";

const PER_PAGE = 20;
// Sales catalog always fetches the full list so every project with a sales_profile
// is visible regardless of which page the "Acervo" tab is currently on.
const SALES_PER_PAGE = 200;

export default function CatalogPage() {
  const { can } = useAuth();
  const [activeTab, setActiveTab] = useState<"projects" | "sales">("projects");
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [backfilling, setBackfilling] = useState(false);
  const [backfillMsg, setBackfillMsg] = useState<string | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [renameMsg, setRenameMsg] = useState<string | null>(null);

  // Paginated fetch for the "Acervo de projetos" tab.
  const { error, loading, projects, total, pages, refreshProjects } = useProjects({
    page,
    per_page: PER_PAGE,
    search: debouncedSearch || undefined,
  });

  // Full-list fetch for the "Catálogo de venda" tab — independent of pagination.
  const { projects: salesItems, loading: salesLoading, refreshProjects: refreshSales } = useProjects({
    page: 1,
    per_page: SALES_PER_PAGE,
    search: debouncedSearch || undefined,
  });

  const metrics = buildProjectMetrics(projects);

  const handleBackfill = useCallback(async () => {
    setBackfilling(true);
    setBackfillMsg(null);
    try {
      const result = await backfillCatalog();
      setBackfillMsg(`${result.fixed} ficha(s) gerada(s), ${result.skipped} já existiam.`);
      void refreshSales();
      void refreshProjects();
    } catch {
      setBackfillMsg("Erro ao sincronizar fichas. Tente novamente.");
    } finally {
      setBackfilling(false);
    }
  }, [refreshSales, refreshProjects]);

  const handleRenameAll = useCallback(async () => {
    setRenaming(true);
    setRenameMsg(null);
    try {
      const result = await renameAllProjects();
      setRenameMsg(`${result.renamed} projeto(s) renomeado(s), ${result.skipped} sem alteração.`);
      void refreshProjects();
      void refreshSales();
    } catch {
      setRenameMsg("Erro ao renomear projetos. Tente novamente.");
    } finally {
      setRenaming(false);
    }
  }, [refreshProjects, refreshSales]);

  function handleSearchChange(e: React.ChangeEvent<HTMLInputElement>) {
    setSearch(e.target.value);
    // Simple debounce: reset to page 1 and update after a short delay.
    const value = e.target.value;
    clearTimeout((handleSearchChange as { _timer?: ReturnType<typeof setTimeout> })._timer);
    (handleSearchChange as { _timer?: ReturnType<typeof setTimeout> })._timer = setTimeout(() => {
      setDebouncedSearch(value);
      setPage(1);
    }, 300);
  }

  return (
    <AppShell
      active="Catálogo"
      title="Catálogo comercial e técnico"
      subtitle="Gerencie produções, galeria principal e preparação comercial em uma mesma vitrine."
    >
      {!can(PERMISSIONS.catalogView) ? (
        <div className="portal-stack pb-12">
          <AccessDeniedPanel description="Seu perfil não possui acesso ao catálogo de projetos e produtos." />
        </div>
      ) : (
      <div className="portal-stack pb-12">
        <section className="py-10">
          <div className="portal-card rounded-[1.8rem] px-6 py-6">
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <ProjectStatCard label="Total do acervo" value={`${total}`} />
              <ProjectStatCard label="Prontos para uso" value={`${metrics.completed}`} tone="success" />
              <ProjectStatCard label="Em processamento" value={`${metrics.processing}`} />
              <ProjectStatCard label="Pontos de atenção" value={`${metrics.needsAttention}`} tone="warning" />
            </div>
          </div>
        </section>

        {error ? <p className="rounded-[1.35rem] border border-red-200 bg-red-50 px-5 py-4 text-base text-red-700">{error}</p> : null}
        {renameMsg && (
          <p className="rounded-[1.35rem] border border-blue-200 bg-blue-50 px-5 py-3 text-sm text-blue-800">{renameMsg}</p>
        )}

        <section className="portal-card rounded-[1.6rem] px-5 py-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="section-kicker">Áreas do catálogo</p>
              <h3 className="mt-2 text-2xl font-semibold text-slate-950">Escolha a visão que faz sentido para a operação</h3>
            </div>
            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => void handleRenameAll()}
                disabled={renaming}
                className="rounded-full border border-blue-200 bg-blue-50 px-4 py-2.5 text-sm font-semibold text-blue-800 transition hover:bg-blue-100 disabled:opacity-50"
              >
                {renaming ? "Renomeando…" : "Renomear todos em PT"}
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("projects")}
                className={`rounded-full px-5 py-3 text-sm font-semibold transition ${activeTab === "projects" ? "bg-slate-950 text-white" : "border border-slate-900/10 bg-white text-slate-700"}`}
              >
                Acervo de projetos
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("sales")}
                className={`rounded-full px-5 py-3 text-sm font-semibold transition ${activeTab === "sales" ? "bg-slate-950 text-white" : "border border-slate-900/10 bg-white text-slate-700"}`}
              >
                Catálogo de venda
              </button>
            </div>
          </div>

          {/* Search bar */}
          <div className="mt-4">
            <input
              type="search"
              value={search}
              onChange={handleSearchChange}
              placeholder="Buscar projeto por nome…"
              className="w-full rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-800 placeholder-slate-400 outline-none focus:ring-2 focus:ring-slate-900/20"
            />
          </div>
        </section>

        {loading && activeTab === "projects" ? (
          <div className="portal-card rounded-[1.6rem] px-6 py-6 text-base text-slate-700">Carregando catálogo...</div>
        ) : salesLoading && activeTab === "sales" ? (
          <div className="portal-card rounded-[1.6rem] px-6 py-6 text-base text-slate-700">Carregando vitrine de vendas...</div>
        ) : activeTab === "sales" ? (
          <>
            {backfillMsg && (
              <p className="rounded-[1.35rem] border border-emerald-200 bg-emerald-50 px-5 py-3 text-sm text-emerald-800">{backfillMsg}</p>
            )}
            <SalesCatalogPanel
              items={salesItems}
              onSyncRequest={handleBackfill}
              syncing={backfilling}
            />
          </>
        ) : (
          <ProjectList items={projects} onProjectDeleted={refreshProjects} />
        )}

        {/* Pagination controls */}
        {!loading && pages > 1 && (
          <div className="flex items-center justify-center gap-3 pt-2">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-40"
            >
              ← Anterior
            </button>
            <span className="text-sm text-slate-600">
              Página {page} de {pages} · {total} projetos
            </span>
            <button
              type="button"
              disabled={page >= pages}
              onClick={() => setPage((p) => Math.min(pages, p + 1))}
              className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-40"
            >
              Próxima →
            </button>
          </div>
        )}
      </div>
      )}
    </AppShell>
  );
}
