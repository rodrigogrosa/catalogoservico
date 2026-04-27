"use client";

import Link from "next/link";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { AccessDeniedPanel } from "@/components/permission-gate";
import { ProjectQueuePanel } from "@/components/project-queue-panel";
import { StatusBadge } from "@/components/status-badge";
import { useProjects } from "@/hooks/use-projects";
import { PERMISSIONS } from "@/lib/permissions";
import { buildProjectMetrics, latestProjects } from "@/lib/project-metrics";

export default function QueuePage() {
  const { can } = useAuth();
  const { error, loading, projects } = useProjects();
  const metrics = buildProjectMetrics(projects);
  const activeItems = projects.filter((project) => ["uploaded", "processing", "awaiting_user", "failed"].includes(project.status));
  const recentItems = latestProjects(projects, 8);

  return (
    <AppShell
      active="Fila"
      title="Fila de processamento"
      subtitle="Acompanhe projetos em andamento, falhas e itens que precisam de resposta antes da exportação final."
    >
      {!can(PERMISSIONS.queueView) ? (
        <div className="portal-stack">
          <AccessDeniedPanel description="Seu perfil não possui acesso à fila operacional." />
        </div>
      ) : (
      <div className="portal-stack">
        <ProjectQueuePanel metrics={metrics} />

        {error ? <p className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-base text-red-700">{error}</p> : null}

        <section className="border-b border-slate-900/10 py-8">
          <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="section-kicker">Operação</p>
              <h2 className="mt-2 text-2xl font-semibold text-slate-950">Itens que exigem acompanhamento</h2>
            </div>
            <Link href="/new-project" className="rounded-full bg-slate-950 px-5 py-3 text-sm font-semibold text-white">
              Novo projeto
            </Link>
          </div>

          <div className="mt-5 divide-y divide-slate-900/10">
            {loading ? <p className="text-base text-slate-600">Carregando fila...</p> : null}
            {!loading && activeItems.length === 0 ? <p className="text-base text-slate-600">Nenhum projeto aguardando ação agora.</p> : null}
            {activeItems.map((project) => (
              <Link
                key={project.id}
                href={`/projects/${project.id}`}
                className="flex flex-col gap-3 py-4 transition hover:text-orange-800 md:flex-row md:items-center md:justify-between"
              >
                <div>
                  <h3 className="text-base font-semibold text-slate-950">{project.name}</h3>
                  <p className="mt-1 text-sm text-slate-500">v{String(project.version).padStart(3, "0")} · {project.input_format.toUpperCase()}</p>
                </div>
                <StatusBadge status={project.status} />
              </Link>
            ))}
          </div>
        </section>

        <section className="border-b border-slate-900/10 py-8">
          <p className="section-kicker">Histórico rápido</p>
          <h2 className="mt-2 text-2xl font-semibold text-slate-950">Últimos movimentos</h2>
          <div className="mt-5 divide-y divide-slate-900/10">
            {recentItems.map((project) => (
              <Link key={project.id} href={`/projects/${project.id}`} className="block py-4">
                <p className="truncate text-base font-semibold text-slate-950">{project.name}</p>
                <p className="mt-1 text-sm text-slate-500">{new Date(project.updated_at).toLocaleString("pt-BR")}</p>
              </Link>
            ))}
          </div>
        </section>
      </div>
      )}
    </AppShell>
  );
}
