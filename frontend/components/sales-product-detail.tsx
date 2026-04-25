"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import {
  buildPublicationDraft,
  fetchStores,
  fileUrl,
  updateStore,
  type ArtifactReference,
  type MarketplaceAttribute,
  type ProductPublishDraft,
  type ProjectDetail,
  type StoreIntegration,
} from "@/lib/api";
import { PERMISSIONS } from "@/lib/permissions";

type Props = {
  project: ProjectDetail;
};

export function SalesProductDetail({ project }: Props) {
  const { can } = useAuth();
  const sales = project.sales_profile;
  const [margin, setMargin] = useState(sales?.default_margin_percent ?? 50);
  const [resellerMargin, setResellerMargin] = useState(sales?.reseller_margin_percent ?? 18);
  const [copied, setCopied] = useState<string | null>(null);
  const [stores, setStores] = useState<StoreIntegration[]>([]);
  const [storesLoading, setStoresLoading] = useState(true);
  const [storesError, setStoresError] = useState<string | null>(null);
  const [selectedStoreId, setSelectedStoreId] = useState("");
  const [draft, setDraft] = useState<ProductPublishDraft | null>(null);
  const [draftLoading, setDraftLoading] = useState(false);
  const [draftError, setDraftError] = useState<string | null>(null);
  const [saveStoreLoading, setSaveStoreLoading] = useState(false);
  const [storeSettingsMessage, setStoreSettingsMessage] = useState<string | null>(null);
  const [categoryId, setCategoryId] = useState("");
  const imageUrl = fileUrl(project.preview_url);
  const hasImagePreview = imageUrl ? /\.(png|jpe?g|webp)(\?.*)?$/i.test(imageUrl) : false;
  const channels = useMemo(() => sales?.marketplace_attributes ?? [], [sales]);
  const adPhotos = useMemo(() => collectAdPhotos(project), [project]);
  const primary = channels[0];
  const publicationStores = useMemo(
    () => stores.filter((store) => store.status === "configured" || store.status === "needs_credentials" || store.status === "draft"),
    [stores],
  );
  const selectedStore = publicationStores.find((store) => store.id === selectedStoreId) ?? null;

  useEffect(() => {
    setCategoryId(typeof selectedStore?.settings?.category_id === "string" ? selectedStore.settings.category_id : "");
    setStoreSettingsMessage(null);
  }, [selectedStoreId, selectedStore]);

  useEffect(() => {
    let cancelled = false;
    async function loadStores() {
      if (!can(PERMISSIONS.storesView)) {
        setStoresLoading(false);
        return;
      }
      try {
        const result = await fetchStores();
        if (cancelled) return;
        setStores(result);
        setSelectedStoreId((current) => current || result[0]?.id || "");
        setStoresError(null);
      } catch (error) {
        if (cancelled) return;
        setStoresError(error instanceof Error ? error.message : "Falha ao carregar lojas do usuário.");
      } finally {
        if (!cancelled) setStoresLoading(false);
      }
    }
    void loadStores();
    return () => {
      cancelled = true;
    };
  }, [can]);

  if (!sales) {
    return (
      <section className="panel p-6 md:p-8">
        <p className="section-kicker">Venda</p>
        <h1 className="mt-3 text-3xl font-semibold text-slate-950">Este projeto ainda não tem ficha comercial.</h1>
      </section>
    );
  }

  const salePrice = sales.estimated_base_cost_brl * (1 + margin / 100);
  const resellerPrice = sales.estimated_base_cost_brl * (1 + resellerMargin / 100);

  async function copyText(label: string, text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(label);
      window.setTimeout(() => setCopied(null), 1800);
    } catch {
      setCopied("Não foi possível copiar");
    }
  }

  async function prepareStoreDraft() {
    if (!selectedStoreId) return;
    setDraftLoading(true);
    setDraftError(null);
    try {
      const result = await buildPublicationDraft(selectedStoreId, project.id);
      setDraft(result);
    } catch (error) {
      setDraftError(error instanceof Error ? error.message : "Falha ao preparar cadastro para a loja.");
      setDraft(null);
    } finally {
      setDraftLoading(false);
    }
  }

  async function saveStoreSettings() {
    if (!selectedStore) return;
    setSaveStoreLoading(true);
    setStoreSettingsMessage(null);
    try {
      const updated = await updateStore(selectedStore.id, {
        settings: {
          ...(selectedStore.settings ?? {}),
          category_id: categoryId.trim(),
        },
      });
      setStores((current) => current.map((store) => (store.id === updated.id ? updated : store)));
      setStoreSettingsMessage("Configuração da loja atualizada.");
      setDraft(null);
      setDraftError(null);
    } catch (error) {
      setStoreSettingsMessage(error instanceof Error ? error.message : "Falha ao salvar categoria da loja.");
    } finally {
      setSaveStoreLoading(false);
    }
  }

  async function publishNow() {
    if (!selectedStoreId) return;
    setDraftLoading(true);
    setDraftError(null);
    try {
      const result = await buildPublicationDraft(selectedStoreId, project.id, { mode: "publish", stock: 1 });
      setDraft(result);
    } catch (error) {
      setDraftError(error instanceof Error ? error.message : "Falha ao publicar produto.");
    } finally {
      setDraftLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <section className="panel overflow-hidden p-0">
        <div className="grid gap-0 lg:grid-cols-[0.95fr_1.05fr]">
          <div className="min-h-[340px] bg-slate-100">
            {hasImagePreview ? (
              <img src={imageUrl} alt={`Imagem principal de ${project.name}`} className="h-full min-h-[340px] w-full object-cover" />
            ) : (
              <div className="flex h-full min-h-[340px] items-center justify-center p-8 text-center text-base text-slate-500">
                Sem imagem principal disponível
              </div>
            )}
          </div>

          <div className="p-6 md:p-8">
            <p className="section-kicker">Produto para venda</p>
            <h1 className="mt-3 text-4xl font-semibold leading-tight text-slate-950">{project.name}</h1>
            <p className="mt-4 text-lg leading-8 text-slate-700">
              {primary?.short_description ?? primary?.description ?? "Produto impresso em 3D sob demanda, com ficha comercial e precificação em Real brasileiro."}
            </p>

            <div className="mt-6 grid gap-3 sm:grid-cols-3">
              <Metric label="Preço sugerido" value={currency(sales.suggested_price_50_margin_brl)} strong />
              <Metric label="Custo base" value={currency(sales.estimated_base_cost_brl)} />
              <Metric label="Revendedor" value={currency(sales.reseller_price_brl)} />
            </div>

            <div className="mt-6 grid gap-3 text-sm text-slate-600 sm:grid-cols-3">
              <InfoPill label="Material" value={materialFromAssumptions(sales.assumptions)} />
              <InfoPill label="Produção" value={`${sales.estimated_material_g}g · ${sales.estimated_print_hours}h`} />
              <InfoPill label="Versão" value={`v${String(project.version).padStart(3, "0")} · ${project.input_format.toUpperCase()}`} />
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-5 lg:grid-cols-[0.85fr_1.15fr]">
        <div className="panel p-5 md:p-6">
          <p className="section-kicker">Precificação</p>
          <h2 className="mt-2 text-2xl font-semibold text-slate-950">Simulador de venda</h2>
          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            <Metric label={`Venda com ${margin}%`} value={currency(salePrice)} strong />
            <Metric label={`Revenda com ${resellerMargin}%`} value={currency(resellerPrice)} />
          </div>
          <div className="mt-5 space-y-4">
            <MarginInput label="Margem de lucro desejada" value={margin} onChange={setMargin} />
            <MarginInput label="Margem para revendedor" value={resellerMargin} onChange={setResellerMargin} />
          </div>
          <ul className="mt-5 space-y-2 text-sm leading-6 text-slate-600">
            {sales.assumptions.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>

        <div className="panel p-5 md:p-6">
          <p className="section-kicker">Produto</p>
          <h2 className="mt-2 text-2xl font-semibold text-slate-950">Explicação e contexto</h2>
          <div className="mt-5 rounded-[1.3rem] border border-slate-900/10 bg-white p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">O que é</p>
            <p className="mt-2 text-base leading-7 text-slate-700">
              {primary?.product_context ?? primary?.full_description ?? primary?.description ?? "Produto impresso em 3D sob demanda."}
            </p>
          </div>
          {primary?.character_origin ? (
            <div className="mt-4 rounded-[1.3rem] border border-orange-200 bg-orange-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-orange-700">Personagem / origem</p>
              <p className="mt-2 text-sm leading-6 text-orange-950">{primary.character_origin}</p>
            </div>
          ) : null}
        </div>
      </section>

      <PhotoDownloadPanel photos={adPhotos} projectName={project.name} />

      <StorePublicationPanel
        canPublish={can(PERMISSIONS.storesPublish)}
        canManageStores={can(PERMISSIONS.storesManage)}
        project={project}
        stores={publicationStores}
        storesLoading={storesLoading}
        storesError={storesError}
        selectedStoreId={selectedStoreId}
        onSelectStore={(value) => {
          setSelectedStoreId(value);
          setDraft(null);
          setDraftError(null);
        }}
        onPrepareDraft={prepareStoreDraft}
        onPublishNow={publishNow}
        onSaveStoreSettings={saveStoreSettings}
        selectedStore={selectedStore}
        draft={draft}
        draftLoading={draftLoading}
        draftError={draftError}
        categoryId={categoryId}
        onCategoryIdChange={setCategoryId}
        saveStoreLoading={saveStoreLoading}
        storeSettingsMessage={storeSettingsMessage}
      />

      <section className="panel p-5 md:p-6">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="section-kicker">Marketplaces</p>
            <h2 className="mt-2 text-2xl font-semibold text-slate-950">Conteúdo para cadastrar o produto</h2>
          </div>
          {copied ? <span className="pill">{copied}</span> : null}
        </div>

        <div className="mt-6 grid gap-5 xl:grid-cols-3">
          {channels.map((channel) => (
            <MarketplaceCard key={channel.marketplace} channel={channel} price={currency(salePrice)} onCopy={copyText} />
          ))}
        </div>
      </section>

      <section className="panel p-5 md:p-6">
        <p className="section-kicker">Dicas comerciais</p>
        <h2 className="mt-2 text-2xl font-semibold text-slate-950">Cuidados antes de publicar</h2>
        <ul className="mt-5 grid gap-3 md:grid-cols-2">
          {sales.sales_tips.map((tip) => (
            <li key={tip} className="rounded-[1.2rem] border border-slate-900/10 bg-white p-4 text-sm leading-6 text-slate-700">
              {tip}
            </li>
          ))}
        </ul>
      </section>

      <section className="grid gap-5 lg:grid-cols-2">
        <ArtifactPanel title="Arquivos exportados" items={project.artifacts} />
        <ArtifactPanel title="Relatórios e previews" items={[...project.reports, ...project.previews]} />
      </section>
    </div>
  );
}

function StorePublicationPanel({
  canPublish,
  canManageStores,
  project,
  stores,
  storesLoading,
  storesError,
  selectedStoreId,
  onSelectStore,
  onPrepareDraft,
  onPublishNow,
  onSaveStoreSettings,
  selectedStore,
  draft,
  draftLoading,
  draftError,
  categoryId,
  onCategoryIdChange,
  saveStoreLoading,
  storeSettingsMessage,
}: {
  canPublish: boolean;
  canManageStores: boolean;
  project: ProjectDetail;
  stores: StoreIntegration[];
  storesLoading: boolean;
  storesError: string | null;
  selectedStoreId: string;
  onSelectStore: (value: string) => void;
  onPrepareDraft: () => void;
  onPublishNow: () => void;
  onSaveStoreSettings: () => void;
  selectedStore: StoreIntegration | null;
  draft: ProductPublishDraft | null;
  draftLoading: boolean;
  draftError: string | null;
  categoryId: string;
  onCategoryIdChange: (value: string) => void;
  saveStoreLoading: boolean;
  storeSettingsMessage: string | null;
}) {
  return (
    <section className="panel p-5 md:p-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="section-kicker">Lojas do usuário</p>
          <h2 className="mt-2 text-2xl font-semibold text-slate-950">Cadastrar este produto em uma loja</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            A publicação sempre usa apenas as lojas do usuário logado. Assim o produto não corre risco de ir para a conta errada.
          </p>
        </div>
        <span className="pill">{storesLoading ? "Carregando lojas..." : `${stores.length} lojas disponíveis`}</span>
      </div>

      {!canPublish ? (
        <div className="mt-5 rounded-[1.3rem] border border-slate-900/10 bg-white p-5 text-sm leading-6 text-slate-600">
          Seu perfil não tem permissão para publicar em lojas.
        </div>
      ) : storesError ? (
        <div className="mt-5 rounded-[1.3rem] border border-red-200 bg-red-50 p-5 text-sm leading-6 text-red-700">{storesError}</div>
      ) : stores.length === 0 ? (
        <div className="mt-5 rounded-[1.3rem] border border-slate-900/10 bg-white p-5 text-sm leading-6 text-slate-600">
          Nenhuma loja foi cadastrada para este usuário.
          {canManageStores ? (
            <>
              {" "}
              <Link href="/stores" className="font-semibold text-orange-700 underline">
                Cadastre uma loja antes de publicar.
              </Link>
            </>
          ) : null}
        </div>
      ) : (
        <div className="mt-6 space-y-5">
          <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
            <div className="rounded-[1.3rem] border border-slate-900/10 bg-white p-5">
              <label className="block">
                <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Escolha a loja de destino</span>
                <select
                  value={selectedStoreId}
                  onChange={(event) => onSelectStore(event.target.value)}
                  className="mt-3 w-full rounded-[1.1rem] border border-slate-900/10 bg-white px-4 py-4 text-base text-slate-950 outline-none focus:border-orange-500"
                >
                  {stores.map((store) => (
                    <option key={store.id} value={store.id}>
                      {store.marketplace_label} · {store.name}
                    </option>
                  ))}
                </select>
              </label>

              {selectedStore ? (
                <>
                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    <StoreSummaryLine label="Loja" value={selectedStore.name} />
                    <StoreSummaryLine label="Marketplace" value={selectedStore.marketplace_label} />
                    <StoreSummaryLine label="Conta" value={selectedStore.account_label || "Sem apelido"} />
                    <StoreSummaryLine label="Status" value={selectedStore.status} />
                  </div>

                  <div className="mt-4 rounded-[1.2rem] border border-slate-900/10 bg-slate-50 p-4">
                    <label className="block">
                      <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Categoria MLB do produto</span>
                      <input
                        value={categoryId}
                        onChange={(event) => onCategoryIdChange(event.target.value)}
                        placeholder="Ex.: MLB3937"
                        className="mt-3 w-full rounded-[1rem] border border-slate-900/10 bg-white px-4 py-3 text-base text-slate-950 outline-none focus:border-orange-500"
                      />
                    </label>
                    <p className="mt-2 text-sm leading-6 text-slate-600">
                      Informe a categoria correta do Mercado Livre para remover o bloqueio de publicação.
                    </p>
                    <div className="mt-3 flex flex-wrap gap-3">
                      <button
                        type="button"
                        onClick={onSaveStoreSettings}
                        disabled={saveStoreLoading}
                        className="rounded-full border border-slate-900/10 bg-white px-4 py-2.5 text-sm font-semibold text-slate-900 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {saveStoreLoading ? "Salvando..." : "Salvar categoria"}
                      </button>
                      {storeSettingsMessage ? <span className="pill">{storeSettingsMessage}</span> : null}
                    </div>
                  </div>
                </>
              ) : null}

              <div className="mt-5 flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={onPrepareDraft}
                  disabled={!selectedStoreId || draftLoading}
                  className="rounded-full bg-slate-950 px-5 py-3 text-sm font-semibold text-white transition hover:bg-orange-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {draftLoading ? "Preparando cadastro..." : "Cadastrar nesta loja"}
                </button>
                <button
                  type="button"
                  onClick={onPublishNow}
                  disabled={!selectedStoreId || draftLoading}
                  className="rounded-full bg-orange-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-orange-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {draftLoading ? "Publicando..." : "Publicar agora"}
                </button>
                {canManageStores ? (
                  <Link href="/stores" className="rounded-full border border-slate-900/10 bg-white px-5 py-3 text-sm font-semibold text-slate-900">
                    Gerenciar lojas
                  </Link>
                ) : null}
              </div>
            </div>

            <div className="rounded-[1.3rem] border border-slate-900/10 bg-slate-50/80 p-5">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Contexto do cadastro</p>
              <h3 className="mt-2 text-lg font-semibold text-slate-950">{project.name}</h3>
              <ul className="mt-4 space-y-2 text-sm leading-6 text-slate-600">
                <li>O rascunho usa a ficha comercial deste produto como base.</li>
                <li>Preço, descrição, imagens e atributos são preparados para a loja escolhida.</li>
                <li>Se a loja não estiver pronta, o sistema mostra bloqueios antes da publicação.</li>
              </ul>
            </div>
          </div>

          {draftError ? (
            <div className="rounded-[1.3rem] border border-red-200 bg-red-50 p-5 text-sm leading-6 text-red-700">{draftError}</div>
          ) : null}

          {draft ? (
            <div className="grid gap-5 xl:grid-cols-[0.85fr_1.15fr]">
              <div className="rounded-[1.3rem] border border-slate-900/10 bg-white p-5">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Resultado do cadastro</p>
                <h3 className="mt-2 text-xl font-semibold text-slate-950">{draft.store_name}</h3>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  Marketplace: {draft.marketplace} · status do rascunho: {draft.status}
                </p>
                <div className="mt-4 rounded-[1rem] border border-slate-900/10 bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-900">
                  Publicação real: {draft.can_publish ? "liberada" : "bloqueada até validar os itens obrigatórios"}
                </div>
                {draft.status === "published" ? (
                  <div className="mt-4 rounded-[1rem] border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm leading-6 text-emerald-900">
                    Produto publicado com sucesso.
                    {draft.published_item_id ? ` ID do anúncio: ${draft.published_item_id}.` : ""}
                    {draft.published_permalink ? (
                      <>
                        {" "}
                        <a href={draft.published_permalink} target="_blank" rel="noreferrer" className="font-semibold underline">
                          Abrir anúncio
                        </a>
                      </>
                    ) : null}
                  </div>
                ) : null}
                <DraftList title="Bloqueios" items={draft.blockers} emptyText="Nenhum bloqueio no momento." tone="danger" />
                <DraftList title="Avisos" items={draft.warnings} emptyText="Nenhum aviso adicional." tone="warning" />
                <DraftList title="Próximos passos" items={draft.next_steps} emptyText="Nenhuma ação pendente." tone="neutral" />
              </div>

              <div className="rounded-[1.3rem] border border-slate-900/10 bg-white p-5">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Payload preparado</p>
                <pre className="mt-4 overflow-x-auto rounded-[1rem] border border-slate-900/10 bg-slate-950 p-4 text-xs leading-6 text-slate-100">
{JSON.stringify(draft.payload, null, 2)}
                </pre>
              </div>
            </div>
          ) : null}
        </div>
      )}
    </section>
  );
}

function StoreSummaryLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1rem] border border-slate-900/10 bg-slate-50 px-4 py-3">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">{label}</p>
      <p className="mt-1 text-sm font-semibold text-slate-900">{value}</p>
    </div>
  );
}

function DraftList({
  title,
  items,
  emptyText,
  tone,
}: {
  title: string;
  items: string[];
  emptyText: string;
  tone: "danger" | "warning" | "neutral";
}) {
  const toneClass =
    tone === "danger"
      ? "border-red-200 bg-red-50 text-red-800"
      : tone === "warning"
        ? "border-orange-200 bg-orange-50 text-orange-900"
        : "border-slate-900/10 bg-slate-50 text-slate-700";

  return (
    <div className="mt-4">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">{title}</p>
      <div className={`mt-2 rounded-[1rem] border px-4 py-3 ${toneClass}`}>
        {items.length === 0 ? (
          <p className="text-sm leading-6">{emptyText}</p>
        ) : (
          <ul className="space-y-2 text-sm leading-6">
            {items.map((item) => (
              <li key={item}>• {item}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

type AdPhoto = {
  label: string;
  href: string;
  filename: string;
};

function PhotoDownloadPanel({ photos, projectName }: { photos: AdPhoto[]; projectName: string }) {
  const [status, setStatus] = useState<string | null>(null);

  async function downloadPhoto(photo: AdPhoto) {
    try {
      const response = await fetch(photo.href);
      if (!response.ok) throw new Error("download_failed");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = photo.filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setStatus(`Baixando ${photo.filename}`);
      window.setTimeout(() => setStatus(null), 1800);
    } catch {
      window.open(photo.href, "_blank", "noopener,noreferrer");
      setStatus("A imagem abriu em nova aba para salvar manualmente.");
      window.setTimeout(() => setStatus(null), 2600);
    }
  }

  return (
    <section className="panel p-5 md:p-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="section-kicker">Fotos para anúncio</p>
          <h2 className="mt-2 text-2xl font-semibold text-slate-950">Imagens prontas para marketplace</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            Baixe a imagem principal e os previews gerados para usar no Mercado Livre, Shopee, Instagram e catálogo próprio.
          </p>
        </div>
        {status ? <span className="pill">{status}</span> : <span className="pill">{photos.length} imagens</span>}
      </div>

      {photos.length === 0 ? (
        <div className="mt-5 rounded-[1.3rem] border border-slate-900/10 bg-white p-5 text-sm leading-6 text-slate-600">
          Nenhuma imagem de anúncio foi encontrada para este produto. Gere previews no processamento do projeto antes de publicar.
        </div>
      ) : (
        <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {photos.map((photo, index) => (
            <article key={`${photo.href}-${photo.label}`} className="overflow-hidden rounded-[1.4rem] border border-slate-900/10 bg-white shadow-sm">
              <div className="aspect-[4/3] bg-slate-100">
                <img src={photo.href} alt={`${projectName} - ${photo.label}`} className="h-full w-full object-cover" loading="lazy" />
              </div>
              <div className="space-y-3 p-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Imagem {index + 1}</p>
                  <h3 className="mt-1 text-sm font-semibold text-slate-950">{photo.label}</h3>
                </div>
                <button
                  type="button"
                  onClick={() => downloadPhoto(photo)}
                  className="w-full rounded-full bg-slate-950 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-orange-700"
                >
                  Baixar foto
                </button>
                <a
                  href={photo.href}
                  target="_blank"
                  rel="noreferrer"
                  className="block text-center text-xs font-semibold text-slate-500 underline"
                >
                  Abrir original
                </a>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function MarketplaceCard({ channel, price, onCopy }: { channel: MarketplaceAttribute; price: string; onCopy: (label: string, text: string) => void }) {
  const attributes = channel.registration_attributes ?? [];
  const bullets = channel.bullet_points ?? [];
  const hashtags = channel.hashtags?.length ? channel.hashtags : channel.tags;
  const text = [
    channel.title,
    "",
    `Preço: ${price}`,
    `Categoria: ${channel.category}`,
    "",
    channel.full_description ?? channel.description,
    "",
    "Atributos:",
    ...attributes.map((item) => `- ${item.label}: ${item.value}`),
    "",
    "Destaques:",
    ...bullets.map((item) => `- ${item}`),
    "",
    `Tags/hashtags: ${hashtags.join(", ")}`,
  ].join("\n");

  return (
    <article className="rounded-[1.5rem] border border-slate-900/10 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="section-kicker">{channel.marketplace}</p>
          <h3 className="mt-2 text-xl font-semibold leading-tight text-slate-950">{channel.title}</h3>
        </div>
        <button
          type="button"
          onClick={() => onCopy(`Copiado: ${channel.marketplace}`, text)}
          className="rounded-full border border-slate-900/10 px-3 py-2 text-xs font-semibold text-slate-700 hover:border-orange-300 hover:text-orange-700"
        >
          Copiar
        </button>
      </div>
      <p className="mt-4 text-sm leading-6 text-slate-600">{channel.full_description ?? channel.description}</p>

      {attributes.length ? (
        <div className="mt-5 rounded-[1.1rem] bg-slate-50 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Atributos de cadastro</p>
          <div className="mt-3 grid gap-2">
            {attributes.map((item) => (
              <div key={`${channel.marketplace}-${item.label}`} className="rounded-xl bg-white px-3 py-2 text-sm">
                <span className="font-semibold text-slate-900">{item.label}: </span>
                <span className="text-slate-600">{item.value}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {bullets.length ? (
        <div className="mt-5 rounded-[1.1rem] bg-orange-50 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-orange-700">Destaques do anúncio</p>
          <ul className="mt-3 space-y-2 text-sm leading-6 text-orange-950">
            {bullets.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="mt-4 flex flex-wrap gap-2">
        {hashtags.slice(0, 12).map((tag) => (
          <span key={tag} className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">
            {tag.startsWith("#") ? tag : `#${tag.replaceAll(" ", "")}`}
          </span>
        ))}
      </div>
      <div className="mt-5 rounded-[1.1rem] bg-slate-50 p-4">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Campos obrigatórios</p>
        <ul className="mt-3 space-y-2 text-sm leading-6 text-slate-700">
          {channel.required_fields.map((field) => (
            <li key={field}>{field}</li>
          ))}
        </ul>
      </div>
    </article>
  );
}

function Metric({ label, value, strong = false }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="rounded-[1.2rem] border border-slate-900/10 bg-white p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">{label}</p>
      <p className={`mt-2 text-2xl font-semibold ${strong ? "text-orange-700" : "text-slate-950"}`}>{value}</p>
    </div>
  );
}

function InfoPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.1rem] bg-slate-50 px-4 py-3">
      <p className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-slate-400">{label}</p>
      <p className="mt-1 font-semibold text-slate-800">{value}</p>
    </div>
  );
}

function MarginInput({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return (
    <label className="block rounded-[1.2rem] border border-slate-900/10 bg-white/80 p-4">
      <span className="text-sm font-semibold text-slate-900">{label}</span>
      <div className="mt-3 flex items-center gap-3">
        <input
          type="range"
          min="0"
          max="200"
          step="5"
          value={value}
          onChange={(event) => onChange(Number(event.target.value))}
          className="w-full accent-orange-600"
        />
        <input
          type="number"
          min="0"
          max="500"
          value={value}
          onChange={(event) => onChange(Number(event.target.value || 0))}
          className="w-24 rounded-xl border border-slate-900/10 px-3 py-2 text-sm font-semibold outline-none focus:border-orange-500"
        />
        <span className="text-sm font-semibold text-slate-500">%</span>
      </div>
    </label>
  );
}

function ArtifactPanel({ title, items }: { title: string; items: ArtifactReference[] }) {
  return (
    <section className="panel p-5 md:p-6">
      <p className="section-kicker">{title}</p>
      <div className="mt-4 space-y-3">
        {items.length === 0 ? (
          <p className="text-sm text-slate-500">Nenhum item disponível.</p>
        ) : (
          items.slice(0, 8).map((item) => (
            <div key={`${item.label}-${item.path}`} className="rounded-[1.1rem] border border-slate-900/10 bg-white p-3">
              <p className="text-sm font-semibold text-slate-900">{item.label}</p>
              <p className="mt-1 break-all text-xs text-slate-500">{item.path}</p>
            </div>
          ))
        )}
      </div>
    </section>
  );
}

function collectAdPhotos(project: ProjectDetail): AdPhoto[] {
  const photos = new Map<string, AdPhoto>();
  const addPhoto = (label: string, path?: string | null) => {
    const href = fileUrl(path);
    if (!href || !/\.(png|jpe?g|webp)(\?.*)?$/i.test(href)) return;
    photos.set(href, {
      label,
      href,
      filename: `${safeFileName(project.name)}_${safeFileName(label)}.${extensionFromUrl(href)}`,
    });
  };

  addPhoto("imagem-principal", project.preview_url);
  project.previews.forEach((item) => addPhoto(item.label, item.path));
  return Array.from(photos.values());
}

function safeFileName(value: string) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .toLowerCase()
    .slice(0, 80);
}

function extensionFromUrl(url: string) {
  const clean = url.split("?")[0] ?? url;
  const extension = clean.split(".").pop()?.toLowerCase();
  return extension && ["png", "jpg", "jpeg", "webp"].includes(extension) ? extension : "png";
}

function materialFromAssumptions(items: string[]) {
  const material = items.find((item) => item.startsWith("Material assumido:"));
  return material?.replace("Material assumido:", "").replace("Ajuste se o projeto usar outro filamento.", "").trim() || "PLA";
}

function currency(value: number) {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);
}
