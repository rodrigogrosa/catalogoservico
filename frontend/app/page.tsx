"use client";

import Link from "next/link";
import { useMemo } from "react";

import { AppShell } from "@/components/app-shell";
import { ProjectList } from "@/components/project-list";
import { ProjectQueuePanel } from "@/components/project-queue-panel";
import { ProjectStatCard } from "@/components/project-stat-card";
import { useProjects } from "@/hooks/use-projects";
import { buildProjectMetrics, latestProjects } from "@/lib/project-metrics";

export default function HomePage() {
  const { error, loading, projects, refreshProjects } = useProjects();
  const metrics = useMemo(() => buildProjectMetrics(projects), [projects]);
  const recentProjects = useMemo(() => latestProjects(projects, 6), [projects]);

  return (
    <AppShell
      active="Visão geral"
      title="Painel de projetos"
      subtitle="Um fluxo mais simples para enviar, acompanhar e abrir projetos prontos para Snapmaker U1."
    >
      <div className="portal-stack">
        <section className="border-b border-slate-900/10 py-10 md:py-14">
          <div className="max-w-6xl">
            <p className="section-kicker">Visão executiva</p>
            <h1 className="mt-3 max-w-5xl text-5xl font-semibold leading-tight text-slate-950 md:text-7xl">
              Operação organizada por áreas especializadas.
            </h1>
            <p className="mt-5 max-w-4xl text-xl leading-9 text-slate-600">
              Use cada página para uma responsabilidade: entrada de arquivos, catálogo, fila e relatórios. A home mostra apenas o estado geral.
            </p>
            <div className="mt-8 flex flex-wrap gap-4">
              <Link href="/new-project" className="rounded-full bg-slate-950 px-6 py-4 text-base font-semibold text-white transition hover:bg-slate-800">
                Criar novo projeto
              </Link>
              <Link href="/catalog" className="rounded-full border border-slate-900/10 bg-white px-6 py-4 text-base font-semibold text-slate-800 transition hover:border-orange-500/40">
                Abrir catálogo
              </Link>
            </div>
          </div>
        </section>

        <section className="grid border-b border-slate-900/10 py-7 md:grid-cols-3">
          <ProjectStatCard label="Projetos" value={`${metrics.total}`} />
          <ProjectStatCard label="Concluídos" value={`${metrics.completed}`} tone="success" />
          <ProjectStatCard label="Em atenção" value={`${metrics.needsAttention}`} tone="warning" />
        </section>

        <section>
          <ProjectQueuePanel metrics={metrics} compact />
        </section>

        {error ? <p className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-base text-red-700">{error}</p> : null}

        <section>
          {loading ? (
            <div className="panel p-6 text-base text-slate-700">Carregando visão geral...</div>
          ) : (
            <ProjectList
              items={recentProjects}
              onProjectDeleted={refreshProjects}
              title="Projetos recentes"
              description="Atalhos para os últimos projetos alterados. O catálogo completo fica em uma página própria."
            />
          )}
        </section>

        <section className="border-b border-slate-900/10 py-8">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="section-kicker">Mapa do sistema</p>
              <h2 className="mt-2 text-3xl font-semibold text-slate-950">Cada menu abre uma área dedicada</h2>
            </div>
            <Link href="/reports" className="rounded-full bg-white px-6 py-4 text-base font-semibold text-slate-800">
              Ver relatórios
            </Link>
          </div>
        </section>
      </div>
    </AppShell>
  );
}
