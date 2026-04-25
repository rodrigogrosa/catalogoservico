"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { AccessDeniedPanel } from "@/components/permission-gate";
import { ProjectDetailView } from "@/components/project-detail";
import { fetchProject, type ProjectDetail } from "@/lib/api";
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
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void fetchProject(id)
      .then((result) => {
        setProject(result);
        setError(null);
      })
      .catch((loadError) => setError(loadError instanceof Error ? loadError.message : "Falha ao carregar projeto."))
      .finally(() => setLoading(false));
  }, [id]);

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
      <div className="mx-auto max-w-5xl space-y-6">
        <Link href="/catalog" className="text-sm text-accentSoft underline">
          Voltar para o catálogo
        </Link>
        <ProjectDetailView project={project} section={section} />
      </div>
    </AppShell>
  );
}
