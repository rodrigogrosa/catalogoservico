"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { StatusBadge } from "@/components/status-badge";
import { deleteProject, fetchProjectBundle, fetchProjectPrintFile, fileUrl, ProjectSummary } from "@/lib/api";
import { downloadUrlToUser } from "@/lib/download";
import { PERMISSIONS } from "@/lib/permissions";

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

export function ProjectList({
  items,
  title = "Portfólio operacional",
  description = "Encontre rapidamente a versão certa, a imagem principal e o estágio de entrega de cada projeto.",
  onProjectDeleted,
}: Props) {
  const { can } = useAuth();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<(typeof filters)[number]["value"]>("all");
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [downloadStatus, setDownloadStatus] = useState<string | null>(null);

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
    <div className="portal-card rounded-[1.9rem] px-6 py-6 md:px-7">
      <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <p className="section-kicker">Portfólio</p>
          <h2 className="mt-2 text-3xl font-semibold text-slate-950 md:text-4xl">{title}</h2>
          <p className="mt-3 max-w-3xl text-lg leading-8 text-slate-600">{description}</p>
        </div>
        <div className="flex flex-col gap-3 md:flex-row md:items-center">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Buscar projeto, origem ou formato"
            className="w-full rounded-full border border-slate-900/10 bg-white px-5 py-4 text-base outline-none transition placeholder:text-slate-400 focus:border-orange-500 md:min-w-[360px]"
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
              className={`rounded-full px-4 py-2.5 text-sm font-semibold transition ${
                active ? "bg-slate-950 text-white" : "border border-slate-900/10 bg-white text-slate-700"
              }`}
            >
              {item.label}
            </button>
          );
        })}
      </div>

      <div className="mt-7 space-y-5">
        {deleteError ? <div className="rounded-[1.3rem] border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{deleteError}</div> : null}
        {downloadStatus ? <div className="rounded-[1.3rem] border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{downloadStatus}</div> : null}
        {filtered.length === 0 ? (
          <div className="rounded-[1.4rem] border border-dashed border-slate-900/10 px-5 py-8 text-base text-slate-600">
            Nenhum projeto encontrado com esse filtro.
          </div>
        ) : (
          filtered.map((project) => (
            <ProjectCard
              key={project.id}
              deleting={deletingId === project.id}
              downloading={downloadingId === project.id}
              canDelete={can(PERMISSIONS.projectsDelete)}
              canDownload={can(PERMISSIONS.projectsDownload)}
              canOpen={can(PERMISSIONS.projectsView)}
              onDownload={async () => {
                setDeleteError(null);
                setDownloadStatus(null);
                setDownloadingId(project.id);
                try {
                  const printFile = await fetchProjectPrintFile(project.id);
                  const href = fileUrl(printFile.path);
                  if (!href) throw new Error("print_file_missing");
                  await downloadUrlToUser(href, printFile.label);
                  setDownloadStatus(`Arquivo de impressão de ${project.name} pronto para salvar.`);
                } catch (error) {
                  try {
                    const bundle = await fetchProjectBundle(project.id);
                    const href = fileUrl(bundle.path);
                    if (!href) throw new Error("bundle_missing");
                    await downloadUrlToUser(href, bundle.label);
                    setDownloadStatus(`Arquivo final indisponível. ZIP consolidado de ${project.name} baixado.`);
                  } catch (fallbackError) {
                    setDeleteError(fallbackError instanceof Error ? fallbackError.message : "Falha ao baixar projeto.");
                  }
                } finally {
                  setDownloadingId(null);
                }
              }}
              onDelete={async () => {
                if (project.status === "processing") {
                  setDeleteError("Não é seguro excluir um projeto em processamento.");
                  return;
                }
                const confirmed = window.confirm(`Excluir "${project.name}" do portal? Esta ação remove a pasta desta versão.`);
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

function ProjectCard({
  deleting,
  downloading,
  canDelete,
  canDownload,
  canOpen,
  onDelete,
  onDownload,
  project,
}: {
  deleting: boolean;
  downloading: boolean;
  canDelete: boolean;
  canDownload: boolean;
  canOpen: boolean;
  onDelete: () => void;
  onDownload: () => void;
  project: ProjectSummary;
}) {
  const score = project.printable_score;
  const riskLabel = score ? `${score.score}/100 · risco ${score.level}` : "score pendente";
  const previewHref = fileUrl(project.preview_url);
  const hasImagePreview = previewHref ? /\.(png|jpe?g|webp)(\?.*)?$/i.test(previewHref) : false;

  return (
    <article className="overflow-hidden rounded-[1.6rem] border border-slate-900/10 bg-white/78 shadow-[0_12px_40px_rgba(15,23,42,0.06)]">
      <div className="grid gap-0 xl:grid-cols-[320px_1fr]">
        <Link href={`/projects/${project.id}`} className="relative block min-h-[240px] bg-slate-100">
          {previewHref && hasImagePreview ? (
            <img
              src={previewHref}
              alt={`Preview do projeto ${project.name}`}
              className="h-full w-full object-cover"
              loading="lazy"
            />
          ) : (
            <div className="soft-grid flex h-full w-full items-center justify-center bg-gradient-to-br from-slate-100 to-orange-50 px-6 text-center">
              <div>
                <p className="section-kicker">Sem imagem final</p>
                <p className="mt-3 text-base leading-7 text-slate-500">A galeria principal aparecerá assim que o preview comercial for gerado.</p>
              </div>
            </div>
          )}
        </Link>

        <div className="px-6 py-6">
          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div className="min-w-0">
              <p className="info-label">Versão {String(project.version).padStart(3, "0")}</p>
              <Link href={`/projects/${project.id}`} className="block">
                <h3 className="mt-2 text-3xl font-semibold leading-tight text-slate-950">{project.name}</h3>
              </Link>
              <p className="mt-2 text-base text-slate-500">
                {project.input_format.toUpperCase()} · {project.source_ecosystem.replaceAll("_", " ")}
              </p>
            </div>
            <StatusBadge status={project.status} />
          </div>

          <div className="mt-6 grid gap-4 md:grid-cols-3">
            <InfoBlock label="Origem" value={project.source_ecosystem.replaceAll("_", " ")} />
            <InfoBlock label="Formato" value={project.input_format.toUpperCase()} />
            <InfoBlock label="Imprimibilidade" value={riskLabel} highlight={score?.level === "high"} />
          </div>

          <div className="mt-5 flex flex-wrap items-center gap-3 text-sm text-slate-600">
            <span className="pill">{hasImagePreview ? "Imagem principal disponível" : "Abrir galeria do projeto"}</span>
            <Link href={`/projects/${project.id}/images`} className="font-semibold text-orange-700 underline underline-offset-4">
              Abrir galeria do projeto
            </Link>
          </div>

          <div className="mt-6 flex flex-wrap gap-3">
            {canOpen ? (
              <Link href={`/projects/${project.id}`} className="portal-action portal-action-primary">
                Abrir projeto
              </Link>
            ) : null}
            {canOpen ? (
              <Link href={`/projects/${project.id}/images`} className="portal-action">
                Ver imagens
              </Link>
            ) : null}
            {canDownload ? (
              <button
                type="button"
                disabled={downloading}
                onClick={onDownload}
                className="portal-action"
              >
                {downloading ? "Preparando download..." : "Baixar para imprimir"}
              </button>
            ) : null}
            {canDelete ? (
              <button
                type="button"
                disabled={deleting || project.status === "processing"}
                onClick={onDelete}
                className="portal-action border-red-200 bg-red-50 text-red-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {deleting ? "Excluindo..." : "Excluir"}
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </article>
  );
}

function InfoBlock({ label, value, highlight = false }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className={`rounded-[1.15rem] border px-4 py-4 ${highlight ? "border-orange-200 bg-orange-50" : "border-slate-900/10 bg-slate-50/80"}`}>
      <p className="info-label">{label}</p>
      <p className="mt-2 text-sm font-semibold text-slate-900">{value}</p>
    </div>
  );
}
