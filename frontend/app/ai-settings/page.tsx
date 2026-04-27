"use client";

import { useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { AccessDeniedPanel } from "@/components/permission-gate";
import { fetchAiRuntimeSettings, updateAiRuntimeSettings, type AiProviderState, type AiRuntimeSettings } from "@/lib/api";
import { PERMISSIONS } from "@/lib/permissions";

type FormState = {
  free_ai_enabled: boolean;
  external_providers_enabled: boolean;
  provider_order: string[];
};

export default function AiSettingsPage() {
  const { can } = useAuth();
  const [settings, setSettings] = useState<AiRuntimeSettings | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  useEffect(() => {
    void loadSettings();
  }, []);

  async function loadSettings() {
    setLoading(true);
    setError(null);
    try {
      const response = await fetchAiRuntimeSettings();
      setSettings(response);
      setForm({
        free_ai_enabled: response.free_ai_enabled,
        external_providers_enabled: response.external_providers_enabled,
        provider_order: response.provider_order,
      });
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Falha ao carregar provedores externos de IA.");
    } finally {
      setLoading(false);
    }
  }

  const providerMap = useMemo(() => {
    const map = new Map<string, AiProviderState>();
    for (const item of settings?.providers ?? []) map.set(item.key, item);
    return map;
  }, [settings?.providers]);

  function isProviderSelected(key: string): boolean {
    return Boolean(form?.provider_order.includes(key));
  }

  function toggleProvider(provider: AiProviderState) {
    if (!form) return;
    if (provider.key === "ollama") return;

    const exists = form.provider_order.includes(provider.key);
    const nextOrder = exists
      ? form.provider_order.filter((item) => item !== provider.key)
      : [...form.provider_order, provider.key];
    setForm({ ...form, provider_order: nextOrder });
  }

  function moveProvider(providerKey: string, direction: "up" | "down") {
    if (!form) return;
    const index = form.provider_order.indexOf(providerKey);
    if (index < 0) return;
    const targetIndex = direction === "up" ? index - 1 : index + 1;
    if (targetIndex < 0 || targetIndex >= form.provider_order.length) return;
    const reordered = [...form.provider_order];
    [reordered[index], reordered[targetIndex]] = [reordered[targetIndex], reordered[index]];
    setForm({ ...form, provider_order: reordered });
  }

  async function handleSave() {
    if (!form) return;
    setSaving(true);
    setError(null);
    setFeedback(null);
    try {
      const response = await updateAiRuntimeSettings({
        free_ai_enabled: form.free_ai_enabled,
        external_providers_enabled: form.external_providers_enabled,
        provider_order: form.provider_order,
      });
      setSettings(response);
      setForm({
        free_ai_enabled: response.free_ai_enabled,
        external_providers_enabled: response.external_providers_enabled,
        provider_order: response.provider_order,
      });
      setFeedback("Configuração de provedores externos atualizada.");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Falha ao salvar provedores externos.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <AppShell
      active="Provedores IA"
      title="Provedores externos de IA"
      subtitle="Ative ou desative provedores externos e controle a ordem de fallback usada durante geração de conteúdo e imagens."
    >
      {!can(PERMISSIONS.aiSettingsView) ? (
        <div className="space-y-8 px-5 py-8 md:px-10 2xl:px-16">
          <AccessDeniedPanel description="Seu perfil não possui acesso às configurações de provedores externos de IA." />
        </div>
      ) : (
        <div className="space-y-8 px-5 py-8 md:px-10 2xl:px-16">
          {error ? <p className="rounded-3xl border border-red-200 bg-red-50 px-5 py-4 text-base text-red-700">{error}</p> : null}
          {feedback ? <p className="rounded-3xl border border-emerald-200 bg-emerald-50 px-5 py-4 text-base text-emerald-700">{feedback}</p> : null}

          {loading || !settings || !form ? (
            <p className="text-lg text-slate-600">Carregando configurações...</p>
          ) : (
            <>
              <section className="space-y-5 rounded-[1.8rem] border border-slate-900/10 bg-white/80 p-6">
                <h3 className="text-2xl font-semibold text-slate-950">Status global</h3>
                <label className="flex items-center justify-between gap-4 border-b border-slate-900/10 pb-4">
                  <div>
                    <p className="text-lg font-semibold text-slate-900">Motor de IA habilitado</p>
                    <p className="text-sm text-slate-600">Quando desligado, o sistema usa apenas fallback determinístico sem provedores.</p>
                  </div>
                  <input
                    type="checkbox"
                    checked={form.free_ai_enabled}
                    onChange={(event) => setForm({ ...form, free_ai_enabled: event.target.checked })}
                    className="h-5 w-5 accent-slate-950"
                    disabled={!can(PERMISSIONS.aiSettingsManage)}
                  />
                </label>

                <label className="flex items-center justify-between gap-4">
                  <div>
                    <p className="text-lg font-semibold text-slate-900">Provedores externos habilitados</p>
                    <p className="text-sm text-slate-600">Permite uso de Pollinations e Hugging Face além do Ollama local.</p>
                  </div>
                  <input
                    type="checkbox"
                    checked={form.external_providers_enabled}
                    onChange={(event) => setForm({ ...form, external_providers_enabled: event.target.checked })}
                    className="h-5 w-5 accent-slate-950"
                    disabled={!can(PERMISSIONS.aiSettingsManage)}
                  />
                </label>
              </section>

              <section className="space-y-5 rounded-[1.8rem] border border-slate-900/10 bg-white/80 p-6">
                <h3 className="text-2xl font-semibold text-slate-950">Ordem de fallback</h3>
                <p className="text-sm text-slate-600">A cadeia roda de cima para baixo até obter resposta válida. Ollama local é obrigatório.</p>
                <ul className="space-y-3">
                  {form.provider_order.map((providerKey, index) => {
                    const provider = providerMap.get(providerKey);
                    if (!provider) return null;
                    const isExternal = provider.provider_type === "external";
                    const isDisabledByGlobalToggle = isExternal && !form.external_providers_enabled;
                    return (
                      <li key={provider.key} className="flex items-center justify-between gap-4 rounded-2xl border border-slate-900/10 px-4 py-3">
                        <label className="flex min-w-0 items-start gap-3">
                          <input
                            type="checkbox"
                            checked={isProviderSelected(provider.key)}
                            disabled={provider.key === "ollama" || !can(PERMISSIONS.aiSettingsManage)}
                            onChange={() => toggleProvider(provider)}
                            className="mt-1 h-4 w-4 accent-slate-950"
                          />
                          <span>
                            <span className="block text-base font-semibold text-slate-900">
                              {provider.label}
                              {isDisabledByGlobalToggle ? (
                                <span className="ml-2 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-700">desativado globalmente</span>
                              ) : null}
                            </span>
                            <span className="text-sm text-slate-600">{provider.description}</span>
                          </span>
                        </label>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => moveProvider(provider.key, "up")}
                            disabled={index === 0 || !can(PERMISSIONS.aiSettingsManage)}
                            className="rounded-full border border-slate-900/10 px-3 py-1 text-xs font-semibold text-slate-700 disabled:opacity-40"
                          >
                            Subir
                          </button>
                          <button
                            type="button"
                            onClick={() => moveProvider(provider.key, "down")}
                            disabled={index === form.provider_order.length - 1 || !can(PERMISSIONS.aiSettingsManage)}
                            className="rounded-full border border-slate-900/10 px-3 py-1 text-xs font-semibold text-slate-700 disabled:opacity-40"
                          >
                            Descer
                          </button>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </section>

              <section className="space-y-3 rounded-[1.8rem] border border-slate-900/10 bg-white/80 p-6">
                <h3 className="text-xl font-semibold text-slate-950">Observações operacionais</h3>
                <ul className="space-y-2 text-sm leading-7 text-slate-600">
                  {settings.notes.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                  {settings.updated_at ? <li>Última atualização: {new Date(settings.updated_at).toLocaleString("pt-BR")}.</li> : null}
                </ul>
              </section>

              {can(PERMISSIONS.aiSettingsManage) ? (
                <div className="flex flex-wrap items-center gap-3">
                  <button
                    type="button"
                    onClick={() => void handleSave()}
                    disabled={saving}
                    className="rounded-full bg-slate-950 px-6 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-60"
                  >
                    {saving ? "Salvando..." : "Salvar configuração"}
                  </button>
                  <button
                    type="button"
                    onClick={() => void loadSettings()}
                    disabled={loading}
                    className="rounded-full border border-slate-900/10 bg-white px-6 py-3 text-sm font-semibold text-slate-700 transition hover:border-orange-300 hover:text-orange-700"
                  >
                    Recarregar
                  </button>
                </div>
              ) : null}
            </>
          )}
        </div>
      )}
    </AppShell>
  );
}
