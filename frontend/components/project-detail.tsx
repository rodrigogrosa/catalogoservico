"use client";

import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { ModelPreview } from "@/components/model-preview";
import { StatusBadge } from "@/components/status-badge";
import {
  compareProjects,
  fetchProject,
  fetchProjectBundle,
  fetchProjects,
  fileUrl,
  ProcessPayload,
  processProject,
  ProcessingStage,
  ProjectCompareResponse,
  ProjectDetail,
  ProjectSummary,
} from "@/lib/api";
import { PERMISSIONS } from "@/lib/permissions";

type Props = {
  project: ProjectDetail;
};

const defaultPayload: ProcessPayload = {
  repair_mesh: true,
  adapt_to_snapmaker: true,
  convert_from_bambu: true,
  scale_mode: "keep",
  unit_mode: "auto",
  hollowing: false,
  objective_preset: "balanced",
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

export function ProjectDetailView({ project }: Props) {
  const { can } = useAuth();
  const [currentProject, setCurrentProject] = useState<ProjectDetail>(project);
  const [payload, setPayload] = useState<ProcessPayload>(defaultPayload);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [allProjects, setAllProjects] = useState<ProjectSummary[]>([]);
  const [comparisonTarget, setComparisonTarget] = useState<string>("");
  const [comparison, setComparison] = useState<ProjectCompareResponse | null>(null);
  const [bundlePath, setBundlePath] = useState<string | null>(null);
  const previewHref = useMemo(() => fileUrl(currentProject.preview_url), [currentProject.preview_url]);
  const outputFolder = useMemo(() => `${currentProject.storage_path}/export`, [currentProject.storage_path]);
  const isProcessing = currentProject.status === "processing";
  const stage = deriveStage(currentProject.status);
  const galleryItems = useMemo(() => selectGalleryItems(currentProject.previews), [currentProject.previews]);
  const processStages = useMemo(
    () => selectProcessingStages(currentProject.processing_stages, currentProject.status),
    [currentProject.processing_stages, currentProject.status],
  );
  const siblingVersions = useMemo(
    () => allProjects.filter((item) => item.slug === currentProject.slug && item.id !== currentProject.id),
    [allProjects, currentProject.slug, currentProject.id],
  );
  const completedStages = processStages.filter((item) => item.status === "completed").length;
  const progressPercent = processStages.length ? Math.round((completedStages / processStages.length) * 100) : stage * 25;
  const mainGalleryItem = galleryItems[0] ?? null;
  const blockerCount = currentProject.blocking_questions.length;
  const pendingCount = currentProject.questions_pending.length;
  const riskCount = currentProject.risks.length;
  const printableLevel = currentProject.printable_score?.level ?? "medium";

  useEffect(() => {
    setCurrentProject(project);
  }, [project]);

  useEffect(() => {
    void fetchProjects().then(setAllProjects).catch(() => undefined);
  }, []);

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
      setMessage("Processamento iniciado. As barras abaixo serão atualizadas automaticamente.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao iniciar processamento.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleBundle() {
    try {
      const bundle = await fetchProjectBundle(currentProject.id);
      setBundlePath(bundle.path);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao gerar bundle.");
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

  return (
    <div className="space-y-6">
      <section className="panel hero-panel overflow-hidden p-6 md:p-8">
        <div className="grid gap-8 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="space-y-6">
            <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
              <div className="max-w-4xl">
                <p className="section-kicker">Projeto ativo</p>
                <h1 className="mt-3 text-4xl font-semibold leading-[1.02] text-slate-950 md:text-5xl">{currentProject.name}</h1>
                <p className="mt-4 text-lg leading-8 text-slate-700">
                  {currentProject.original_filename} · {currentProject.input_format.toUpperCase()} · origem {currentProject.source_ecosystem}
                </p>
              </div>
              <StatusBadge status={currentProject.status} />
            </div>

            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <HeroStat label="Versão" value={`v${String(currentProject.version).padStart(3, "0")}`} />
              <HeroStat label="Progresso" value={`${progressPercent}%`} />
              <HeroStat label="Risco" value={printableLevel} />
              <HeroStat label="Arquivos" value={`${currentProject.artifacts.length + currentProject.reports.length}`} />
            </div>

            <div className="card-surface p-5 md:p-6">
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                  <p className="section-kicker">Jornada simples</p>
                  <h2 className="mt-2 text-2xl font-semibold text-slate-950">Do upload ao arquivo pronto</h2>
                </div>
                <p className="text-base font-semibold text-slate-700">{currentProject.status.replaceAll("_", " ")}</p>
              </div>
              <div className="mt-5">
                <ProcessingIndicator stage={stage} status={currentProject.status} progressPercent={progressPercent} />
              </div>
              <div className="mt-6 grid gap-4 md:grid-cols-3">
                <JourneyStep
                  number="1"
                  title="Entender"
                  description="Veja rapidamente o nível de imprimibilidade e os bloqueios antes de converter."
                  badge={`${blockerCount} bloqueios`}
                />
                <JourneyStep
                  number="2"
                  title="Escolher"
                  description="Defina objetivo, material e suporte sem entrar em dezenas de parâmetros."
                  badge={`${pendingCount} decisões`}
                />
                <JourneyStep
                  number="3"
                  title="Entregar"
                  description="Processe e baixe o resultado final já organizado com relatórios e exportações."
                  badge={`${currentProject.artifacts.length} saídas`}
                />
              </div>
            </div>
          </div>

          <div className="rounded-[1.8rem] border border-slate-900/10 bg-white/90 p-4 md:p-5">
            <div className="flex items-center justify-between gap-3">
              <p className="section-kicker">Projeto ativo</p>
              <span className="pill">{galleryItems.length} imagens</span>
            </div>
            <div className="mt-4 overflow-hidden rounded-[1.4rem] border border-slate-900/10 bg-slate-100">
              {mainGalleryItem ? (
                <img src={fileUrl(mainGalleryItem.path)} alt={mainGalleryItem.label} className="aspect-[4/3] w-full object-cover" />
              ) : (
                <div className="flex aspect-[4/3] items-center justify-center text-base text-slate-500">Prévia visual em processamento.</div>
              )}
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <CompactInfo label="Pasta final" value={outputFolder} />
              <CompactInfo label="Tamanho enviado" value={`${(currentProject.size_bytes / 1024 / 1024).toFixed(2)} MB`} />
            </div>
            <div className="mt-4 flex flex-wrap gap-3">
              {can(PERMISSIONS.projectsDownload) ? (
                <button type="button" onClick={() => void handleBundle()} className="pill bg-slate-950 text-white">
                  Gerar ZIP final
                </button>
              ) : null}
              {bundlePath ? (
                <a href={fileUrl(bundlePath)} target="_blank" className="pill">
                  Abrir ZIP
                </a>
              ) : null}
            </div>
          </div>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[0.78fr_1.22fr]">
        <aside className="space-y-6">
          <div className="panel p-6 md:p-7">
            <p className="section-kicker">Passo 1</p>
            <h2 className="mt-2 text-3xl font-semibold text-slate-950">Escolha o objetivo</h2>
            <p className="mt-3 text-base leading-7 text-slate-600">
              Use um preset rápido para não precisar preencher tudo manualmente. Depois refine apenas o essencial.
            </p>

            <div className="mt-5 grid gap-3">
              <QuickAction
                title="Versão funcional PETG + brim"
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
                title="Versão decorativa qualidade"
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
                title="Ajustar à mesa automaticamente"
                onClick={() => setPayload((current) => ({ ...current, scale_mode: "fit_to_bed" }))}
              />
            </div>

            <div className="mt-6 space-y-4">
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
                label="Estratégia de cor"
                value={payload.color_preferences.strategy}
                onChange={(value) =>
                  setPayload((current) => ({
                    ...current,
                    color_preferences: {
                      ...current.color_preferences,
                      strategy: value as ProcessPayload["color_preferences"]["strategy"],
                    },
                  }))
                }
                options={[
                  { value: "undecided", label: "Perguntar" },
                  { value: "multicolor", label: "Multicolor" },
                  { value: "split_parts", label: "Partes separadas" },
                  { value: "paint_after", label: "Pintura posterior" },
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
              <Toggle
                label="Correção de malha"
                detail="Recalcula normais e tenta reparar falhas simples."
                checked={payload.repair_mesh}
                onChange={(checked) => setPayload((current) => ({ ...current, repair_mesh: checked }))}
              />
              <Toggle
                label="Adaptar para Snapmaker U1"
                detail="Aplica envelope, suporte, primeira camada e perfil seguro."
                checked={payload.adapt_to_snapmaker}
                onChange={(checked) => setPayload((current) => ({ ...current, adapt_to_snapmaker: checked }))}
              />
              <Toggle
                label="Converter de Bambu Lab"
                detail="Sanitiza 3MF, geometria, layout e parâmetros herdados."
                checked={payload.convert_from_bambu}
                onChange={(checked) => setPayload((current) => ({ ...current, convert_from_bambu: checked }))}
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
              <label className="block space-y-2">
                <span className="text-base font-semibold text-slate-900">Nozzle alvo (mm)</span>
                <input
                  type="number"
                  step="0.1"
                  min="0.2"
                  className="w-full rounded-[1.2rem] border border-slate-900/10 bg-white px-4 py-4 text-base outline-none transition placeholder:text-slate-400 focus:border-orange-500"
                  value={payload.target_nozzle_mm}
                  onChange={(event) => setPayload((current) => ({ ...current, target_nozzle_mm: Number(event.target.value || 0.4) }))}
                />
              </label>
              <label className="block space-y-2">
                <span className="text-base font-semibold text-slate-900">Material alvo</span>
                <input
                  className="w-full rounded-[1.2rem] border border-slate-900/10 bg-white px-4 py-4 text-base outline-none transition placeholder:text-slate-400 focus:border-orange-500"
                  placeholder="Ex.: PETG, ASA, TPU"
                  value={payload.target_material ?? ""}
                  onChange={(event) => setPayload((current) => ({ ...current, target_material: event.target.value || undefined }))}
                />
              </label>
            </div>

            <button
              type="button"
              onClick={() => void handleProcess()}
              disabled={isSubmitting || !can(PERMISSIONS.projectsProcess)}
              className="mt-6 w-full rounded-[1.35rem] bg-slate-950 px-5 py-4 text-lg font-semibold text-white transition hover:bg-slate-800 disabled:opacity-60"
            >
              {!can(PERMISSIONS.projectsProcess) ? "Sem permissão para processar" : isSubmitting ? "Iniciando..." : "Processar projeto"}
            </button>
            {message ? <p className="mt-4 rounded-2xl bg-orange-50 px-4 py-3 text-base text-orange-800">{message}</p> : null}
          </div>

          <div className="panel p-6 md:p-7">
            <p className="section-kicker">Passo 2</p>
            <h2 className="mt-2 text-3xl font-semibold text-slate-950">Próximas decisões</h2>
            <div className="mt-5 space-y-4">
              <DecisionCard
                title="Bloqueios"
                count={blockerCount}
                tone={blockerCount ? "danger" : "success"}
                description={blockerCount ? "Existem perguntas que travam a saída final." : "Nenhum bloqueio formal no momento."}
              />
              <DecisionCard
                title="Pendências"
                count={pendingCount}
                tone={pendingCount ? "warning" : "success"}
                description={pendingCount ? "Ainda há escolhas recomendadas antes da exportação." : "Nenhuma pergunta pendente registrada."}
              />
              <DecisionCard
                title="Riscos"
                count={riskCount}
                tone={riskCount ? "warning" : "success"}
                description={riskCount ? "Revise os riscos antes de imprimir." : "Sem riscos relevantes registrados agora."}
              />
            </div>
          </div>

          <div className="panel p-6 md:p-7">
            <p className="section-kicker">Passo 3</p>
            <h2 className="mt-2 text-3xl font-semibold text-slate-950">Acompanhe a execução</h2>
            <div className="mt-5">
              <StageList stages={processStages} />
            </div>
          </div>
        </aside>

        <main className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-[0.95fr_1.05fr]">
            <SectionCard title="Resumo rápido">
              <PrintableScoreCard project={currentProject} />
            </SectionCard>
            <SectionCard title="Receber os arquivos finais">
              <div className="space-y-4">
                <FolderBlock label="Pasta da versão" value={currentProject.storage_path} />
                <FolderBlock label="Arquivos novos" value={outputFolder} highlight />
                <ArtifactList items={[...currentProject.artifacts, ...currentProject.reports, ...currentProject.bundles]} empty="Nenhum arquivo final disponível ainda." />
              </div>
            </SectionCard>
          </div>

          <div className="panel p-6 md:p-7">
            <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
              <div>
                <p className="section-kicker">Visual</p>
                <h2 className="mt-2 text-3xl font-semibold text-slate-950">Galeria do projeto</h2>
              </div>
              <span className="pill">{galleryItems.length} imagens</span>
            </div>
            <div className="mt-6">
              <PreviewGallery items={galleryItems} />
            </div>
          </div>

          <details className="panel group p-6 md:p-7" open>
            <summary className="cursor-pointer list-none">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="section-kicker">Detalhes</p>
                  <h2 className="mt-2 text-3xl font-semibold text-slate-950">Perguntas, riscos e preview 3D</h2>
                </div>
                <span className="pill">abrir ou fechar</span>
              </div>
            </summary>
            <div className="mt-6 grid gap-6 lg:grid-cols-[1.08fr_0.92fr]">
              <div className="space-y-6">
                <div className="rounded-[1.5rem] border border-slate-900/10 bg-white/80 p-5">
                  <div className="flex items-center justify-between gap-4">
                    <h3 className="text-2xl font-semibold text-slate-950">Preview 3D</h3>
                    {previewHref ? <a href={previewHref} target="_blank" className="pill">Abrir arquivo</a> : null}
                  </div>
                  <div className="mt-5">
                    <ModelPreview url={previewHref} />
                  </div>
                </div>
                <SectionCard title="Perguntas bloqueantes">
                  <QuestionList items={currentProject.blocking_questions} empty="Nenhum bloqueio formal no momento." tone="danger" />
                </SectionCard>
                <SectionCard title="Perguntas pendentes">
                  <QuestionList items={currentProject.questions_pending} empty="Nenhuma pergunta pendente no momento." tone="warning" />
                </SectionCard>
              </div>

              <div className="space-y-6">
                <SectionCard title="Achados">
                  <ListBlock items={currentProject.findings} empty="Nenhum achado registrado." />
                </SectionCard>
                <SectionCard title="Riscos">
                  <ListBlock items={currentProject.risks} empty="Nenhum risco registrado." tone="warning" />
                </SectionCard>
              </div>
            </div>
          </details>

          <details className="panel p-6 md:p-7">
            <summary className="cursor-pointer list-none">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="section-kicker">Técnico</p>
                  <h2 className="mt-2 text-3xl font-semibold text-slate-950">Arquivos, equivalência e métricas</h2>
                </div>
                <span className="pill">uso avançado</span>
              </div>
            </summary>
            <div className="mt-6 space-y-6">
              <div className="grid gap-6 lg:grid-cols-2">
                <SectionCard title="Arquivos de entrada">
                  <InputFileList items={currentProject.input_files} />
                </SectionCard>
                <SectionCard title="Equivalência Bambu → Snapmaker">
                  <ParameterEquivalenceTable items={currentProject.bambu_parameter_equivalence} />
                </SectionCard>
              </div>

              <div className="grid gap-6 lg:grid-cols-3">
                <SectionCard title="Relatórios">
                  <ArtifactList items={currentProject.reports} empty="Nenhum relatório disponível." />
                </SectionCard>
                <SectionCard title="Logs">
                  <ArtifactList items={currentProject.logs} empty="Nenhum log disponível." />
                </SectionCard>
                <SectionCard title="Manifesto e bundles">
                  <ArtifactList items={[...currentProject.bundles, ...(currentProject.manifest ? [{ label: "project_manifest.json", path: `${currentProject.storage_path}/project_manifest.json`, kind: "manifest" }] : [])].filter(Boolean) as { label: string; path: string; kind: string }[]} empty="Nenhum bundle disponível." />
                </SectionCard>
              </div>

              <div className="grid gap-6 lg:grid-cols-[0.95fr_1.05fr]">
                <SectionCard title="Comparar versões">
                  <div className="space-y-4">
                    <FieldSelect
                      label="Versão para comparar"
                      value={comparisonTarget}
                      onChange={setComparisonTarget}
                      options={[
                        { value: "", label: siblingVersions.length ? "Selecione" : "Sem outras versões" },
                        ...siblingVersions.map((item) => ({
                          value: item.id,
                          label: `${item.id} · ${item.status}`,
                        })),
                      ]}
                    />
                    <button type="button" onClick={() => void handleCompare()} className="pill bg-white">
                      Comparar
                    </button>
                    {comparison ? <ComparisonCard comparison={comparison} /> : <p className="text-base text-slate-600">Selecione outra versão para comparar parâmetros e score.</p>}
                  </div>
                </SectionCard>
                <SectionCard title="Métricas por etapa">
                  <StageMetricList items={currentProject.stage_metrics} />
                </SectionCard>
              </div>
            </div>
          </details>
        </main>
      </div>
    </div>
  );
}

function HeroStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.4rem] border border-slate-900/10 bg-white/80 p-5">
      <p className="text-sm uppercase tracking-[0.18em] text-slate-500">{label}</p>
      <p className="mt-3 text-2xl font-semibold text-slate-950">{value}</p>
    </div>
  );
}

function JourneyStep({
  number,
  title,
  description,
  badge,
}: {
  number: string;
  title: string;
  description: string;
  badge: string;
}) {
  return (
    <div className="rounded-[1.35rem] border border-slate-900/10 bg-white/80 p-5">
      <div className="flex items-center justify-between gap-3">
        <span className="flex h-9 w-9 items-center justify-center rounded-full bg-orange-100 text-sm font-semibold text-orange-700">
          {number}
        </span>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-slate-600">
          {badge}
        </span>
      </div>
      <p className="mt-4 text-xl font-semibold text-slate-950">{title}</p>
      <p className="mt-2 text-base leading-7 text-slate-600">{description}</p>
    </div>
  );
}

function CompactInfo({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.15rem] border border-slate-900/10 bg-white/80 p-4">
      <p className="text-sm font-semibold text-slate-700">{label}</p>
      <p className="mt-2 break-all text-sm leading-6 text-slate-900">{value}</p>
    </div>
  );
}

function DecisionCard({
  title,
  count,
  description,
  tone,
}: {
  title: string;
  count: number;
  description: string;
  tone: "success" | "warning" | "danger";
}) {
  const toneClass =
    tone === "danger"
      ? "border-red-200 bg-red-50 text-red-900"
      : tone === "warning"
        ? "border-orange-200 bg-orange-50 text-orange-900"
        : "border-emerald-200 bg-emerald-50 text-emerald-900";
  return (
    <div className={`rounded-[1.25rem] border p-4 ${toneClass}`}>
      <div className="flex items-center justify-between gap-3">
        <p className="text-base font-semibold">{title}</p>
        <span className="text-2xl font-semibold">{count}</span>
      </div>
      <p className="mt-2 text-sm leading-6 opacity-90">{description}</p>
    </div>
  );
}

function FolderBlock({ label, value, highlight = false }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className={`rounded-[1.25rem] border p-4 ${highlight ? "border-orange-200 bg-orange-50" : "border-slate-900/10 bg-white/80"}`}>
      <p className="text-sm font-semibold text-slate-700">{label}</p>
      <p className={`mt-2 break-all font-mono text-sm leading-6 ${highlight ? "text-orange-800" : "text-slate-900"}`}>{value}</p>
    </div>
  );
}

function QuestionList({
  items,
  empty,
  tone,
}: {
  items: ProjectDetail["questions_pending"];
  empty: string;
  tone: "warning" | "danger";
}) {
  if (items.length === 0) {
    return <div className="card-surface p-5 text-base leading-7 text-slate-600">{empty}</div>;
  }

  const cardClass =
    tone === "danger"
      ? "border-red-200 bg-red-50"
      : "border-orange-200 bg-orange-50";
  const titleClass = tone === "danger" ? "text-red-950" : "text-orange-950";
  const textClass = tone === "danger" ? "text-red-900/80" : "text-orange-900/80";
  const badgeClass = tone === "danger" ? "text-red-700" : "text-orange-700";

  return (
    <div className="space-y-3">
      {items.map((question) => (
        <div key={question.code} className={`rounded-[1.4rem] border p-5 ${cardClass}`}>
          <div className="flex items-start justify-between gap-3">
            <p className={`text-lg font-semibold ${titleClass}`}>{question.question}</p>
            <span className={`rounded-full bg-white/80 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] ${badgeClass}`}>
              {question.severity}
            </span>
          </div>
          <p className={`mt-3 text-base leading-7 ${textClass}`}>{question.reason}</p>
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
    <div className={`rounded-[1.35rem] border p-5 ${tone === "warning" ? "border-amber-200 bg-amber-50" : "border-slate-900/10 bg-white/80"}`}>
      <ul className="space-y-3 text-base leading-7">
        {(items.length ? items : [empty]).map((item) => (
          <li key={item} className="text-slate-800">
            {item}
          </li>
        ))}
      </ul>
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
  return (
    <div className="space-y-3">
      {items.length === 0 ? (
        <p className="rounded-[1.2rem] bg-white/80 px-4 py-4 text-base text-slate-600">{empty}</p>
      ) : (
        items.map((item) => (
          <a
            key={`${item.label}-${item.path}`}
            href={fileUrl(item.path)}
            target="_blank"
            className="flex items-center justify-between rounded-[1.2rem] border border-slate-900/10 bg-white/80 px-4 py-4 text-base font-semibold text-slate-900 transition hover:border-orange-500/30 hover:bg-white"
          >
            <span className="truncate">{item.label}</span>
            <span className="ml-3 text-orange-700">abrir</span>
          </a>
        ))
      )}
    </div>
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
    <label className="flex items-start justify-between gap-4 rounded-[1.25rem] border border-slate-900/10 bg-white px-4 py-4">
      <div>
        <p className="text-base font-semibold text-slate-950">{label}</p>
        <p className="mt-1 text-sm leading-6 text-slate-600">{detail}</p>
      </div>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} className="mt-1 h-5 w-5 accent-orange-600" />
    </label>
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

function SectionCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="panel p-6 md:p-7">
      <h2 className="text-3xl font-semibold text-slate-950">{title}</h2>
      <div className="mt-5">{children}</div>
    </div>
  );
}

function QuickAction({ title, onClick }: { title: string; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className="rounded-[1.15rem] border border-slate-900/10 bg-white/80 px-4 py-3 text-left text-sm font-semibold text-slate-800 transition hover:border-orange-500/30">
      {title}
    </button>
  );
}

function ProcessingIndicator({
  stage,
  status,
  progressPercent,
}: {
  stage: number;
  status: string;
  progressPercent: number;
}) {
  const labels = ["Recebido", "Analisando", "Processando", "Concluído"];
  const effectiveProgress = Math.max(12, Math.min(100, progressPercent || stage * 25));

  return (
    <div className="space-y-4">
      <div className="h-4 overflow-hidden rounded-full bg-slate-900/10">
        <div
          className={`h-full rounded-full bg-gradient-to-r from-orange-500 via-orange-400 to-amber-300 transition-all ${status === "processing" ? "animate-pulse" : ""}`}
          style={{ width: `${effectiveProgress}%` }}
        />
      </div>
      <div className="grid grid-cols-2 gap-3 text-sm font-semibold text-slate-500 md:grid-cols-4">
        {labels.map((label, index) => (
          <div key={label} className={`rounded-full px-3 py-2 ${index < stage ? "bg-white text-slate-900" : "bg-white/50 text-slate-500"}`}>
            {label}
          </div>
        ))}
      </div>
    </div>
  );
}

function StageList({ stages }: { stages: ProcessingStage[] }) {
  if (stages.length === 0) {
    return <p className="text-base text-slate-600">As etapas detalhadas aparecem quando o processamento é iniciado.</p>;
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {stages.map((stage) => {
        const tone =
          stage.status === "completed"
            ? "from-emerald-500 to-emerald-300"
            : stage.status === "failed"
              ? "from-red-500 to-red-300"
              : stage.status === "skipped"
                ? "from-slate-400 to-slate-300"
                : stage.status === "in_progress"
                  ? "from-orange-500 to-amber-300"
                  : "from-slate-300 to-slate-200";
        const width =
          stage.status === "completed"
            ? "100%"
            : stage.status === "failed"
              ? "100%"
              : stage.status === "skipped"
                ? "100%"
                : stage.status === "in_progress"
                  ? "62%"
                  : "12%";

        return (
          <div key={stage.key} className="rounded-[1.45rem] border border-slate-900/10 bg-white/80 p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-lg font-semibold text-slate-950">{stage.label}</p>
                <p className="mt-1 text-sm uppercase tracking-[0.18em] text-slate-500">{renderStageStatus(stage.status)}</p>
              </div>
            </div>
            <div className="mt-4 h-3 overflow-hidden rounded-full bg-slate-900/10">
              <div
                className={`h-full rounded-full bg-gradient-to-r ${tone} transition-all ${stage.status === "in_progress" ? "animate-pulse" : ""}`}
                style={{ width }}
              />
            </div>
            {stage.message ? <p className="mt-4 text-base leading-7 text-slate-700">{stage.message}</p> : null}
          </div>
        );
      })}
    </div>
  );
}

function PreviewGallery({ items }: { items: { label: string; path: string; kind: string }[] }) {
  if (items.length === 0) {
    return <p className="text-base text-slate-600">Nenhuma imagem disponível ainda para este projeto.</p>;
  }

  return (
    <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
      {items.map((item) => (
        <a
          key={`${item.label}-${item.path}`}
          href={fileUrl(item.path)}
          target="_blank"
          className="group overflow-hidden rounded-[1.6rem] border border-slate-900/10 bg-white/80 transition hover:-translate-y-0.5 hover:shadow-lg hover:shadow-orange-100"
        >
          <div className="overflow-hidden">
            <img src={fileUrl(item.path)} alt={item.label} className="aspect-[4/3] w-full object-cover transition duration-300 group-hover:scale-[1.02]" />
          </div>
          <div className="border-t border-slate-900/10 px-4 py-4">
            <p className="text-base font-semibold text-slate-900">{item.label}</p>
          </div>
        </a>
      ))}
    </div>
  );
}

function PrintableScoreCard({ project }: { project: ProjectDetail }) {
  const score = project.printable_score;
  if (!score) {
    return <p className="text-base text-slate-600">Score ainda não disponível.</p>;
  }
  return (
    <div className="space-y-4">
      <div className="rounded-[1.35rem] border border-slate-900/10 bg-white/80 p-5">
        <p className="text-sm uppercase tracking-[0.18em] text-slate-500">Pontuação</p>
        <p className="mt-3 text-5xl font-semibold text-slate-950">{score.score}</p>
        <p className="mt-2 text-base font-semibold text-slate-700">Risco {score.level}</p>
      </div>
      <ListBlock items={score.blockers} empty="Sem bloqueantes formais." tone="warning" />
      <ListBlock items={score.recommendations} empty="Sem recomendações adicionais." />
    </div>
  );
}

function ComparisonCard({ comparison }: { comparison: ProjectCompareResponse }) {
  return (
    <div className="space-y-3">
      <ListBlock items={comparison.summary} empty="Sem resumo." />
      {comparison.artifacts_added.length > 0 ? <ArtifactList items={comparison.artifacts_added} empty="Sem novos artefatos." /> : null}
    </div>
  );
}

function InputFileList({ items }: { items: ProjectDetail["input_files"] }) {
  if (items.length === 0) {
    return <p className="text-base text-slate-600">Nenhum arquivo de entrada registrado.</p>;
  }
  return (
    <div className="space-y-3">
      {items.map((item) => (
        <div key={item.path} className="rounded-[1.2rem] border border-slate-900/10 bg-white/80 p-4">
          <p className="text-base font-semibold text-slate-900">{item.name}</p>
          <p className="mt-1 text-sm text-slate-600">{item.role} · {item.suffix} · {(item.size_bytes / 1024).toFixed(1)} KB</p>
        </div>
      ))}
    </div>
  );
}

function ParameterEquivalenceTable({ items }: { items: ProjectDetail["bambu_parameter_equivalence"] }) {
  if (items.length === 0) {
    return <p className="text-base text-slate-600">Nenhuma equivalência formal registrada para este projeto.</p>;
  }
  return (
    <div className="space-y-3">
      {items.slice(0, 12).map((item) => (
        <div key={`${item.parameter}-${item.status}`} className="rounded-[1.2rem] border border-slate-900/10 bg-white/80 p-4">
          <p className="text-base font-semibold text-slate-900">{item.parameter}</p>
          <p className="mt-1 text-sm text-slate-600">{item.status}</p>
          {item.note ? <p className="mt-2 text-sm leading-6 text-slate-700">{item.note}</p> : null}
        </div>
      ))}
    </div>
  );
}

function StageMetricList({ items }: { items: ProjectDetail["stage_metrics"] }) {
  if (items.length === 0) {
    return <p className="text-base text-slate-600">Nenhuma métrica registrada ainda.</p>;
  }
  return (
    <div className="space-y-3">
      {items.map((item, index) => (
        <div key={`${item.stage_key}-${index}`} className="rounded-[1.2rem] border border-slate-900/10 bg-white/80 p-4">
          <div className="flex items-center justify-between gap-4">
            <p className="text-base font-semibold text-slate-900">{item.stage_key}</p>
            <p className="text-sm text-slate-600">{item.duration_ms.toFixed(0)} ms</p>
          </div>
          <p className="mt-1 text-sm text-slate-600">{item.status}</p>
        </div>
      ))}
    </div>
  );
}

function deriveStage(status: string): number {
  switch (status) {
    case "uploaded":
      return 1;
    case "analyzed":
      return 2;
    case "processing":
      return 3;
    case "completed":
    case "awaiting_user":
      return 4;
    case "failed":
      return 1;
    default:
      return 1;
  }
}

function selectGalleryItems(items: { label: string; path: string; kind: string }[]) {
  return items.filter((item) => /\.(png|jpg|jpeg|webp)$/i.test(item.path)).slice(0, 12);
}

function selectProcessingStages(stages: ProcessingStage[], status: string): ProcessingStage[] {
  if (stages.length > 0) return stages;
  return [
    {
      key: "status",
      label: "Estado atual",
      status: status === "processing" ? "in_progress" : status === "completed" ? "completed" : "pending",
      message: "O backend ainda não publicou as etapas detalhadas para esta execução.",
    } as ProcessingStage,
  ];
}

function renderStageStatus(status: ProcessingStage["status"]) {
  switch (status) {
    case "completed":
      return "concluída";
    case "failed":
      return "falhou";
    case "skipped":
      return "pulada";
    case "in_progress":
      return "em andamento";
    default:
      return "pendente";
  }
}
