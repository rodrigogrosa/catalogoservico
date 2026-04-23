"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { deleteProject, fileUrl, ProjectSummary } from "@/lib/api";
import { StatusBadge } from "@/components/status-badge";

type Props = {
  items: ProjectSummary[];
  title?: string;
  description?: string;
  onProjectDeleted?: () => Promise<void> | void;
};

const filters = [
  { label: "Todos", value: "all" },
  { label: "Prontos", value: "completed" },
  { label: "Enviados", value: "uploaded" },
  { label: "Processando", value: "processing" },
  { label: "Atenção", value: "attention" },
] as const;

export function ProjectList({ items, title = "Projetos e versões", description = "Encontre rapidamente o projeto, status e versão final sem abrir relatórios técnicos.", onProjectDeleted }: Props) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<(typeof filters)[number]["value"]>("all");
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return items.filter((project) => {
      const matchesQuery =
        normalizedQuery.length === 0 ||
        [project.name, project.id, project.input_format, project.source_ecosystem].some((value) =>
          value.toLowerCase().includes(normalizedQuery),
        );
      const matchesFilter =
        filter === "all" ||
        project.status === filter ||
        (filter === "attention" && (project.status === "awaiting_user" || project.printable_score?.level === "high"));
      return matchesQuery && matchesFilter;
    });
  }, [filter, items, query]);

  return (
    <div className="border-b border-slate-900/10 py-8">
      <div className="space-y-5">
        <div>
          <p className="section-kicker">Catálogo</p>
          <h2 className="mt-2 text-3xl font-semibold text-slate-950 md:text-4xl">{title}</h2>
          <p className="mt-3 max-w-3xl text-lg leading-8 text-slate-600">{description}</p>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Buscar projeto"
            className="w-full rounded-full border border-slate-900/10 bg-white px-5 py-4 text-base outline-none transition placeholder:text-slate-400 focus:border-orange-500 sm:max-w-xl"
          />
          <span className="pill">{filtered.length} itens</span>
        </div>
      </div>

      <div className="mt-5 flex gap-2 overflow-x-auto pb-1">
        {filters.map((item) => {
          const active = filter === item.value;
          return (
            <button
              key={item.value}
              type="button"
              onClick={() => setFilter(item.value)}
              className={`shrink-0 rounded-full border px-5 py-3 text-base font-semibold transition ${
                active ? "border-slate-950 bg-slate-950 text-white" : "border-slate-900/10 bg-white text-slate-700 hover:border-orange-500/40"
              }`}
            >
              {item.label}
            </button>
          );
        })}
      </div>

      <div className="mt-7 space-y-5">
        {deleteError ? (
          <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 md:col-span-2 2xl:col-span-3">
            {deleteError}
          </div>
        ) : null}
        {filtered.length === 0 ? (
          <div className="border-t border-slate-900/10 py-6 text-base text-slate-600">Nenhum projeto encontrado para este filtro.</div>
        ) : (
          filtered.map((project) => (
            <ProjectCard
              key={project.id}
              deleting={deletingId === project.id}
              onDelete={async () => {
                if (project.status === "processing") {
                  setDeleteError("Nao e seguro excluir um projeto em processamento.");
                  return;
                }
                const confirmed = window.confirm(`Excluir "${project.name}" do catalogo? Esta acao remove a pasta desta versao do disco.`);
                if (!confirmed) return;
                setDeleteError(null);
                setDeletingId(project.id);
                try {
                  await deleteProject(project.id);
                  await onProjectDeleted?.();
                } catch (error) {
                  setDeleteError(error instanceof Error ? error.message : "Falha ao excluir projeto.");
                } finally {
                  setDeletingId(null);
                }
              }}
              project={project}
            />
          ))
        )}
      </div>
    </div>
  );
}

function ProjectCard({ deleting, onDelete, project }: { deleting: boolean; onDelete: () => void; project: ProjectSummary }) {
  const score = project.printable_score;
  const riskLabel = score ? `${score.score}/100 · risco ${score.level}` : "Sem score";
  const previewHref = fileUrl(project.preview_url);
  const hasImagePreview = previewHref ? /\.(png|jpe?g|webp)(\?.*)?$/i.test(previewHref) : false;

  return (
    <article className="group border-t border-slate-900/10 py-6 transition hover:border-orange-500/40">
      <div className="grid gap-6 lg:grid-cols-[320px_1fr] lg:items-center">
        <Link href={`/projects/${project.id}`} className="relative block aspect-[4/3] overflow-hidden bg-slate-100">
          {previewHref && hasImagePreview ? (
            <img
              src={previewHref}
              alt={`Preview do projeto ${project.name}`}
              className="h-full w-full object-cover transition duration-300 group-hover:scale-[1.03]"
              loading="lazy"
            />
          ) : (
            <div className="flex h-full w-full flex-col items-center justify-center bg-gradient-to-br from-slate-100 to-orange-50 px-5 text-center">
              <span className="rounded-full bg-white px-3 py-1 text-sm font-semibold uppercase tracking-[0.18em] text-slate-500">Sem preview</span>
              <p className="mt-3 text-base leading-7 text-slate-500">A imagem principal será exibida após a geração do preview.</p>
            </div>
          )}
        </Link>

        <div className="min-w-0">
          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div className="min-w-0">
              <Link href={`/projects/${project.id}`} className="block">
                <h3 className="text-2xl font-semibold leading-tight text-slate-950">{project.name}</h3>
              </Link>
              <p className="mt-2 text-base text-slate-500">v{String(project.version).padStart(3, "0")} · {project.input_format.toUpperCase()}</p>
            </div>
            <StatusBadge status={project.status} />
          </div>

          <div className="mt-5 border-l-4 border-slate-200 pl-4">
            <p className="text-sm font-semibold uppercase tracking-[0.2em] text-slate-400">Origem</p>
            <p className="mt-2 text-base font-semibold text-slate-700">{project.source_ecosystem.replaceAll("_", " ")}</p>
          </div>

          <div className="mt-5 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <span className="text-base font-semibold text-slate-600">{riskLabel}</span>
            <div className="flex flex-wrap gap-3">
              <Link href={`/projects/${project.id}`} className="rounded-full bg-orange-500/10 px-5 py-3 text-base font-semibold text-orange-800 transition group-hover:bg-orange-500 group-hover:text-white">
                Abrir
              </Link>
              <button
                type="button"
                disabled={deleting || project.status === "processing"}
                onClick={onDelete}
                className="rounded-full border border-red-200 bg-red-50 px-5 py-3 text-base font-semibold text-red-700 transition hover:border-red-300 hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {deleting ? "Excluindo..." : "Excluir"}
              </button>
            </div>
          </div>

        </div>
      </div>
    </article>
  );
}
