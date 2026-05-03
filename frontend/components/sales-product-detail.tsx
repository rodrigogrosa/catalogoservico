"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import {
  buildPublicationDraft,
  fetchStores,
  fileUrl,
  updateProject,
  updateStore,
  type ArtifactReference,
  type MarketplaceAttribute,
  type ProductPublishDraft,
  type ProjectDetail,
  type SalesProfile,
  type SalesProfileExtraPhoto,
  type SalesProfileVariation,
  type StoreIntegration,
} from "@/lib/api";
import { PERMISSIONS } from "@/lib/permissions";

type Props = {
  project: ProjectDetail;
};

export function SalesProductDetail({ project }: Props) {
  const { can } = useAuth();

  // --- local copy (updated after save) ---
  const [localProject, setLocalProject] = useState<ProjectDetail>(project);
  const sales = localProject.sales_profile;

  // --- edit mode ---
  const [editing, setEditing] = useState(false);
  const [salesDraft, setSalesDraft] = useState<SalesProfile | null>(null);
  const [nameDraft, setNameDraft] = useState(localProject.name);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  // --- pricing simulator (view mode) ---
  const [margin, setMargin] = useState(sales?.default_margin_percent ?? 50);
  const [resellerMargin, setResellerMargin] = useState(sales?.reseller_margin_percent ?? 18);

  // --- clipboard ---
  const [copied, setCopied] = useState<string | null>(null);

  // --- stores / publication ---
  const [stores, setStores] = useState<StoreIntegration[]>([]);
  const [storesLoading, setStoresLoading] = useState(true);
  const [storesError, setStoresError] = useState<string | null>(null);
  const [selectedStoreId, setSelectedStoreId] = useState("");
  const [publishDraft, setPublishDraft] = useState<ProductPublishDraft | null>(null);
  const [draftLoading, setDraftLoading] = useState(false);
  const [draftError, setDraftError] = useState<string | null>(null);
  const [saveStoreLoading, setSaveStoreLoading] = useState(false);
  const [storeSettingsMessage, setStoreSettingsMessage] = useState<string | null>(null);
  const [categoryId, setCategoryId] = useState("");

  const imageUrl = fileUrl(localProject.preview_url);
  const hasImagePreview = imageUrl ? /\.(png|jpe?g|webp)(\?.*)?$/i.test(imageUrl) : false;

  // active display data — in edit mode show draft values
  const activeSales = editing ? salesDraft : sales;
  const channels = useMemo(() => activeSales?.marketplace_attributes ?? [], [activeSales]);
  const adPhotos = useMemo(
    () => collectAdPhotos(localProject, activeSales?.photo_label_overrides ?? null, activeSales?.hidden_photo_paths ?? null, activeSales?.extra_ad_photos ?? null, activeSales?.photo_order ?? null),
    [localProject, activeSales],
  );
  const primary = channels[0];

  const publicationStores = useMemo(
    () => stores.filter((s) => s.status === "configured" || s.status === "needs_credentials" || s.status === "draft"),
    [stores],
  );
  const selectedStore = publicationStores.find((s) => s.id === selectedStoreId) ?? null;

  // --- edit helpers ---
  function startEditing() {
    setNameDraft(localProject.name);
    setSalesDraft(JSON.parse(JSON.stringify(localProject.sales_profile)) as SalesProfile);
    setEditing(true);
    setSaveMsg(null);
  }

  function cancelEditing() {
    setEditing(false);
    setSalesDraft(null);
    setSaveMsg(null);
  }

  async function handleSave() {
    if (!salesDraft) return;
    setSaving(true);
    setSaveMsg(null);
    try {
      const updated = await updateProject(localProject.id, {
        name: nameDraft,
        sales_profile: salesDraft as Record<string, unknown>,
      });
      setLocalProject(updated);
      setEditing(false);
      setSalesDraft(null);
      setSaveMsg("Ficha salva com sucesso.");
    } catch (err) {
      setSaveMsg(err instanceof Error ? err.message : "Falha ao salvar. Tente novamente.");
    } finally {
      setSaving(false);
    }
  }

  function setSalesField(field: keyof SalesProfile, value: unknown) {
    setSalesDraft((prev) => (prev ? { ...prev, [field]: value } : prev));
  }

  function updateChannel(idx: number, updates: Partial<MarketplaceAttribute>) {
    setSalesDraft((prev) => {
      if (!prev) return prev;
      const attrs = [...(prev.marketplace_attributes ?? [])];
      attrs[idx] = { ...attrs[idx], ...updates };
      return { ...prev, marketplace_attributes: attrs };
    });
  }

  function updateVariation(idx: number, updates: Partial<SalesProfileVariation>) {
    setSalesDraft((prev) => {
      if (!prev) return prev;
      const vars = [...(prev.variations ?? [])];
      vars[idx] = { ...vars[idx], ...updates };
      return { ...prev, variations: vars };
    });
  }

  function addVariation() {
    setSalesDraft((prev) => {
      if (!prev) return prev;
      const base = prev.sku ?? "SM3D-NOVO";
      const unitPrice = prev.suggested_price_50_margin_brl;
      const kitIdx = (prev.variations?.filter((v) => v.sku.includes("-KIT")).length ?? 0) + 1;
      const newVar: SalesProfileVariation = {
        sku: `${base}-KIT${kitIdx === 1 ? "10" : kitIdx * 10}`,
        name: "Kit 10 unidades (10% desconto)",
        quantity: 10,
        stock: 320,
        price_brl: Math.round(unitPrice * 10 * 0.9 * 100) / 100,
        description: "Lote de 10 peças iguais ou em cores variadas — 10% de desconto sobre o unitário.",
      };
      return { ...prev, variations: [...(prev.variations ?? []), newVar] };
    });
  }

  function removeVariation(idx: number) {
    setSalesDraft((prev) => {
      if (!prev) return prev;
      const vars = (prev.variations ?? []).filter((_, i) => i !== idx);
      return { ...prev, variations: vars };
    });
  }

  function updateSalesTip(idx: number, value: string) {
    setSalesDraft((prev) => {
      if (!prev) return prev;
      const tips = [...(prev.sales_tips ?? [])];
      tips[idx] = value;
      return { ...prev, sales_tips: tips };
    });
  }


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

  const salePrice = (activeSales?.estimated_base_cost_brl ?? sales.estimated_base_cost_brl) * (1 + margin / 100);
  const resellerPrice = (activeSales?.estimated_base_cost_brl ?? sales.estimated_base_cost_brl) * (1 + resellerMargin / 100);

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
      const result = await buildPublicationDraft(selectedStoreId, localProject.id);
      setPublishDraft(result);
    } catch (error) {
      setDraftError(error instanceof Error ? error.message : "Falha ao preparar cadastro para a loja.");
      setPublishDraft(null);
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
      setPublishDraft(null);
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
      const result = await buildPublicationDraft(selectedStoreId, localProject.id, { mode: "publish", stock: 1 });
      setPublishDraft(result);
    } catch (error) {
      setDraftError(error instanceof Error ? error.message : "Falha ao publicar produto.");
    } finally {
      setDraftLoading(false);
    }
  }

  return (
    <div className="space-y-6">

      {/* ── Edit toolbar ─────────────────────────────────────────────────── */}
      {editing ? (
        <div className="sticky top-2 z-20 flex flex-wrap items-center gap-3 rounded-[1.4rem] border border-blue-200 bg-blue-50 px-5 py-4 shadow-lg">
          <span className="flex-1 text-sm font-semibold text-blue-900">Modo de edição — altere qualquer campo e clique em Salvar.</span>
          {saveMsg ? <span className="text-sm text-red-700">{saveMsg}</span> : null}
          <button
            type="button"
            onClick={() => { void handleSave(); }}
            disabled={saving}
            className="rounded-full bg-blue-700 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-800 disabled:opacity-60"
          >
            {saving ? "Salvando..." : "Salvar alterações"}
          </button>
          <button
            type="button"
            onClick={cancelEditing}
            disabled={saving}
            className="rounded-full border border-blue-300 bg-white px-5 py-2.5 text-sm font-semibold text-blue-800 transition hover:bg-blue-100 disabled:opacity-60"
          >
            Cancelar
          </button>
        </div>
      ) : (
        <div className="flex items-center justify-between">
          <div />
          <div className="flex items-center gap-3">
            {saveMsg ? <span className="pill text-emerald-700">{saveMsg}</span> : null}
            <button
              type="button"
              onClick={startEditing}
              className="rounded-full border border-slate-900/10 bg-white px-5 py-2.5 text-sm font-semibold text-slate-900 transition hover:bg-slate-100"
            >
              Editar ficha
            </button>
          </div>
        </div>
      )}

      <section className="panel overflow-hidden p-0">
        <div className="grid gap-0 lg:grid-cols-[0.95fr_1.05fr]">
          <div className="min-h-[340px] bg-slate-100">
            {hasImagePreview ? (
              <img src={imageUrl} alt={`Imagem principal de ${localProject.name}`} className="h-full min-h-[340px] w-full object-cover" />
            ) : (
              <div className="flex h-full min-h-[340px] items-center justify-center p-8 text-center text-base text-slate-500">
                Sem imagem principal disponível
              </div>
            )}
          </div>

          <div className="p-6 md:p-8">
            <p className="section-kicker">Produto para venda</p>
            {editing ? (
              <input
                value={nameDraft}
                onChange={(e) => setNameDraft(e.target.value)}
                className="mt-3 w-full rounded-[1rem] border border-blue-300 bg-white px-4 py-3 text-2xl font-semibold text-slate-950 outline-none focus:border-blue-500"
                placeholder="Nome do produto"
              />
            ) : (
              <h1 className="mt-3 text-4xl font-semibold leading-tight text-slate-950">{localProject.name}</h1>
            )}
            {editing ? (
              <textarea
                value={salesDraft?.marketplace_attributes?.[0]?.short_description ?? salesDraft?.marketplace_attributes?.[0]?.description ?? ""}
                onChange={(e) => updateChannel(0, { short_description: e.target.value, description: e.target.value })}
                rows={3}
                className="mt-4 w-full rounded-[1rem] border border-blue-300 bg-white px-4 py-3 text-base leading-7 text-slate-700 outline-none focus:border-blue-500"
                placeholder="Descrição curta do produto"
              />
            ) : (
              <p className="mt-4 text-lg leading-8 text-slate-700">
                {primary?.short_description ?? primary?.description ?? "Produto impresso em 3D sob demanda, com ficha comercial e precificação em Real brasileiro."}
              </p>
            )}

            <div className="mt-6 grid gap-3 sm:grid-cols-3">
              {editing ? (
                <>
                  <EditableMetric
                    label="Preço sugerido"
                    value={salesDraft?.suggested_price_50_margin_brl ?? 0}
                    onChange={(v) => setSalesField("suggested_price_50_margin_brl", v)}
                    strong
                  />
                  <EditableMetric
                    label="Custo base"
                    value={salesDraft?.estimated_base_cost_brl ?? 0}
                    onChange={(v) => setSalesField("estimated_base_cost_brl", v)}
                  />
                  <EditableMetric
                    label="Revendedor"
                    value={salesDraft?.reseller_price_brl ?? 0}
                    onChange={(v) => setSalesField("reseller_price_brl", v)}
                  />
                </>
              ) : (
                <>
                  <Metric label="Preço sugerido" value={currency(sales.suggested_price_50_margin_brl)} strong />
                  <Metric label="Custo base" value={currency(sales.estimated_base_cost_brl)} />
                  <Metric label="Revendedor" value={currency(sales.reseller_price_brl)} />
                </>
              )}
            </div>

            <div className="mt-6 grid gap-3 text-sm text-slate-600 sm:grid-cols-3">
              <InfoPill label="Material" value={materialFromAssumptions(sales.assumptions)} />
              <InfoPill label="Produção" value={`${sales.estimated_material_g}g · ${sales.estimated_print_hours}h`} />
              <InfoPill label="Versão" value={`v${String(localProject.version).padStart(3, "0")} · ${localProject.input_format.toUpperCase()}`} />
            </div>
          </div>
        </div>
      </section>

      {/* ── Identificação e Estoque ───────────────────────────────────────── */}
      <section className="panel p-5 md:p-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="section-kicker">Identificação e Estoque</p>
            <h2 className="mt-2 text-2xl font-semibold text-slate-950">SKU, Estoque e Garantia</h2>
          </div>
        </div>
        <div className="mt-5 grid gap-4 sm:grid-cols-3">
          <EditableField
            label="Código SKU"
            editing={editing}
            value={editing ? (salesDraft?.sku ?? "") : (sales.sku ?? "Não cadastrado")}
            onChange={(v) => setSalesField("sku", v)}
            placeholder="Ex.: SM3D-PRODUTO-001"
          />
          <EditableField
            label="Estoque padrão"
            editing={editing}
            type="number"
            value={editing ? String(salesDraft?.default_stock ?? 100) : String(sales.default_stock ?? 100)}
            onChange={(v) => setSalesField("default_stock", Number(v))}
            placeholder="100"
          />
          <EditableField
            label="Prazo de garantia (meses)"
            editing={editing}
            type="number"
            value={editing ? String(salesDraft?.warranty?.duration ?? 1) : String(sales.warranty?.duration ?? 1)}
            onChange={(v) =>
              setSalesField("warranty", {
                ...(editing ? salesDraft?.warranty : sales.warranty),
                duration: Number(v),
                unit: "months",
                type: "seller",
                label: `${v} mês — garantia do vendedor`,
              })
            }
            placeholder="1"
          />
        </div>
        {(editing ? salesDraft?.warranty : sales.warranty) ? (
          <p className="mt-3 text-sm text-slate-600">
            {editing ? salesDraft?.warranty?.label : sales.warranty?.label}
          </p>
        ) : null}
      </section>

      {/* ── Variações ────────────────────────────────────────────────────── */}
      <section className="panel p-5 md:p-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="section-kicker">Variações</p>
            <h2 className="mt-2 text-2xl font-semibold text-slate-950">Opções de venda</h2>
          </div>
          {editing ? (
            <button
              type="button"
              onClick={addVariation}
              className="rounded-full border border-blue-300 bg-blue-50 px-4 py-2 text-sm font-semibold text-blue-800 hover:bg-blue-100"
            >
              + Adicionar variação
            </button>
          ) : null}
        </div>
        {((editing ? salesDraft?.variations : sales.variations) ?? []).length === 0 ? (
          <p className="mt-4 text-sm text-slate-500">
            {editing ? "Clique em '+ Adicionar variação' para criar variações." : "Nenhuma variação cadastrada."}
          </p>
        ) : (
          <div className="mt-5 grid gap-4 md:grid-cols-2">
            {((editing ? salesDraft?.variations : sales.variations) ?? []).map((v, idx) => (
              <div key={idx} className="rounded-[1.2rem] border border-slate-900/10 bg-white p-4">
                {editing ? (
                  <div className="space-y-3">
                    <div className="grid grid-cols-2 gap-3">
                      <EditableField label="SKU" editing value={v.sku} onChange={(val) => updateVariation(idx, { sku: val })} />
                      <EditableField label="Nome" editing value={v.name} onChange={(val) => updateVariation(idx, { name: val })} />
                      <EditableField label="Qtd" editing type="number" value={String(v.quantity)} onChange={(val) => updateVariation(idx, { quantity: Number(val) })} />
                      <EditableField label="Estoque" editing type="number" value={String(v.stock)} onChange={(val) => updateVariation(idx, { stock: Number(val) })} />
                      <EditableField label="Preço (R$)" editing type="number" value={String(v.price_brl)} onChange={(val) => updateVariation(idx, { price_brl: Number(val) })} />
                    </div>
                    <button
                      type="button"
                      onClick={() => removeVariation(idx)}
                      className="rounded-full border border-red-200 px-3 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-50"
                    >
                      Remover
                    </button>
                  </div>
                ) : (
                  <>
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">{v.sku}</p>
                    <h3 className="mt-1 text-base font-semibold text-slate-950">{v.name}</h3>
                    <div className="mt-3 grid grid-cols-3 gap-2 text-sm text-slate-600">
                      <div><span className="font-semibold">Qtd:</span> {v.quantity}</div>
                      <div><span className="font-semibold">Estoque:</span> {v.stock}</div>
                      <div><span className="font-semibold">Preço:</span> {currency(v.price_brl)}</div>
                    </div>
                    {v.description ? <p className="mt-2 text-xs text-slate-500">{v.description}</p> : null}
                  </>
                )}
              </div>
            ))}
          </div>
        )}
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
            {editing ? (
              <textarea
                value={salesDraft?.marketplace_attributes?.[0]?.product_context ?? salesDraft?.marketplace_attributes?.[0]?.full_description ?? ""}
                onChange={(e) => updateChannel(0, { product_context: e.target.value, full_description: e.target.value })}
                rows={5}
                className="mt-2 w-full rounded-[0.8rem] border border-blue-300 bg-white p-3 text-base leading-7 text-slate-700 outline-none focus:border-blue-500"
                placeholder="Descrição completa do produto"
              />
            ) : (
              <p className="mt-2 text-base leading-7 text-slate-700">
                {primary?.product_context ?? primary?.full_description ?? primary?.description ?? "Produto impresso em 3D sob demanda."}
              </p>
            )}
          </div>
          {primary?.character_origin ? (
            <div className="mt-4 rounded-[1.3rem] border border-orange-200 bg-orange-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-orange-700">Personagem / origem</p>
              <p className="mt-2 text-sm leading-6 text-orange-950">{primary.character_origin}</p>
            </div>
          ) : null}
        </div>
      </section>

      <PhotoDownloadPanel
        photos={adPhotos}
        projectName={localProject.name}
        editing={editing}
        labelOverrides={salesDraft?.photo_label_overrides ?? {}}
        hiddenPaths={salesDraft?.hidden_photo_paths ?? []}
        extraPhotos={salesDraft?.extra_ad_photos ?? []}
        onUpdateLabel={(path, label) =>
          setSalesField("photo_label_overrides", { ...(salesDraft?.photo_label_overrides ?? {}), [path]: label })
        }
        onHidePhoto={(path) =>
          setSalesField("hidden_photo_paths", [...new Set([...(salesDraft?.hidden_photo_paths ?? []), path])])
        }
        onShowPhoto={(path) =>
          setSalesField("hidden_photo_paths", (salesDraft?.hidden_photo_paths ?? []).filter((p) => p !== path))
        }
        onAddPhoto={(photo) =>
          setSalesField("extra_ad_photos", [...(salesDraft?.extra_ad_photos ?? []), photo])
        }
        onRemoveExtra={(idx) =>
          setSalesField("extra_ad_photos", (salesDraft?.extra_ad_photos ?? []).filter((_, i) => i !== idx))
        }
        onUpdateExtra={(idx, updates) => {
          const arr = [...(salesDraft?.extra_ad_photos ?? [])];
          arr[idx] = { ...arr[idx], ...updates };
          setSalesField("extra_ad_photos", arr);
        }}
        onReorder={(newOrder) => setSalesField("photo_order", newOrder)}
      />

      <StorePublicationPanel
        canPublish={can(PERMISSIONS.storesPublish)}
        canManageStores={can(PERMISSIONS.storesManage)}
        project={localProject}
        stores={publicationStores}
        storesLoading={storesLoading}
        storesError={storesError}
        selectedStoreId={selectedStoreId}
        onSelectStore={(value) => {
          setSelectedStoreId(value);
          setPublishDraft(null);
          setDraftError(null);
        }}
        onPrepareDraft={prepareStoreDraft}
        onPublishNow={publishNow}
        onSaveStoreSettings={saveStoreSettings}
        selectedStore={selectedStore}
        draft={publishDraft}
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
          {channels.map((channel, idx) =>
            editing ? (
              <EditableMarketplaceCard
                key={channel.marketplace}
                channel={channel}
                onUpdate={(updates) => updateChannel(idx, updates)}
              />
            ) : (
              <MarketplaceCard key={channel.marketplace} channel={channel} price={currency(salePrice)} onCopy={copyText} />
            ),
          )}
        </div>
      </section>

      <section className="panel p-5 md:p-6">
        <p className="section-kicker">Dicas comerciais</p>
        <h2 className="mt-2 text-2xl font-semibold text-slate-950">Cuidados antes de publicar</h2>
        <ul className="mt-5 grid gap-3 md:grid-cols-2">
          {(editing ? (salesDraft?.sales_tips ?? []) : sales.sales_tips).map((tip, idx) =>
            editing ? (
              <li key={idx}>
                <textarea
                  value={tip}
                  onChange={(e) => updateSalesTip(idx, e.target.value)}
                  rows={3}
                  className="w-full rounded-[1.2rem] border border-blue-300 bg-white p-4 text-sm leading-6 text-slate-700 outline-none focus:border-blue-500"
                />
              </li>
            ) : (
              <li key={tip} className="rounded-[1.2rem] border border-slate-900/10 bg-white p-4 text-sm leading-6 text-slate-700">
                {tip}
              </li>
            ),
          )}
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

const MAX_AD_PHOTOS = 5;

type PhotoDownloadPanelProps = {
  photos: AdPhoto[];
  projectName: string;
  editing?: boolean;
  labelOverrides?: Record<string, string>;
  hiddenPaths?: string[];
  extraPhotos?: SalesProfileExtraPhoto[];
  onUpdateLabel?: (path: string, label: string) => void;
  onHidePhoto?: (path: string) => void;
  onShowPhoto?: (path: string) => void;
  onAddPhoto?: (photo: SalesProfileExtraPhoto) => void;
  onRemoveExtra?: (idx: number) => void;
  onUpdateExtra?: (idx: number, updates: Partial<SalesProfileExtraPhoto>) => void;
  onReorder?: (newOrderHrefs: string[]) => void;
};

function PhotoDownloadPanel({
  photos,
  projectName,
  editing = false,
  labelOverrides = {},
  hiddenPaths = [],
  extraPhotos = [],
  onUpdateLabel,
  onHidePhoto,
  onShowPhoto,
  onAddPhoto,
  onRemoveExtra,
  onUpdateExtra,
  onReorder,
}: PhotoDownloadPanelProps) {
  const [status, setStatus] = useState<string | null>(null);
  const [newPhotoUrl, setNewPhotoUrl] = useState("");
  const [newPhotoLabel, setNewPhotoLabel] = useState("");

  function movePhoto(idx: number, dir: -1 | 1) {
    const newIdx = idx + dir;
    if (newIdx < 0 || newIdx >= photos.length) return;
    const newOrder = photos.map((p) => p.href);
    [newOrder[idx], newOrder[newIdx]] = [newOrder[newIdx], newOrder[idx]];
    onReorder?.(newOrder);
  }

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

  function handleAddPhoto() {
    const url = newPhotoUrl.trim();
    if (!url) return;
    onAddPhoto?.({ label: newPhotoLabel.trim() || url.split("/").pop() || "foto-extra", path: url });
    setNewPhotoUrl("");
    setNewPhotoLabel("");
  }

  const hiddenSet = new Set(hiddenPaths);

  return (
    <section className="panel p-5 md:p-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="section-kicker">Fotos para anúncio</p>
          <h2 className="mt-2 text-2xl font-semibold text-slate-950">Imagens prontas para marketplace</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            {editing
              ? "Edite o rótulo, exclua ou adicione fotos extras por URL. As alterações são salvas junto com a ficha."
              : "Baixe a imagem principal e os previews gerados para usar no Mercado Livre, Shopee, Instagram e catálogo próprio."}
          </p>
        </div>
        {status ? <span className="pill">{status}</span> : <span className="pill">{photos.length} imagens</span>}
      </div>

      {/* ── Active photos ─────────────────────────────────────────────── */}
      {photos.length === 0 && !editing ? (
        <div className="mt-5 rounded-[1.3rem] border border-slate-900/10 bg-white p-5 text-sm leading-6 text-slate-600">
          Nenhuma imagem de anúncio foi encontrada para este produto. Gere previews no processamento do projeto antes de publicar.
        </div>
      ) : (
        <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {photos.map((photo, index) => (
            <article
              key={`${photo.href}-${photo.label}`}
              className={`overflow-hidden rounded-[1.4rem] border bg-white shadow-sm ${
                editing ? "border-blue-200" : "border-slate-900/10"
              }`}
            >
              <div className="aspect-[4/3] bg-slate-100 relative">
                <img src={photo.href} alt={`${projectName} - ${photo.label}`} className="h-full w-full object-cover" loading="lazy" />
                {editing ? (
                  <>
                    {index === 0 ? (
                      <span className="absolute left-2 top-2 rounded-full bg-orange-600 px-2 py-1 text-xs font-bold text-white shadow">
                        Principal
                      </span>
                    ) : null}
                    <div className="absolute right-2 top-2 flex flex-col gap-1">
                      <button
                        type="button"
                        title="Mover para cima"
                        disabled={index === 0}
                        onClick={() => movePhoto(index, -1)}
                        className="rounded-full bg-white/90 px-2 py-1 text-xs font-bold text-slate-800 shadow disabled:opacity-30 hover:bg-white"
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        title="Mover para baixo"
                        disabled={index === photos.length - 1}
                        onClick={() => movePhoto(index, 1)}
                        className="rounded-full bg-white/90 px-2 py-1 text-xs font-bold text-slate-800 shadow disabled:opacity-30 hover:bg-white"
                      >
                        ↓
                      </button>
                      <button
                        type="button"
                        title="Excluir esta foto do anúncio"
                        onClick={() => onHidePhoto?.(photo.href)}
                        className="rounded-full bg-red-600 px-2 py-1 text-xs font-semibold text-white shadow hover:bg-red-700"
                      >
                        ✕
                      </button>
                    </div>
                  </>
                ) : (
                  index === 0 ? (
                    <span className="absolute left-2 top-2 rounded-full bg-orange-600 px-2 py-1 text-xs font-bold text-white shadow">
                      Principal
                    </span>
                  ) : null
                )}
              </div>
              <div className="space-y-3 p-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Imagem {index + 1}</p>
                  {editing ? (
                    <input
                      value={labelOverrides[photo.href] ?? photo.label}
                      onChange={(e) => onUpdateLabel?.(photo.href, e.target.value)}
                      className="mt-1 w-full rounded-[0.7rem] border border-blue-300 px-2 py-1.5 text-sm font-semibold text-slate-950 outline-none focus:border-blue-500"
                      placeholder="Rótulo da foto"
                    />
                  ) : (
                    <h3 className="mt-1 text-sm font-semibold text-slate-950">{photo.label}</h3>
                  )}
                </div>
                {!editing ? (
                  <>
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
                  </>
                ) : null}
              </div>
            </article>
          ))}
        </div>
      )}

      {/* hidden photos are excluded from display; no restore UI — cancel editing reverts all */}

      {/* ── Extra photos (user-added) ──────────────────────────────────── */}
      {extraPhotos.length > 0 ? (
        <div className="mt-5">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Fotos extras adicionadas</p>
          <div className="mt-3 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {extraPhotos.map((ep, idx) => (
              <article key={idx} className="overflow-hidden rounded-[1.4rem] border border-blue-200 bg-white shadow-sm">
                <div className="aspect-[4/3] bg-slate-100">
                  <img src={ep.path} alt={ep.label} className="h-full w-full object-cover" loading="lazy" onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }} />
                </div>
                <div className="space-y-3 p-4">
                  {editing ? (
                    <>
                      <input
                        value={ep.label}
                        onChange={(e) => onUpdateExtra?.(idx, { label: e.target.value })}
                        className="w-full rounded-[0.7rem] border border-blue-300 px-2 py-1.5 text-sm font-semibold text-slate-950 outline-none focus:border-blue-500"
                        placeholder="Rótulo"
                      />
                      <input
                        value={ep.path}
                        onChange={(e) => onUpdateExtra?.(idx, { path: e.target.value })}
                        className="w-full rounded-[0.7rem] border border-blue-300 px-2 py-1 text-xs text-slate-700 outline-none focus:border-blue-500"
                        placeholder="URL da imagem"
                      />
                      <button
                        type="button"
                        onClick={() => onRemoveExtra?.(idx)}
                        className="w-full rounded-full border border-red-200 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-50"
                      >
                        Remover
                      </button>
                    </>
                  ) : (
                    <>
                      <h3 className="text-sm font-semibold text-slate-950">{ep.label}</h3>
                      <button
                        type="button"
                        onClick={() => downloadPhoto({ label: ep.label, href: ep.path, filename: `${safeFileName(ep.label)}.jpg` })}
                        className="w-full rounded-full bg-slate-950 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-orange-700"
                      >
                        Baixar foto
                      </button>
                    </>
                  )}
                </div>
              </article>
            ))}
          </div>
        </div>
      ) : null}

      {/* ── Add photo by URL ───────────────────────────────────────────── */}
      {editing ? (
        <div className="mt-5 rounded-[1.3rem] border border-blue-200 bg-blue-50 p-5">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-blue-700">Adicionar foto por URL</p>
          <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_0.4fr_auto]">
            <input
              value={newPhotoUrl}
              onChange={(e) => setNewPhotoUrl(e.target.value)}
              placeholder="https://... (URL pública da imagem)"
              className="rounded-[0.8rem] border border-blue-300 bg-white px-4 py-2.5 text-sm text-slate-950 outline-none focus:border-blue-500"
            />
            <input
              value={newPhotoLabel}
              onChange={(e) => setNewPhotoLabel(e.target.value)}
              placeholder="Rótulo (opcional)"
              className="rounded-[0.8rem] border border-blue-300 bg-white px-4 py-2.5 text-sm text-slate-950 outline-none focus:border-blue-500"
            />
            <button
              type="button"
              onClick={handleAddPhoto}
              disabled={!newPhotoUrl.trim()}
              className="rounded-full bg-blue-700 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-800 disabled:opacity-50"
            >
              Adicionar
            </button>
          </div>
          <p className="mt-2 text-xs text-blue-700">A URL deve ser pública e acessível. JPG, PNG e WebP são suportados.</p>
        </div>
      ) : null}
    </section>
  );
}

function EditableField({
  label,
  editing,
  value,
  onChange,
  type = "text",
  placeholder,
}: {
  label: string;
  editing: boolean;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  placeholder?: string;
}) {
  return (
    <div className="rounded-[1.2rem] border border-slate-900/10 bg-white p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">{label}</p>
      {editing ? (
        <input
          type={type}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="mt-2 w-full rounded-[0.7rem] border border-blue-300 bg-white px-3 py-2 text-sm font-semibold text-slate-950 outline-none focus:border-blue-500"
        />
      ) : (
        <p className="mt-2 text-sm font-semibold text-slate-900">{value || "—"}</p>
      )}
    </div>
  );
}

function EditableMetric({
  label,
  value,
  onChange,
  strong = false,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  strong?: boolean;
}) {
  return (
    <div className="rounded-[1.2rem] border border-blue-200 bg-white p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">{label}</p>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        step="0.01"
        min="0"
        className={`mt-2 w-full rounded-[0.7rem] border border-blue-300 bg-white px-3 py-2 text-lg font-semibold outline-none focus:border-blue-500 ${strong ? "text-orange-700" : "text-slate-950"}`}
      />
    </div>
  );
}

function EditableMarketplaceCard({
  channel,
  onUpdate,
}: {
  channel: MarketplaceAttribute;
  onUpdate: (updates: Partial<MarketplaceAttribute>) => void;
}) {
  const bulletText = (channel.bullet_points ?? []).join("\n");
  const hashtagText = (channel.hashtags ?? []).join("\n");

  return (
    <article className="rounded-[1.5rem] border border-blue-200 bg-white p-5 shadow-sm space-y-4">
      <p className="section-kicker">{channel.marketplace}</p>

      <div>
        <label className="block text-xs font-semibold uppercase tracking-[0.18em] text-slate-400 mb-1">SKU do canal</label>
        <input
          value={channel.sku ?? ""}
          onChange={(e) => onUpdate({ sku: e.target.value })}
          placeholder="Ex.: SM3D-...-ML"
          className="w-full rounded-[0.8rem] border border-blue-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-blue-500"
        />
      </div>

      <div>
        <label className="block text-xs font-semibold uppercase tracking-[0.18em] text-slate-400 mb-1">Título</label>
        <input
          value={channel.title}
          onChange={(e) => onUpdate({ title: e.target.value })}
          className="w-full rounded-[0.8rem] border border-blue-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-blue-500"
        />
      </div>

      <div>
        <label className="block text-xs font-semibold uppercase tracking-[0.18em] text-slate-400 mb-1">Categoria</label>
        <input
          value={channel.category}
          onChange={(e) => onUpdate({ category: e.target.value })}
          className="w-full rounded-[0.8rem] border border-blue-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-blue-500"
        />
      </div>

      <div>
        <label className="block text-xs font-semibold uppercase tracking-[0.18em] text-slate-400 mb-1">Descrição curta</label>
        <textarea
          value={channel.short_description ?? channel.description ?? ""}
          onChange={(e) => onUpdate({ short_description: e.target.value, description: e.target.value })}
          rows={3}
          className="w-full rounded-[0.8rem] border border-blue-300 px-3 py-2 text-sm text-slate-700 outline-none focus:border-blue-500"
        />
      </div>

      <div>
        <label className="block text-xs font-semibold uppercase tracking-[0.18em] text-slate-400 mb-1">Descrição completa</label>
        <textarea
          value={channel.full_description ?? ""}
          onChange={(e) => onUpdate({ full_description: e.target.value })}
          rows={5}
          className="w-full rounded-[0.8rem] border border-blue-300 px-3 py-2 text-sm text-slate-700 outline-none focus:border-blue-500"
        />
      </div>

      <div>
        <label className="block text-xs font-semibold uppercase tracking-[0.18em] text-slate-400 mb-1">Destaques (um por linha)</label>
        <textarea
          value={bulletText}
          onChange={(e) => onUpdate({ bullet_points: e.target.value.split("\n").filter(Boolean) })}
          rows={4}
          className="w-full rounded-[0.8rem] border border-blue-300 px-3 py-2 text-sm text-slate-700 outline-none focus:border-blue-500"
        />
      </div>

      <div>
        <label className="block text-xs font-semibold uppercase tracking-[0.18em] text-slate-400 mb-1">Hashtags / tags (uma por linha)</label>
        <textarea
          value={hashtagText}
          onChange={(e) => {
            const arr = e.target.value.split("\n").filter(Boolean);
            onUpdate({ hashtags: arr, tags: arr });
          }}
          rows={4}
          className="w-full rounded-[0.8rem] border border-blue-300 px-3 py-2 text-sm text-slate-700 outline-none focus:border-blue-500"
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-semibold uppercase tracking-[0.18em] text-slate-400 mb-1">Estoque</label>
          <input
            type="number"
            value={channel.default_stock ?? 100}
            onChange={(e) => onUpdate({ default_stock: Number(e.target.value) })}
            className="w-full rounded-[0.8rem] border border-blue-300 px-3 py-2 text-sm outline-none focus:border-blue-500"
          />
        </div>
        <div>
          <label className="block text-xs font-semibold uppercase tracking-[0.18em] text-slate-400 mb-1">Garantia (meses)</label>
          <input
            type="number"
            value={channel.warranty?.duration ?? 1}
            onChange={(e) =>
              onUpdate({
                warranty: { type: "seller", duration: Number(e.target.value), unit: "months", label: `${e.target.value} mês — garantia do vendedor` },
              })
            }
            className="w-full rounded-[0.8rem] border border-blue-300 px-3 py-2 text-sm outline-none focus:border-blue-500"
          />
        </div>
      </div>

      {(channel.registration_attributes ?? []).length > 0 ? (
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400 mb-2">Atributos de cadastro</p>
          <div className="space-y-2">
            {(channel.registration_attributes ?? []).map((attr, ai) => (
              <div key={ai} className="grid grid-cols-2 gap-2">
                <input
                  value={attr.label}
                  onChange={(e) => {
                    const attrs = [...(channel.registration_attributes ?? [])];
                    attrs[ai] = { ...attrs[ai], label: e.target.value };
                    onUpdate({ registration_attributes: attrs });
                  }}
                  className="rounded-[0.7rem] border border-blue-300 px-3 py-2 text-xs outline-none focus:border-blue-500"
                  placeholder="Atributo"
                />
                <input
                  value={attr.value}
                  onChange={(e) => {
                    const attrs = [...(channel.registration_attributes ?? [])];
                    attrs[ai] = { ...attrs[ai], value: e.target.value };
                    onUpdate({ registration_attributes: attrs });
                  }}
                  className="rounded-[0.7rem] border border-blue-300 px-3 py-2 text-xs outline-none focus:border-blue-500"
                  placeholder="Valor"
                />
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </article>
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

function collectAdPhotos(
  project: ProjectDetail,
  labelOverrides: Record<string, string> | null = null,
  hiddenPaths: string[] | null = null,
  extraPhotos: SalesProfileExtraPhoto[] | null = null,
  photoOrder: string[] | null = null,
): AdPhoto[] {
  const hiddenSet = new Set(hiddenPaths ?? []);
  const overrides = labelOverrides ?? {};
  const raw: Array<{ label: string; href: string; filename: string; score: number; signature: string }> = [];
  const addPhoto = (label: string, path?: string | null) => {
    const href = fileUrl(path);
    if (!href || !/\.(png|jpe?g|webp)(\?.*)?$/i.test(href)) return;
    if (hiddenSet.has(href)) return;
    const effectiveLabel = overrides[href] ?? label;
    raw.push({
      label: effectiveLabel,
      href,
      filename: `${safeFileName(project.name)}_${safeFileName(effectiveLabel)}.${extensionFromUrl(href)}`,
      score: adPhotoScore(label, href),
      signature: normalizePhotoSignature(label, href),
    });
  };

  addPhoto("imagem-principal", project.preview_url);
  project.previews.forEach((item) => addPhoto(item.label, item.path));
  const dedupedByHref = new Map<string, { label: string; href: string; filename: string; score: number; signature: string }>();
  raw.forEach((photo) => {
    const current = dedupedByHref.get(photo.href);
    if (!current || photo.score > current.score) dedupedByHref.set(photo.href, photo);
  });

  // Append extra user-added photos (already resolved)
  (extraPhotos ?? []).forEach((ep) => {
    const href = ep.path;
    if (!href || hiddenSet.has(href)) return;
    const effectiveLabel = overrides[href] ?? ep.label;
    if (!dedupedByHref.has(href)) {
      dedupedByHref.set(href, {
        label: effectiveLabel,
        href,
        filename: `${safeFileName(project.name)}_${safeFileName(effectiveLabel)}.jpg`,
        score: -1,
        signature: normalizePhotoSignature(effectiveLabel, href),
      });
    }
  });

  // If the user defined an explicit order, use it; otherwise fall back to score sort
  if (photoOrder && photoOrder.length > 0) {
    const orderIndex = new Map(photoOrder.map((href, i) => [href, i]));
    const inOrder = photoOrder
      .filter((href) => dedupedByHref.has(href))
      .map((href) => dedupedByHref.get(href)!);
    // Append any photos not mentioned in photoOrder at the end (sorted by score)
    const rest = Array.from(dedupedByHref.values())
      .filter((p) => !orderIndex.has(p.href))
      .sort((a, b) => b.score - a.score);
    return [...inOrder, ...rest].map((p) => ({ label: p.label, href: p.href, filename: p.filename }));
  }

  const ordered = Array.from(dedupedByHref.values()).sort((a, b) => b.score - a.score);
  const selected: AdPhoto[] = [];
  const seenSignatures = new Set<string>();
  for (const photo of ordered) {
    if (seenSignatures.has(photo.signature)) continue;
    seenSignatures.add(photo.signature);
    selected.push({ label: photo.label, href: photo.href, filename: photo.filename });
    if (selected.length >= MAX_AD_PHOTOS) break;
  }
  return selected;
}

function adPhotoScore(label: string, href: string): number {
  const value = `${label} ${href}`.toLowerCase();
  let score = 0;
  if (value.includes("marketplace_01")) score += 120;
  if (value.includes("marketplace_02")) score += 100;
  if (value.includes("marketplace_03")) score += 90;
  if (value.includes("marketplace")) score += 70;
  if (value.includes("hero")) score += 35;
  if (value.includes("lifestyle")) score += 30;
  if (value.includes("dimensions")) score += 20;
  if (value.includes("snapmaker_compatible_final")) score += 16;
  if (value.includes("plate")) score += 10;
  if (value.includes("pick")) score += 8;
  if (value.includes("top")) score += 6;
  if (value.includes("thumbnail")) score -= 12;
  if (value.includes("small")) score -= 25;
  if (value.includes("no_light")) score -= 20;
  return score;
}

function normalizePhotoSignature(label: string, href: string): string {
  const normalizedLabel = label
    .toLowerCase()
    .replace(/^marketplace_\d+_?/, "")
    .replace(/_(\d{2,3})$/, "")
    .replace(/thumbnail_(small|middle)/g, "thumbnail")
    .replace(/_small/g, "");
  const filePart = href.split("?")[0]?.split("/").pop()?.toLowerCase() || "";
  return `${normalizedLabel}::${filePart}`.replace(/[^a-z0-9:._-]+/g, "");
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
