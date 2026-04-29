"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { ModelPreview } from "@/components/model-preview";
import { StatusBadge } from "@/components/status-badge";
import {
  compareProjects,
  fetchProject,
  fetchProjectBundle,
  fetchProjectPrintFile,
  fetchProjectVersions,
  fetchProjects,
  fileUrl,
  processProject,
  reprocessProject,
  type ProcessPayload,
  type ProcessingStage,
  type ProjectCompareResponse,
  type ProjectDetail,
  type ProjectQuestion,
  type ProjectSummary,
} from "@/lib/api";
import { PERMISSIONS } from "@/lib/permissions";

type Props = {
  project: ProjectDetail;
  section: "overview" | "process" | "diagnostics" | "files" | "images";
};

const defaultPayload: ProcessPayload = {
  repair_mesh: true,
  adapt_to_snapmaker: true,
  convert_from_bambu: true,
  scale_mode: "keep",
  unit_mode: "auto",
  hollowing: false,
  objective_preset: "quality",
  orientation_priority: "support_economy",
  target_nozzle_mm: 0.4,
  supports: "auto",
  material_preferences: {
    use_case: "unknown",
    prioritize: "balanced",
  },
  color_preferences: {
    preserve_original_colors: true,
    strategy: "undecided",
  },
  hollowing_preferences: {
    enabled: false,
    shell_thickness_mm: 2,
    drain_holes: true,
    preserve_strength: true,
  },
  transform_preferences: {
    reinforce_weak_regions: false,
    add_helper_base: false,
    simplify_microdetails: false,
    allow_destructive_changes: false,
    generate_alignment_pins: false,
  },
};

const sectionMeta = {
  overview: {
    label: "Visão geral",
    title: "Resumo executivo",
    description: "Situação atual, prévia principal e caminho rápido para seguir com o projeto.",
  },
  process: {
    label: "Processar",
    title: "Configurar e processar",
    description: "Defina objetivo, material e regras essenciais em um fluxo linear e direto.",
  },
  diagnostics: {
    label: "Diagnóstico",
    title: "Achados e riscos",
    description: "Revise etapas, perguntas pendentes e o que precisa de atenção antes da entrega.",
  },
  files: {
    label: "Arquivos",
    title: "Saídas e rastreabilidade",
    description: "Abra relatórios, logs, manifesto e pacote final em uma área dedicada.",
  },
  images: {
    label: "Imagens",
    title: "Galeria completa",
    description: "Veja todas as fotos e previews disponíveis do projeto em uma área própria.",
  },
} as const;

export function ProjectDetailView({ project, section }: Props) {
  const { can } = useAuth();
  const [currentProject, setCurrentProject] = useState<ProjectDetail>(project);
  const [payload, setPayload] = useState<ProcessPayload>(() => {
    // Restore the last processing parameters saved for this project, if any.
    const saved = project.metadata?.request_parameters as ProcessPayload | undefined;
    if (saved && typeof saved === "object" && Object.keys(saved).length > 0) {
      return { ...defaultPayload, ...saved };
    }
    return defaultPayload;
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isReprocessing, setIsReprocessing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [allProjects, setAllProjects] = useState<ProjectSummary[]>([]);
  const [versions, setVersions] = useState<ProjectSummary[]>([]);
  const [comparisonTarget, setComparisonTarget] = useState("");
  const [comparison, setComparison] = useState<ProjectCompareResponse | null>(null);
  const [bundlePath, setBundlePath] = useState<string | null>(null);
  const [printFilePath, setPrintFilePath] = useState<string | null>(null);

  const isProcessing = currentProject.status === "processing";
  const processStages = useMemo(
    () => selectProcessingStages(currentProject.processing_stages, currentProject.status),
    [currentProject.processing_stages, currentProject.status],
  );
  const completedStages = processStages.filter((item) => item.status === "completed" || item.status === "skipped").length;
  const progressPercent = processStages.length ? Math.round((completedStages / processStages.length) * 100) : 0;
  const mainPreview = useMemo(() => selectMainPreview(currentProject), [currentProject]);
  const siblingVersions = versions.filter((item) => item.id !== currentProject.id);

  useEffect(() => {
    setCurrentProject(project);
    // Reload saved parameters whenever the project changes.
    const saved = project.metadata?.request_parameters as ProcessPayload | undefined;
    if (saved && typeof saved === "object" && Object.keys(saved).length > 0) {
      setPayload((prev) => ({ ...prev, ...saved }));
    }
  }, [project]);

  useEffect(() => {
    void fetchProjects().then((r) => setAllProjects(r.items)).catch(() => undefined);
    void fetchProjectVersions(project.id).then(setVersions).catch(() => undefined);
  }, [project.id]);

  useEffect(() => {
    if (!isProcessing) return;
    const timer = window.setInterval(async () => {
      try {
        const nextProject = await fetchProject(currentProject.id);
        setCurrentProject(nextProject);
      } catch {
        // noop
      }
    }, 3000);
    return () => window.clearInterval(timer);
  }, [currentProject.id, isProcessing]);

  async function handleProcess() {
    setIsSubmitting(true);
    setMessage(null);
    try {
      await processProject(currentProject.id, payload);
      const nextProject = await fetchProject(currentProject.id);
      setCurrentProject(nextProject);
      setMessage("Processamento iniciado. Acompanhe a evolução na página de diagnóstico.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao iniciar processamento.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleReprocess() {
    setIsReprocessing(true);
    setMessage(null);
    try {
      const newProject = await reprocessProject(currentProject.id, payload);
      // Refresh version list and navigate to the new version.
      void fetchProjectVersions(newProject.id).then(setVersions).catch(() => undefined);
      setCurrentProject(newProject);
      setMessage(
        `Nova versão v${String(newProject.version).padStart(3, "0")} criada e processamento iniciado. ` +
          "Acompanhe a evolução na aba Diagnóstico.",
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao criar nova versão.");
    } finally {
      setIsReprocessing(false);
    }
  }

  async function handleBundle() {
    try {
      const bundle = await fetchProjectBundle(currentProject.id);
      setBundlePath(bundle.path);
      setMessage("Pacote consolidado gerado com sucesso.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao gerar bundle.");
    }
  }

  async function handlePrintFile() {
    try {
      const printFile = await fetchProjectPrintFile(currentProject.id);
      setPrintFilePath(printFile.path);
      setMessage("Arquivo final para impressão localizado.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao localizar arquivo final para impressão.");
    }
  }

  async function handleCompare() {
    if (!comparisonTarget) return;
    try {
      const result = await compareProjects(currentProject.id, comparisonTarget);
      setComparison(result);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao comparar versões.");
    }
  }

  const meta = sectionMeta[section];

  return (
    <div className="mx-auto max-w-5xl space-y-8 pb-12">
      <section className="clean-hero rounded-[2rem] px-7 py-8 md:px-10 md:py-10">
        <div className="space-y-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="max-w-3xl">
              <p className="section-kicker">Projeto ativo</p>
              <h1 className="mt-3 text-4xl font-semibold leading-[1.02] text-slate-950 md:text-6xl">{currentProject.name}</h1>
              <p className="mt-4 text-lg leading-8 text-slate-600">
                {currentProject.original_filename} · versão {String(currentProject.version).padStart(3, "0")} · {currentProject.input_format.toUpperCase()}
              </p>
            </div>
            <StatusBadge status={currentProject.status} />
          </div>

          <div className="grid gap-3 border-t border-slate-900/8 pt-5 md:grid-cols-4">
            <MetricLine label="Progresso" value={`${progressPercent}%`} />
            <MetricLine label="Etapas concluídas" value={`${completedStages}/${processStages.length || 0}`} />
            <MetricLine label="Risco" value={currentProject.printable_score?.level ?? "medium"} />
            <MetricLine label="Bloqueios" value={String(currentProject.blocking_questions.length)} />
          </div>

          <div className="rounded-[1.4rem] border border-slate-900/8 bg-white/70 p-4">
            <p className="section-kicker">{meta.label}</p>
            <h2 className="mt-2 text-2xl font-semibold text-slate-950 md:text-3xl">{meta.title}</h2>
            <p className="mt-2 text-base leading-7 text-slate-600">{meta.description}</p>
          </div>

          <ProjectSectionNav projectId={currentProject.id} active={section} />
        </div>
      </section>

      {message ? <MessageBanner message={message} /> : null}

      {section === "overview" ? (
        <OverviewSection project={currentProject} progressPercent={progressPercent} previewUrl={mainPreview} />
      ) : null}

      {section === "process" ? (
        <ProcessSection
          project={currentProject}
          payload={payload}
          setPayload={setPayload}
          isSubmitting={isSubmitting}
          isReprocessing={isReprocessing}
          canProcess={can(PERMISSIONS.projectsProcess)}
          onProcess={handleProcess}
          onReprocess={handleReprocess}
          versions={siblingVersions}
        />
      ) : null}

      {section === "diagnostics" ? (
        <DiagnosticsSection project={currentProject} stages={processStages} previewUrl={mainPreview} />
      ) : null}

      {section === "files" ? (
        <FilesSection
          project={currentProject}
          siblingVersions={siblingVersions}
          comparisonTarget={comparisonTarget}
          setComparisonTarget={setComparisonTarget}
          comparison={comparison}
          onCompare={handleCompare}
          onBundle={handleBundle}
          bundlePath={bundlePath}
          onPrintFile={handlePrintFile}
          printFilePath={printFilePath}
        />
      ) : null}

      {section === "images" ? <ImagesSection project={currentProject} /> : null}
    </div>
  );
}

function ProjectSectionNav({
  projectId,
  active,
}: {
  projectId: string;
  active: Props["section"];
}) {
  const items = [
    { key: "overview", label: "Visão geral", href: `/projects/${projectId}` },
    { key: "process", label: "Processar", href: `/projects/${projectId}/process` },
    { key: "diagnostics", label: "Diagnóstico", href: `/projects/${projectId}/diagnostics` },
    { key: "images", label: "Imagens", href: `/projects/${projectId}/images` },
    { key: "files", label: "Arquivos", href: `/projects/${projectId}/files` },
  ] as const;

  return (
    <nav className="flex flex-wrap gap-3 border-t border-slate-900/8 pt-5">
      {items.map((item) => (
        <Link
          key={item.key}
          href={item.href}
          className={`rounded-full px-5 py-3 text-sm font-semibold transition ${
            item.key === active
              ? "bg-slate-950 text-white"
              : "border border-slate-900/10 bg-white/85 text-slate-700 hover:border-orange-500/30"
          }`}
        >
          {item.label}
        </Link>
      ))}
    </nav>
  );
}

function OverviewSection({
  project,
  progressPercent,
  previewUrl,
}: {
  project: ProjectDetail;
  progressPercent: number;
  previewUrl: string | null;
}) {
  return (
    <div className="space-y-6">
      <SectionCard
        kicker="Resumo"
        title="Situação atual do projeto"
        description="Uma leitura rápida do estado do arquivo, da origem e do que já está pronto."
      >
        <div className="space-y-4">
          <InfoPanel label="Origem" value={`Ecossistema ${project.source_ecosystem} · arquivo ${project.original_filename}`} />
          <InfoPanel label="Status" value={`${project.status} · score ${project.printable_score?.score ?? 0}`} />
          <InfoPanel label="Pasta da versão" value={project.storage_path} mono />
          <ProgressBar progress={progressPercent} label="Pipeline de processamento" />
        </div>
      </SectionCard>

      <SectionCard
        kicker="Prévia"
        title="Imagem principal"
        description="A leitura visual principal do projeto fica isolada nesta etapa para evitar concorrência com os controles."
      >
        {previewUrl ? (
          <div className="space-y-4">
            <div className="overflow-hidden rounded-[1.5rem] border border-slate-900/10 bg-white">
              <img src={previewUrl} alt={project.name} className="w-full object-cover" />
            </div>
            <a href={previewUrl} target="_blank" className="inline-flex rounded-full border border-slate-900/10 bg-white px-5 py-3 text-sm font-semibold text-slate-900">
              Abrir imagem
            </a>
          </div>
        ) : (
          <EmptyBlock text="Nenhuma prévia principal disponível ainda." />
        )}
      </SectionCard>

      <SectionCard
        kicker="Jornada"
        title="Como seguir sem fricção"
        description="O fluxo foi reorganizado para reduzir ruído visual e deixar cada decisão na sua página."
      >
        <VerticalSteps
          steps={[
            "Abra Processar para definir o objetivo e disparar uma nova execução.",
            "Abra Diagnóstico para revisar achados, riscos, perguntas e etapas.",
            "Abra Arquivos para baixar saídas, manifesto, relatórios e bundle final.",
          ]}
        />
      </SectionCard>
    </div>
  );
}

function ProcessSection({
  project,
  payload,
  setPayload,
  isSubmitting,
  isReprocessing,
  canProcess,
  onProcess,
  onReprocess,
  versions,
}: {
  project: ProjectDetail;
  payload: ProcessPayload;
  setPayload: React.Dispatch<React.SetStateAction<ProcessPayload>>;
  isSubmitting: boolean;
  isReprocessing: boolean;
  canProcess: boolean;
  onProcess: () => Promise<void>;
  onReprocess: () => Promise<void>;
  versions: ProjectSummary[];
}) {
  return (
    <div className="space-y-6">
      <SectionCard
        kicker="Ação"
        title="Configuração essencial"
        description="Somente o que realmente muda o resultado final. Sem barras laterais, sem ruído técnico espalhado."
      >
        <div className="space-y-4">
          <QuickAction
            title="Versão funcional em PETG com brim"
            subtitle="Prioriza robustez para uso real."
            onClick={() =>
              setPayload((current) => ({
                ...current,
                target_material: "PETG",
                supports: "auto",
                objective_preset: "functional_part",
                material_preferences: { ...current.material_preferences, use_case: "functional" },
                transform_preferences: { ...current.transform_preferences, add_helper_base: true },
              }))
            }
          />
          <QuickAction
            title="Versão decorativa com foco em acabamento"
            subtitle="Mantém prioridade visual e material mais simples."
            onClick={() =>
              setPayload((current) => ({
                ...current,
                target_material: "PLA",
                objective_preset: "character_decorative",
                orientation_priority: "aesthetics",
                material_preferences: { ...current.material_preferences, use_case: "decorative" },
              }))
            }
          />
          <QuickAction
            title="Ajustar escala automaticamente à mesa"
            subtitle="Usa envelope de impressão como limite."
            onClick={() => setPayload((current) => ({ ...current, scale_mode: "fit_to_bed" }))}
          />
        </div>
      </SectionCard>

      <SectionCard
        kicker="Parâmetros"
        title="Definições principais"
        description="Fluxo linear, uma escolha por vez."
      >
        <div className="space-y-5">
          <FieldSelect
            label="Uso da peça"
            value={payload.material_preferences.use_case}
            onChange={(value) =>
              setPayload((current) => ({
                ...current,
                material_preferences: {
                  ...current.material_preferences,
                  use_case: value as ProcessPayload["material_preferences"]["use_case"],
                },
              }))
            }
            options={[
              { value: "unknown", label: "A decidir" },
              { value: "decorative", label: "Decorativa" },
              { value: "functional", label: "Funcional" },
              { value: "structural", label: "Estrutural" },
            ]}
          />
          <FieldSelect
            label="Supports"
            value={payload.supports}
            onChange={(value) => setPayload((current) => ({ ...current, supports: value as ProcessPayload["supports"] }))}
            options={[
              { value: "auto", label: "Automático" },
              { value: "disabled", label: "Desabilitado" },
              { value: "ask", label: "Perguntar" },
            ]}
          />
          <FieldSelect
            label="Escala"
            value={payload.scale_mode}
            onChange={(value) => setPayload((current) => ({ ...current, scale_mode: value as ProcessPayload["scale_mode"] }))}
            options={[
              { value: "keep", label: "Manter original" },
              { value: "fit_to_bed", label: "Ajustar à mesa" },
              { value: "normalize_units", label: "Normalizar unidade" },
              { value: "ask", label: "Perguntar" },
            ]}
          />
          <FieldSelect
            label="Preset da máquina"
            value={payload.objective_preset}
            onChange={(value) => setPayload((current) => ({ ...current, objective_preset: value }))}
            options={[
              { value: "balanced", label: "Equilibrado" },
              { value: "quality", label: "Qualidade" },
              { value: "speed", label: "Velocidade" },
              { value: "strength", label: "Resistência" },
              { value: "character_decorative", label: "Personagem decorativo" },
              { value: "functional_part", label: "Peça funcional" },
            ]}
          />
          <FieldSelect
            label="Prioridade de orientação"
            value={payload.orientation_priority}
            onChange={(value) =>
              setPayload((current) => ({ ...current, orientation_priority: value as ProcessPayload["orientation_priority"] }))
            }
            options={[
              { value: "support_economy", label: "Economia de suporte" },
              { value: "aesthetics", label: "Estética" },
              { value: "strength", label: "Resistência" },
              { value: "speed", label: "Velocidade" },
            ]}
          />
          <TextField
            label="Material alvo"
            placeholder="Ex.: PETG, ASA, TPU"
            value={payload.target_material ?? ""}
            onChange={(value) => setPayload((current) => ({ ...current, target_material: value || undefined }))}
          />
          <NumberField
            label="Nozzle alvo (mm)"
            value={payload.target_nozzle_mm}
            onChange={(value) => setPayload((current) => ({ ...current, target_nozzle_mm: value }))}
          />
        </div>
      </SectionCard>

      <SectionCard
        kicker="Validações"
        title="Ações automáticas"
        description="Ative ou desative os comportamentos padrão da execução."
      >
        <div className="space-y-4">
          <Toggle
            label="Correção de malha"
            detail="Recalcula normais e tenta reparar falhas simples."
            checked={payload.repair_mesh}
            onChange={(checked) => setPayload((current) => ({ ...current, repair_mesh: checked }))}
          />
          <Toggle
            label="Adaptar para Snapmaker U1"
            detail="Aplica envelope, suporte, aderência inicial e perfil seguro."
            checked={payload.adapt_to_snapmaker}
            onChange={(checked) => setPayload((current) => ({ ...current, adapt_to_snapmaker: checked }))}
          />
          <Toggle
            label="Converter de Bambu Lab"
            detail="Sanitiza 3MF, geometrias e parâmetros herdados do projeto de origem."
            checked={payload.convert_from_bambu}
            onChange={(checked) => setPayload((current) => ({ ...current, convert_from_bambu: checked }))}
          />
          <Toggle
            label="Hollowing"
            detail="Gera casca interna aproximada quando seguro."
            checked={payload.hollowing_preferences.enabled}
            onChange={(checked) =>
              setPayload((current) => ({
                ...current,
                hollowing: checked,
                hollowing_preferences: { ...current.hollowing_preferences, enabled: checked },
              }))
            }
          />
        </div>
      </SectionCard>

      <SectionCard
        kicker="Execução"
        title="Disparar nova rodada"
        description={`Projeto atual: ${project.name}. A nova execução preserva o histórico existente.`}
      >
        <div className="space-y-3">
          <button
            type="button"
            onClick={() => void onProcess()}
            disabled={isSubmitting || isReprocessing || !canProcess}
            className="w-full rounded-[1.4rem] bg-slate-950 px-5 py-5 text-lg font-semibold text-white transition hover:bg-slate-800 disabled:opacity-60"
          >
            {!canProcess ? "Sem permissão para processar" : isSubmitting ? "Iniciando..." : "Processar projeto (mesma versão)"}
          </button>
          <button
            type="button"
            onClick={() => void onReprocess()}
            disabled={isSubmitting || isReprocessing || !canProcess}
            className="w-full rounded-[1.4rem] bg-blue-700 px-5 py-4 text-base font-semibold text-white transition hover:bg-blue-800 disabled:opacity-60"
          >
            {isReprocessing ? "Criando nova versão..." : "Reprocessar → nova versão (sem re-upload)"}
          </button>
          <p className="text-center text-xs text-slate-500">
            "Nova versão" copia os arquivos originais e inicia o pipeline sem precisar enviar o arquivo novamente.
          </p>
        </div>
        {versions.length > 0 ? (
          <div className="mt-4 border-t border-slate-100 pt-4">
            <p className="mb-2 text-sm font-medium text-slate-700">Histórico de versões deste projeto</p>
            <ul className="space-y-1">
              {versions.map((v) => (
                <li key={v.id} className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2 text-sm">
                  <span className="font-mono text-slate-700">
                    v{String(v.version).padStart(3, "0")} <span className="ml-2 text-slate-400">{v.status}</span>
                  </span>
                  <a
                    href={`/projects/${v.id}`}
                    className="text-blue-600 hover:underline"
                  >
                    Abrir
                  </a>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </SectionCard>
    </div>
  );
}

function DiagnosticsSection({
  project,
  stages,
  previewUrl,
}: {
  project: ProjectDetail;
  stages: ProcessingStage[];
  previewUrl: string | null;
}) {
  return (
    <div className="space-y-6">
      <SectionCard
        kicker="Pipeline"
        title="Etapas de processamento"
        description="Acompanhamento completo do que já rodou e do que ainda depende de ação."
      >
        <StageList stages={stages} />
      </SectionCard>

      <SectionCard
        kicker="Prévia 3D"
        title="Arquivo base"
        description="A visualização técnica fica isolada nesta página para não competir com a ação principal."
      >
        <div className="space-y-4">
          <div className="overflow-hidden rounded-[1.5rem] border border-slate-900/10 bg-white/80 p-4">
            <ModelPreview url={previewUrl ?? undefined} />
          </div>
          {previewUrl ? (
            <a href={previewUrl} target="_blank" className="inline-flex rounded-full border border-slate-900/10 bg-white px-5 py-3 text-sm font-semibold text-slate-900">
              Abrir arquivo
            </a>
          ) : null}
        </div>
      </SectionCard>

      <SectionCard
        kicker="Achados"
        title="Leitura técnica"
        description="Tudo em sequência, sem painéis paralelos disputando atenção."
      >
        <ListBlock items={project.findings} empty="Nenhum achado registrado." />
      </SectionCard>

      <SectionCard
        kicker="Riscos"
        title="Pontos de atenção"
        description="Riscos, alertas e pontos que podem afetar a impressão."
      >
        <ListBlock items={project.risks} empty="Nenhum risco registrado." tone="warning" />
      </SectionCard>

      <SectionCard
        kicker="Perguntas"
        title="Pendências e bloqueios"
        description="Itens que ainda precisam de decisão ou confirmação."
      >
        <div className="space-y-4">
          <QuestionGroup title="Bloqueantes" items={project.blocking_questions} empty="Nenhum bloqueio formal no momento." tone="danger" />
          <QuestionGroup title="Pendentes" items={project.questions_pending} empty="Nenhuma pergunta pendente no momento." tone="warning" />
        </div>
      </SectionCard>
    </div>
  );
}

function FilesSection({
  project,
  siblingVersions,
  comparisonTarget,
  setComparisonTarget,
  comparison,
  onCompare,
  onBundle,
  bundlePath,
  onPrintFile,
  printFilePath,
}: {
  project: ProjectDetail;
  siblingVersions: ProjectSummary[];
  comparisonTarget: string;
  setComparisonTarget: (value: string) => void;
  comparison: ProjectCompareResponse | null;
  onCompare: () => Promise<void>;
  onBundle: () => Promise<void>;
  bundlePath: string | null;
  onPrintFile: () => Promise<void>;
  printFilePath: string | null;
}) {
  const outputFolder = `${project.storage_path}/export`;

  return (
    <div className="space-y-6">
      <SectionCard
        kicker="Saída"
        title="Arquivos finais"
        description="Área exclusiva para entrega, logs e rastreabilidade."
      >
        <div className="space-y-4">
          <InfoPanel label="Pasta da versão" value={project.storage_path} mono />
          <InfoPanel label="Pasta de export" value={outputFolder} mono />
          <ArtifactList items={project.artifacts} empty="Nenhum arquivo gerado ainda." />
        </div>
      </SectionCard>

      <SectionCard
        kicker="Documentação"
        title="Relatórios, logs e manifesto"
        description="Todos os artefatos de auditoria separados destaques da operação."
      >
        <div className="space-y-6">
          <ArtifactGroup title="Relatórios" items={project.reports} empty="Nenhum relatório disponível." />
          <ArtifactGroup title="Logs" items={project.logs} empty="Nenhum log disponível." />
          <ArtifactGroup
            title="Manifesto e bundles"
            items={[
              ...project.bundles,
              ...(project.manifest
                ? [{ label: "project_manifest.json", path: `${project.storage_path}/project_manifest.json`, kind: "manifest" }]
                : []),
            ]}
            empty="Nenhum manifesto ou bundle disponível."
          />
        </div>
      </SectionCard>

      <SectionCard
        kicker="Bundle"
        title="Pacote consolidado"
        description="Gera um ZIP único com exportações e documentos do projeto."
      >
        <div className="space-y-4">
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => void onPrintFile()}
              className="inline-flex rounded-full bg-slate-950 px-5 py-3 text-sm font-semibold text-white"
            >
              Localizar arquivo para imprimir
            </button>
            <button
              type="button"
              onClick={() => void onBundle()}
              className="inline-flex rounded-full border border-slate-900/10 bg-white px-5 py-3 text-sm font-semibold text-slate-900"
            >
              Gerar ZIP consolidado
            </button>
          </div>
          <div className="flex flex-wrap gap-3">
            {printFilePath ? (
              <a href={fileUrl(printFilePath)} target="_blank" className="inline-flex rounded-full border border-emerald-200 bg-emerald-50 px-5 py-3 text-sm font-semibold text-emerald-900">
                Abrir arquivo final
              </a>
            ) : null}
            {bundlePath ? (
              <a href={fileUrl(bundlePath)} target="_blank" className="inline-flex rounded-full border border-slate-900/10 bg-white px-5 py-3 text-sm font-semibold text-slate-900">
                Abrir ZIP
              </a>
            ) : null}
          </div>
        </div>
      </SectionCard>

      <SectionCard
        kicker="Comparação"
        title="Comparar versões"
        description="Escolha uma versão antiga e veja o delta em uma área dedicada."
      >
        <div className="space-y-4">
          <FieldSelect
            label="Versão para comparar"
            value={comparisonTarget}
            onChange={setComparisonTarget}
            options={[
              { value: "", label: siblingVersions.length ? "Selecione uma versão" : "Sem outras versões" },
              ...siblingVersions.map((item) => ({ value: item.id, label: `${item.id} · ${item.status}` })),
            ]}
          />
          <button type="button" onClick={() => void onCompare()} className="inline-flex rounded-full border border-slate-900/10 bg-white px-5 py-3 text-sm font-semibold text-slate-900">
            Comparar versões
          </button>
          {comparison ? <ComparisonCard comparison={comparison} /> : <EmptyBlock text="Selecione outra versão para comparar parâmetros e score." />}
        </div>
      </SectionCard>
    </div>
  );
}

function ImagesSection({ project }: { project: ProjectDetail }) {
  const images = collectProjectImages(project);

  return (
    <div className="space-y-6">
      <SectionCard
        kicker="Galeria"
        title="Todas as imagens do projeto"
        description="Aqui ficam reunidas todas as fotos e previews gerados para esta versão, sem esconder nenhuma imagem disponível."
      >
        {images.length === 0 ? (
          <EmptyBlock text="Nenhuma imagem disponível para este projeto ainda." />
        ) : (
          <div className="space-y-5">
            <div className="flex items-center justify-between gap-3">
              <p className="text-base leading-7 text-slate-600">
                {images.length} {images.length === 1 ? "imagem encontrada" : "imagens encontradas"} para este projeto.
              </p>
              <span className="pill">{images.length} fotos</span>
            </div>
            <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
              {images.map((image, index) => (
                <article
                  key={`${image.href}-${index}`}
                  className="overflow-hidden rounded-[1.5rem] border border-slate-900/10 bg-white shadow-[0_10px_30px_rgba(15,23,42,0.06)]"
                >
                  <a href={image.href} target="_blank" rel="noreferrer" className="block aspect-[4/3] bg-slate-100">
                    <img src={image.href} alt={`${project.name} - ${image.label}`} className="h-full w-full object-cover" loading="lazy" />
                  </a>
                  <div className="space-y-3 p-4">
                    <div>
                      <p className="info-label">Imagem {index + 1}</p>
                      <h3 className="mt-1 text-base font-semibold text-slate-950">{image.label}</h3>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <a
                        href={image.href}
                        target="_blank"
                        rel="noreferrer"
                        className="rounded-full border border-slate-900/10 bg-white px-4 py-2 text-sm font-semibold text-slate-900"
                      >
                        Abrir
                      </a>
                      <a
                        href={image.href}
                        download={image.filename}
                        className="rounded-full bg-slate-950 px-4 py-2 text-sm font-semibold text-white"
                      >
                        Baixar
                      </a>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </div>
        )}
      </SectionCard>
    </div>
  );
}

function SectionCard({
  kicker,
  title,
  description,
  children,
}: {
  kicker: string;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-[1.8rem] border border-slate-900/8 bg-white/68 px-7 py-7 shadow-[0_16px_48px_rgba(15,23,42,0.05)] backdrop-blur-[12px]">
      <p className="section-kicker">{kicker}</p>
      <h2 className="mt-3 text-3xl font-semibold text-slate-950 md:text-4xl">{title}</h2>
      <p className="mt-3 max-w-3xl text-base leading-7 text-slate-600">{description}</p>
      <div className="mt-6">{children}</div>
    </section>
  );
}

function MetricLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.1rem] bg-white/70 px-4 py-4">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">{label}</p>
      <p className="mt-2 text-xl font-semibold text-slate-950">{value}</p>
    </div>
  );
}

function ProgressBar({ progress, label }: { progress: number; label: string }) {
  const safe = Math.max(6, Math.min(100, progress));
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-base font-semibold text-slate-900">{label}</p>
        <p className="text-sm font-semibold text-slate-600">{safe}%</p>
      </div>
      <div className="h-3 overflow-hidden rounded-full bg-slate-900/10">
        <div className="h-full rounded-full bg-gradient-to-r from-orange-500 via-orange-400 to-amber-300" style={{ width: `${safe}%` }} />
      </div>
    </div>
  );
}

function InfoPanel({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="rounded-[1.2rem] border border-slate-900/10 bg-white/82 px-5 py-4">
      <p className="text-sm font-semibold text-slate-700">{label}</p>
      <p className={`mt-2 break-all text-base leading-7 text-slate-900 ${mono ? "font-mono text-sm md:text-base" : ""}`}>{value}</p>
    </div>
  );
}

function VerticalSteps({ steps }: { steps: string[] }) {
  return (
    <div className="space-y-3">
      {steps.map((step, index) => (
        <div key={step} className="flex gap-4 rounded-[1.2rem] border border-slate-900/10 bg-white/82 px-5 py-4">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-orange-100 text-sm font-semibold text-orange-700">
            {index + 1}
          </div>
          <p className="text-base leading-7 text-slate-700">{step}</p>
        </div>
      ))}
    </div>
  );
}

function QuickAction({
  title,
  subtitle,
  onClick,
}: {
  title: string;
  subtitle: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full rounded-[1.25rem] border border-slate-900/10 bg-white/82 px-5 py-4 text-left transition hover:border-orange-500/30"
    >
      <p className="text-base font-semibold text-slate-950">{title}</p>
      <p className="mt-1 text-sm leading-6 text-slate-600">{subtitle}</p>
    </button>
  );
}

function FieldSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="block space-y-2">
      <span className="text-base font-semibold text-slate-900">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-[1.2rem] border border-slate-900/10 bg-white px-4 py-4 text-base outline-none transition focus:border-orange-500"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function TextField({
  label,
  placeholder,
  value,
  onChange,
}: {
  label: string;
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block space-y-2">
      <span className="text-base font-semibold text-slate-900">{label}</span>
      <input
        className="w-full rounded-[1.2rem] border border-slate-900/10 bg-white px-4 py-4 text-base outline-none transition placeholder:text-slate-400 focus:border-orange-500"
        placeholder={placeholder}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function NumberField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="block space-y-2">
      <span className="text-base font-semibold text-slate-900">{label}</span>
      <input
        type="number"
        step="0.1"
        min="0.2"
        className="w-full rounded-[1.2rem] border border-slate-900/10 bg-white px-4 py-4 text-base outline-none transition focus:border-orange-500"
        value={value}
        onChange={(event) => onChange(Number(event.target.value || 0.4))}
      />
    </label>
  );
}

function Toggle({
  label,
  detail,
  checked,
  onChange,
}: {
  label: string;
  detail: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex items-start justify-between gap-4 rounded-[1.25rem] border border-slate-900/10 bg-white px-5 py-4">
      <div>
        <p className="text-base font-semibold text-slate-950">{label}</p>
        <p className="mt-1 text-sm leading-6 text-slate-600">{detail}</p>
      </div>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} className="mt-1 h-5 w-5 accent-orange-600" />
    </label>
  );
}

function QuestionGroup({
  title,
  items,
  empty,
  tone,
}: {
  title: string;
  items: ProjectQuestion[];
  empty: string;
  tone: "warning" | "danger";
}) {
  return (
    <div className="space-y-3">
      <p className="text-lg font-semibold text-slate-950">{title}</p>
      {items.length === 0 ? (
        <EmptyBlock text={empty} />
      ) : (
        items.map((question) => (
          <QuestionCard key={question.code} question={question} tone={tone} />
        ))
      )}
    </div>
  );
}

function QuestionCard({
  question,
  tone,
}: {
  question: ProjectQuestion;
  tone: "warning" | "danger";
}) {
  const toneClass =
    tone === "danger" ? "border-red-200 bg-red-50" : "border-orange-200 bg-orange-50";
  const badgeClass = tone === "danger" ? "text-red-700" : "text-orange-700";

  return (
    <div className={`rounded-[1.25rem] border px-5 py-4 ${toneClass}`}>
      <div className="flex items-start justify-between gap-3">
        <p className="text-base font-semibold text-slate-950">{question.question}</p>
        <span className={`rounded-full bg-white/80 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] ${badgeClass}`}>
          {question.severity}
        </span>
      </div>
      <p className="mt-2 text-sm leading-6 text-slate-700">{question.reason}</p>
    </div>
  );
}

function StageList({ stages }: { stages: ProcessingStage[] }) {
  if (stages.length === 0) {
    return <EmptyBlock text="As etapas aparecem quando o processamento é iniciado." />;
  }

  return (
    <div className="space-y-3">
      {stages.map((stage) => (
        <div key={stage.key} className="rounded-[1.2rem] border border-slate-900/10 bg-white/82 px-5 py-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-base font-semibold text-slate-950">{stage.label}</p>
            <span className="rounded-full border border-slate-900/10 bg-slate-50 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-slate-600">
              {stage.status}
            </span>
          </div>
          <p className="mt-2 text-sm leading-6 text-slate-600">{stage.message ?? "Sem detalhe adicional."}</p>
        </div>
      ))}
    </div>
  );
}

function ListBlock({
  items,
  empty,
  tone = "default",
}: {
  items: string[];
  empty: string;
  tone?: "default" | "warning";
}) {
  return (
    <div className={`rounded-[1.25rem] border px-5 py-4 ${tone === "warning" ? "border-amber-200 bg-amber-50" : "border-slate-900/10 bg-white/82"}`}>
      <ul className="space-y-3">
        {(items.length ? items : [empty]).map((item) => (
          <li key={item} className="text-base leading-7 text-slate-700">
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ArtifactGroup({
  title,
  items,
  empty,
}: {
  title: string;
  items: { label: string; path: string; kind: string }[];
  empty: string;
}) {
  return (
    <div className="space-y-3">
      <p className="text-lg font-semibold text-slate-950">{title}</p>
      <ArtifactList items={items} empty={empty} />
    </div>
  );
}

function ArtifactList({
  items,
  empty,
}: {
  items: { label: string; path: string; kind: string }[];
  empty: string;
}) {
  return items.length === 0 ? (
    <EmptyBlock text={empty} />
  ) : (
    <div className="space-y-3">
      {items.map((item) => (
        <a
          key={`${item.label}-${item.path}`}
          href={fileUrl(item.path)}
          target="_blank"
          className="flex items-center justify-between rounded-[1.2rem] border border-slate-900/10 bg-white/82 px-5 py-4 text-base font-semibold text-slate-900 transition hover:border-orange-500/30"
        >
          <span className="truncate">{item.label}</span>
          <span className="ml-4 text-sm font-semibold text-orange-700">abrir</span>
        </a>
      ))}
    </div>
  );
}

function ComparisonCard({ comparison }: { comparison: ProjectCompareResponse }) {
  return (
    <div className="rounded-[1.25rem] border border-slate-900/10 bg-white/82 px-5 py-4">
      <ul className="space-y-3">
        {comparison.summary.map((item) => (
          <li key={item} className="text-base leading-7 text-slate-700">
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function EmptyBlock({ text }: { text: string }) {
  return <div className="rounded-[1.2rem] border border-slate-900/10 bg-white/82 px-5 py-4 text-base leading-7 text-slate-600">{text}</div>;
}

function MessageBanner({ message }: { message: string }) {
  return (
    <div className="rounded-[1.4rem] border border-orange-200 bg-orange-50 px-5 py-4 text-base leading-7 text-orange-900">
      {message}
    </div>
  );
}

function selectMainPreview(project: ProjectDetail) {
  const preview = collectProjectImages(project)[0];
  return preview?.href ?? null;
}

function collectProjectImages(project: ProjectDetail) {
  const candidates = [
    ...(project.preview_url ? [{ label: "Imagem principal", path: project.preview_url }] : []),
    ...project.previews.map((item) => ({ label: item.label, path: item.path })),
  ];
  const seen = new Set<string>();
  return candidates
    .map((item, index) => {
      const href = fileUrl(item.path);
      if (!href || !/\.(png|jpe?g|webp)(\?.*)?$/i.test(href)) return null;
      if (seen.has(href)) return null;
      seen.add(href);
      const filename = href.split("/").pop()?.split("?")[0] || `imagem-${index + 1}.png`;
      return {
        href,
        label: item.label || `Imagem ${index + 1}`,
        filename,
      };
    })
    .filter((item): item is { href: string; label: string; filename: string } => Boolean(item));
}

function selectProcessingStages(stages: ProcessingStage[], status: string) {
  if (stages.length > 0) return stages;
  return [
    {
      key: "status",
      label: "Status geral",
      status: status === "completed" ? "completed" : status === "processing" ? "in_progress" : "pending",
      message: `Status atual: ${status}`,
    },
  ] as ProcessingStage[];
}
