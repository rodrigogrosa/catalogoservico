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
  const recentProjects = useMemo(() => latestProjects(projects, 4), [projects]);

  return (
    <AppShell
      active="Visão geral"
      title="Portal de operação e vendas"
      subtitle="Um ambiente profissional para transformar arquivos 3D em produtos prontos para imprimir, apresentar e publicar."
    >
      <div className="portal-stack pb-12">
        <section className="py-10 md:py-14">
          <div className="hero-panel grid gap-8 overflow-hidden rounded-[2rem] px-7 py-8 md:px-10 md:py-10 xl:grid-cols-[1.2fr_0.8fr] xl:items-center">
            <div className="max-w-4xl">
              <p className="section-kicker">Portal EuAchei3D</p>
              <h1 className="mt-4 text-5xl font-semibold leading-[0.95] text-slate-950 md:text-7xl">
                Da importação do modelo ao anúncio final.
              </h1>
              <p className="mt-6 max-w-3xl text-xl leading-9 text-slate-600">
                Centralize arquivos, conversão para Snapmaker, monitoramento de execução, galeria de produtos e preparo comercial com uma identidade forte e fluxo limpo.
              </p>
              <div className="mt-8 flex flex-wrap gap-4">
                <Link href="/new-project" className="portal-action portal-action-primary">
                  Enviar arquivo ou link
                </Link>
                <Link href="/catalog" className="portal-action">
                  Abrir portfólio
                </Link>
              </div>
            </div>

            <div className="grid-overlay relative min-h-[320px] overflow-hidden rounded-[1.8rem] border border-white/60 bg-slate-950 px-6 py-6 text-white">
              <div className="absolute -right-8 top-8 h-32 w-32 rounded-full bg-orange-500/30 blur-3xl" />
              <div className="absolute -left-10 bottom-4 h-40 w-40 rounded-full bg-sky-400/10 blur-3xl" />
              <div className="relative z-10">
                <p className="brand-kicker text-orange-200">Resumo executivo</p>
                <div className="mt-6 grid gap-4">
                  <div className="rounded-[1.4rem] border border-white/10 bg-white/5 px-5 py-5">
                    <p className="text-sm uppercase tracking-[0.18em] text-slate-400">Projetos ativos</p>
                    <p className="mt-2 text-5xl font-semibold">{metrics.total}</p>
                    <p className="mt-2 text-sm leading-6 text-slate-300">Arquivos catalogados com histórico, previews e artefatos.</p>
                  </div>
                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="rounded-[1.4rem] border border-white/10 bg-white/5 px-5 py-5">
                      <p className="text-sm uppercase tracking-[0.18em] text-slate-400">Prontos</p>
                      <p className="mt-2 text-4xl font-semibold text-emerald-300">{metrics.completed}</p>
                    </div>
                    <div className="rounded-[1.4rem] border border-white/10 bg-white/5 px-5 py-5">
                      <p className="text-sm uppercase tracking-[0.18em] text-slate-400">Atenção</p>
                      <p className="mt-2 text-4xl font-semibold text-orange-200">{metrics.needsAttention}</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="grid gap-6 py-3 xl:grid-cols-[1.35fr_0.65fr]">
          <div className="portal-card rounded-[1.8rem] px-4 py-4 md:px-6 md:py-6">
            <div className="grid gap-4 md:grid-cols-3">
              <ProjectStatCard label="Catálogo total" value={`${metrics.total}`} helper="Itens versionados e rastreáveis." />
              <ProjectStatCard label="Produção concluída" value={`${metrics.completed}`} helper="Saídas já preparadas para uso." tone="success" />
              <ProjectStatCard label="Risco operacional" value={`${metrics.needsAttention}`} helper="Projetos pedindo revisão ou resposta." tone="warning" />
            </div>
          </div>
          <div className="portal-card rounded-[1.8rem] px-6 py-6">
            <p className="section-kicker">Posicionamento</p>
            <h3 className="mt-3 text-2xl font-semibold text-slate-950">Um portal com cara de negócio</h3>
            <p className="mt-3 text-base leading-8 text-slate-600">
              Menos ruído técnico na superfície. Mais clareza para operação, catálogo, vendas e configuração de canais.
            </p>
          </div>
        </section>

        <section className="grid gap-6 py-8 xl:grid-cols-[0.92fr_1.08fr]">
          <div className="portal-card rounded-[1.8rem] px-6 py-6">
            <ProjectQueuePanel metrics={metrics} compact />
          </div>
          <div className="portal-card rounded-[1.8rem] px-6 py-6">
            <div className="flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
              <div>
                <p className="section-kicker">Áreas do portal</p>
                <h3 className="mt-2 text-3xl font-semibold text-slate-950">Cada menu conduz uma parte do negócio</h3>
              </div>
              <Link href="/stores" className="portal-action">
                Configurar canais de venda
              </Link>
            </div>
            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <PortalLane title="Entrada inteligente" text="Receba upload, pacote Bambu, link e dependências de textura num fluxo único." />
              <PortalLane title="Catálogo vendável" text="Transforme versões em uma vitrine com imagem principal, preço e copy comercial." />
              <PortalLane title="Fila operacional" text="Acompanhe processamento, bloqueios e decisões do sistema por etapa." />
              <PortalLane title="Integrações prontas" text="Conecte login social e marketplaces numa camada administrativa separada." />
            </div>
          </div>
        </section>

        {error ? <p className="rounded-[1.35rem] border border-red-200 bg-red-50 px-5 py-4 text-base text-red-700">{error}</p> : null}

        <section className="py-3">
          {loading ? (
            <div className="portal-card rounded-[1.8rem] px-6 py-6 text-base text-slate-700">Carregando visão principal...</div>
          ) : (
            <ProjectList
              items={recentProjects}
              onProjectDeleted={refreshProjects}
              title="Produções recentes"
              description="Acesso rápido aos projetos mais recentes já tratados pelo portal."
            />
          )}
        </section>
      </div>
    </AppShell>
  );
}

function PortalLane({ title, text }: { title: string; text: string }) {
  return (
    <div className="rounded-[1.4rem] border border-slate-900/10 bg-white/70 px-5 py-5">
      <p className="info-label">Área especializada</p>
      <h4 className="mt-3 text-xl font-semibold text-slate-950">{title}</h4>
      <p className="mt-2 text-base leading-7 text-slate-600">{text}</p>
    </div>
  );
}
