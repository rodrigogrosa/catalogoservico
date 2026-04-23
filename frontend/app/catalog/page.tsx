"use client";

import { useState } from "react";

import { AppShell } from "@/components/app-shell";
import { ProjectList } from "@/components/project-list";
import { SalesCatalogPanel } from "@/components/sales-catalog-panel";
import { ProjectStatCard } from "@/components/project-stat-card";
import { useProjects } from "@/hooks/use-projects";
import { buildProjectMetrics } from "@/lib/project-metrics";

export default function CatalogPage() {
  const { error, loading, projects, refreshProjects } = useProjects();
  const [activeTab, setActiveTab] = useState<"projects" | "sales">("projects");
  const metrics = buildProjectMetrics(projects);

  return (
    <AppShell
      active="Catálogo"
      title="Catálogo de projetos"
      subtitle="Biblioteca organizada de projetos, versões geradas e estados de conversão para Snapmaker U1."
    >
      <div className="portal-stack">
        <section className="grid border-b border-slate-900/10 py-7 sm:grid-cols-2 xl:grid-cols-4">
          <ProjectStatCard label="Total" value={`${metrics.total}`} />
          <ProjectStatCard label="Prontos" value={`${metrics.completed}`} tone="success" />
          <ProjectStatCard label="Processando" value={`${metrics.processing}`} />
          <ProjectStatCard label="Atenção" value={`${metrics.needsAttention}`} tone="warning" />
        </section>

        {error ? <p className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-base text-red-700">{error}</p> : null}

        <div className="flex flex-col gap-3 border-b border-slate-900/10 py-5 sm:flex-row">
          <button
            type="button"
            onClick={() => setActiveTab("projects")}
            className={`rounded-full px-6 py-4 text-base font-semibold transition ${activeTab === "projects" ? "bg-slate-950 text-white" : "border border-slate-900/10 bg-transparent text-slate-700"}`}
          >
            Projetos
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("sales")}
            className={`rounded-full px-6 py-4 text-base font-semibold transition ${activeTab === "sales" ? "bg-slate-950 text-white" : "border border-slate-900/10 bg-transparent text-slate-700"}`}
          >
            Venda do produto
          </button>
        </div>

        {loading ? (
          <div className="border-b border-slate-900/10 py-6 text-base text-slate-700">Carregando catálogo...</div>
        ) : activeTab === "sales" ? (
          <SalesCatalogPanel items={projects} />
        ) : (
          <ProjectList items={projects} onProjectDeleted={refreshProjects} />
        )}
      </div>
    </AppShell>
  );
}
