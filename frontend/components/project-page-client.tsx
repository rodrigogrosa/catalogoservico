"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { ProjectDetailView } from "@/components/project-detail";
import { fetchProject, type ProjectDetail } from "@/lib/api";

export function ProjectPageClient({ id }: { id: string }) {
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
      <AppShell active="Catálogo" title="Carregando projeto" subtitle="Buscando dados técnicos e artefatos.">
        <section className="panel p-6 text-base text-slate-700">Carregando projeto...</section>
      </AppShell>
    );
  }

  if (!project || error) {
    return (
      <AppShell active="Catálogo" title="Projeto indisponível" subtitle="O backend não retornou os dados deste projeto.">
        <div className="mx-auto max-w-3xl space-y-6">
          <Link href="/" className="text-sm text-accentSoft underline">
            Voltar para a lista de projetos
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

  return (
    <AppShell active="Catálogo" title={project.name} subtitle="Detalhes técnicos, galeria, processamento e artefatos do projeto selecionado.">
      <div className="mx-auto max-w-7xl space-y-6">
        <Link href="/" className="text-sm text-accentSoft underline">
          Voltar para a lista de projetos
        </Link>
        <ProjectDetailView project={project} />
      </div>
    </AppShell>
  );
}
