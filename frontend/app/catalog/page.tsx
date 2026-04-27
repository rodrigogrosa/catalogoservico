"use client";

import { useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { AccessDeniedPanel } from "@/components/permission-gate";
import { ProjectList } from "@/components/project-list";
import { SalesCatalogPanel } from "@/components/sales-catalog-panel";
import { ProjectStatCard } from "@/components/project-stat-card";
import { useProjects } from "@/hooks/use-projects";
import { PERMISSIONS } from "@/lib/permissions";
import { buildProjectMetrics } from "@/lib/project-metrics";

export default function CatalogPage() {
  const { can } = useAuth();
  const { error, loading, projects, refreshProjects } = useProjects();
  const [activeTab, setActiveTab] = useState<"projects" | "sales">("projects");
  const metrics = buildProjectMetrics(projects);

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
              <ProjectStatCard label="Total do acervo" value={`${metrics.total}`} />
              <ProjectStatCard label="Prontos para uso" value={`${metrics.completed}`} tone="success" />
              <ProjectStatCard label="Em processamento" value={`${metrics.processing}`} />
              <ProjectStatCard label="Pontos de atenção" value={`${metrics.needsAttention}`} tone="warning" />
            </div>
          </div>
        </section>

        {error ? <p className="rounded-[1.35rem] border border-red-200 bg-red-50 px-5 py-4 text-base text-red-700">{error}</p> : null}

        <section className="portal-card rounded-[1.6rem] px-5 py-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="section-kicker">Áreas do catálogo</p>
              <h3 className="mt-2 text-2xl font-semibold text-slate-950">Escolha a visão que faz sentido para a operação</h3>
            </div>
            <div className="flex flex-wrap gap-3">
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
        </section>

        {loading ? (
          <div className="portal-card rounded-[1.6rem] px-6 py-6 text-base text-slate-700">Carregando catálogo...</div>
        ) : activeTab === "sales" ? (
          <SalesCatalogPanel items={projects} />
        ) : (
          <ProjectList items={projects} onProjectDeleted={refreshProjects} />
        )}
      </div>
      )}
    </AppShell>
  );
}
