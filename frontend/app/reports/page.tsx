"use client";

import Link from "next/link";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { AccessDeniedPanel } from "@/components/permission-gate";
import { ProjectStatCard } from "@/components/project-stat-card";
import { useProjects } from "@/hooks/use-projects";
import { PERMISSIONS } from "@/lib/permissions";
import { buildProjectMetrics, latestProjects } from "@/lib/project-metrics";

export default function ReportsPage() {
  const { can } = useAuth();
  const { error, loading, projects } = useProjects();
  const metrics = buildProjectMetrics(projects);
  const recentItems = latestProjects(projects, 10);

  return (
    <AppShell
      active="Relatórios"
      title="Relatórios e auditoria"
      subtitle="Área para localizar entregáveis, manifestos, scores e rastreabilidade dos projetos convertidos."
    >
      {!can(PERMISSIONS.reportsView) ? (
        <div className="portal-stack">
          <AccessDeniedPanel description="Seu perfil não possui acesso à área de relatórios e auditoria." />
        </div>
      ) : (
      <div className="portal-stack">
        <section className="grid border-b border-slate-900/10 py-7 md:grid-cols-4">
          <ProjectStatCard label="Projetos" value={`${metrics.total}`} />
          <ProjectStatCard label="Prontos" value={`${metrics.completed}`} tone="success" />
          <ProjectStatCard label="Falhas" value={`${metrics.failed}`} tone="danger" />
          <ProjectStatCard label="Atenção" value={`${metrics.needsAttention}`} tone="warning" />
        </section>

        <section className="border-b border-slate-900/10 py-8">
          <p className="section-kicker">Persistência</p>
          <h2 className="mt-2 text-2xl font-semibold text-slate-950">Pasta local de entregáveis</h2>
          <p className="mt-4 break-words border-l-4 border-orange-300 pl-4 font-mono text-base text-slate-700">
            ~/Downloads/Projetos3d/SnapMaker3d
          </p>
          <div className="mt-5 grid gap-8 md:grid-cols-3">
            <ReportCard title="Manifesto" text="project_manifest.json com hashes, versões e decisões." />
            <ReportCard title="Relatório técnico" text="Markdown e JSON com achados, riscos e ações." />
            <ReportCard title="Export final" text="Arquivo final único e bundle consolidado por projeto." />
          </div>
        </section>

        {error ? <p className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-base text-red-700">{error}</p> : null}

        <section className="border-b border-slate-900/10 py-8">
          <p className="section-kicker">Projetos recentes</p>
          <h2 className="mt-2 text-2xl font-semibold text-slate-950">Abrir relatórios por projeto</h2>
          <div className="mt-5 divide-y divide-slate-900/10">
            {loading ? <p className="text-base text-slate-600">Carregando relatórios...</p> : null}
            {!loading && recentItems.length === 0 ? <p className="text-base text-slate-600">Nenhum relatório disponível ainda.</p> : null}
            {recentItems.map((project) => (
              <Link
                key={project.id}
                href={`/projects/${project.id}`}
                className="flex flex-col gap-3 py-4 transition hover:text-orange-800 md:flex-row md:items-center md:justify-between"
              >
                <div>
                  <h3 className="text-base font-semibold text-slate-950">{project.name}</h3>
                  <p className="mt-1 text-sm text-slate-500">v{String(project.version).padStart(3, "0")} · {project.source_ecosystem.replaceAll("_", " ")}</p>
                </div>
                <span className="rounded-full bg-orange-500/10 px-3 py-1 text-sm font-semibold text-orange-800">Abrir relatório</span>
              </Link>
            ))}
          </div>
        </section>
      </div>
      )}
    </AppShell>
  );
}

function ReportCard({ title, text }: { title: string; text: string }) {
  return (
    <div className="border-l border-slate-900/10 pl-4">
      <h3 className="text-base font-semibold text-slate-950">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-slate-600">{text}</p>
    </div>
  );
}
