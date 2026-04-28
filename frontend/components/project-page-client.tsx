"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { AccessDeniedPanel } from "@/components/permission-gate";
import { ProjectDetailView } from "@/components/project-detail";
import { fetchProject, type ProjectDetail } from "@/lib/api";
import { getCachedProjectSummary, summaryToPartialDetail } from "@/lib/project-cache";
import { PERMISSIONS } from "@/lib/permissions";

export function ProjectPageClient({ id }: { id: string }) {
  return <ProjectPageSectionClient id={id} section="overview" />;
}

export function ProjectPageSectionClient({
  id,
  section,
}: {
  id: string;
  section: "overview" | "process" | "diagnostics" | "files" | "images";
}) {
  const { can } = useAuth();

  // Seed the initial state from the catalog in-memory cache (if available).
  // This makes the page render instantly on navigation from the catalog —
  // no spinner, no blank screen.  The full detail replaces it silently.
  const [project, setProject] = useState<ProjectDetail | null>(() => {
    const cached = getCachedProjectSummary(id);
    return cached ? summaryToPartialDetail(cached) : null;
  });
  const [error, setError] = useState<string | null>(null);
  // loading=true only when we have NO data at all (cold load, direct URL hit)
  const [loading, setLoading] = useState(project === null);
  // refreshing=true when we already have partial data and are fetching full detail
  const [refreshing, setRefreshing] = useState(project !== null);
  const fetchedRef = useRef(false);

  useEffect(() => {
    if (fetchedRef.current) return;
    fetchedRef.current = true;

    let cancelled = false;
    async function loadFull() {
      try {
        const result = await fetchProject(id);
        if (cancelled) return;
        setProject(result);
        setError(null);
      } catch (firstError) {
        if (cancelled) return;
        // Only retry if we have no partial data (slow network / cold start)
        if (project === null) {
          await new Promise((resolve) => setTimeout(resolve, 1200));
          try {
            const retry = await fetchProject(id);
            if (cancelled) return;
            setProject(retry);
            setError(null);
          } catch (finalError) {
            if (cancelled) return;
            setError(finalError instanceof Error ? finalError.message : "Falha ao carregar projeto.");
          }
        } else {
          // We already have partial data — silently swallow the error;
          // the user sees the cached summary and can refresh manually.
          console.warn("[SnapMaker3d] Full detail fetch failed, using cached summary", firstError);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
          setRefreshing(false);
        }
      }
    }
    void loadFull();
    return () => {
      cancelled = true;
    };
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) {
    return (
      <AppShell active="Catálogo" title="Carregando projeto" subtitle="Buscando dados do portal do projeto.">
        <section className="panel p-6 text-base text-slate-700">Carregando projeto...</section>
      </AppShell>
    );
  }

  if (!can(PERMISSIONS.projectsView)) {
    return (
      <AppShell active="Catálogo" title="Acesso restrito" subtitle="Seu perfil não tem permissão para abrir detalhes técnicos de projeto.">
        <AccessDeniedPanel description="Seu perfil não possui acesso aos detalhes técnicos do projeto." />
      </AppShell>
    );
  }

  if (!project || error) {
    return (
      <AppShell active="Catálogo" title="Projeto indisponível" subtitle="O portal não conseguiu recuperar os dados deste projeto.">
        <div className="mx-auto max-w-3xl space-y-6">
          <Link href="/catalog" className="text-sm text-accentSoft underline">
            Voltar para o catálogo
          </Link>
          <section className="panel p-6 md:p-8">
            <p className="section-kicker">Projeto indisponível</p>
            <h1 className="mt-3 text-3xl font-semibold text-slate-950">Não foi possível carregar este projeto.</h1>
            <p className="mt-4 text-base leading-7 text-slate-700">{error ?? "Projeto não encontrado."}</p>
          </section>
        </div>
      </AppShell>
    );
  }

  const sectionMeta = {
    overview: {
      title: project.name,
      subtitle: "Resumo principal do projeto em uma leitura limpa e direta.",
    },
    process: {
      title: `Processar · ${project.name}`,
      subtitle: "Configuração e disparo de execução em uma página exclusiva.",
    },
    diagnostics: {
      title: `Diagnóstico · ${project.name}`,
      subtitle: "Achados, riscos, etapas e pendências sem poluição visual.",
    },
    files: {
      title: `Arquivos · ${project.name}`,
      subtitle: "Entrega, logs, manifesto e bundle final em uma área própria.",
    },
    images: {
      title: `Imagens · ${project.name}`,
      subtitle: "Galeria completa das fotos e previews disponíveis deste projeto.",
    },
  } as const;

  return (
    <AppShell active="Catálogo" title={sectionMeta[section].title} subtitle={sectionMeta[section].subtitle}>
      {/* Subtle top-bar indicator while fetching the full detail in background */}
      {refreshing && (
        <div className="fixed left-0 top-0 z-50 h-0.5 w-full animate-pulse bg-orange-400" aria-hidden />
      )}
      <div className="mx-auto max-w-5xl space-y-6">
        <Link href="/catalog" className="text-sm text-accentSoft underline">
          Voltar para o catálogo
        </Link>
        <ProjectDetailView project={project} section={section} />
      </div>
    </AppShell>
  );
}
