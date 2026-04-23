"use client";

import { useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import {
  fetchSocialLoginProviders,
  type SocialLoginField,
  type SocialLoginProviderConfig,
  updateSocialLoginProvider,
} from "@/lib/api";

type ProviderFormState = {
  credentials: Record<string, string>;
  redirect_uri: string;
  scopesText: string;
  login_button_enabled: boolean;
};

export default function SocialLoginPage() {
  const [providers, setProviders] = useState<SocialLoginProviderConfig[]>([]);
  const [forms, setForms] = useState<Record<string, ProviderFormState>>({});
  const [loading, setLoading] = useState(true);
  const [savingProvider, setSavingProvider] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  useEffect(() => {
    void loadProviders();
  }, []);

  async function loadProviders() {
    setLoading(true);
    setError(null);
    try {
      const response = await fetchSocialLoginProviders();
      setProviders(response);
      setForms(
        Object.fromEntries(
          response.map((provider) => [
            provider.provider,
            {
              credentials: Object.fromEntries(provider.fields.map((field) => [field.key, field.current_value ?? ""])),
              redirect_uri: provider.redirect_uri || provider.recommended_redirect_uri,
              scopesText: provider.scopes.join(", "),
              login_button_enabled: provider.login_button_enabled,
            },
          ]),
        ),
      );
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Falha ao carregar login social.");
    } finally {
      setLoading(false);
    }
  }

  function updateField(provider: string, key: string, value: string) {
    setForms((current) => ({
      ...current,
      [provider]: {
        ...current[provider],
        credentials: {
          ...current[provider]?.credentials,
          [key]: value,
        },
      },
    }));
  }

  function updateProviderState(provider: string, patch: Partial<ProviderFormState>) {
    setForms((current) => ({
      ...current,
      [provider]: {
        ...current[provider],
        ...patch,
      },
    }));
  }

  async function handleSave(provider: SocialLoginProviderConfig) {
    const form = forms[provider.provider];
    if (!form) return;

    setSavingProvider(provider.provider);
    setError(null);
    setFeedback(null);
    try {
      const updated = await updateSocialLoginProvider(provider.provider, {
        credentials: form.credentials,
        redirect_uri: form.redirect_uri,
        scopes: form.scopesText
          .split(",")
          .map((scope) => scope.trim())
          .filter(Boolean),
        login_button_enabled: form.login_button_enabled,
      });
      setProviders((current) => current.map((item) => (item.provider === updated.provider ? updated : item)));
      setForms((current) => ({
        ...current,
        [updated.provider]: {
          credentials: Object.fromEntries(updated.fields.map((field) => [field.key, field.current_value ?? current[updated.provider]?.credentials?.[field.key] ?? ""])),
          redirect_uri: updated.redirect_uri,
          scopesText: updated.scopes.join(", "),
          login_button_enabled: updated.login_button_enabled,
        },
      }));
      setFeedback(`Configuração de ${provider.label} salva.`);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : `Falha ao salvar ${provider.label}.`);
    } finally {
      setSavingProvider("");
    }
  }

  return (
    <AppShell
      active="Login social"
      title="Configuração de login social"
      subtitle="Centralize Google, Apple e Instagram em uma única tela, com redirect pronta, links oficiais e ativação controlada para a tela de login."
    >
      <div className="space-y-10 px-5 py-8 md:px-10 2xl:px-16">
        <section className="grid gap-8 border-b border-slate-900/10 pb-10 xl:grid-cols-[1.1fr_0.9fr]">
          <div>
            <p className="section-kicker">Autenticação externa</p>
            <h3 className="mt-3 text-4xl font-semibold text-slate-950">Configure sem depender de `.env` manual</h3>
            <p className="mt-4 max-w-4xl text-lg leading-8 text-slate-600">
              Esta área salva as credenciais sociais no sistema e já gera as callbacks recomendadas para o ambiente publicado.
              Deixe o botão de login desativado até concluir a configuração do provedor no painel oficial.
            </p>
          </div>
          <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-1">
            <SummaryCard title="Google" text="Client ID, Client Secret e redirect exata." />
            <SummaryCard title="Apple" text="Services ID, Team ID, Key ID e private key." />
            <SummaryCard title="Instagram" text="App ID, App Secret e redirect do app Meta." />
          </div>
        </section>

        {error ? <p className="rounded-3xl border border-red-200 bg-red-50 px-5 py-4 text-base text-red-700">{error}</p> : null}
        {feedback ? <p className="rounded-3xl border border-emerald-200 bg-emerald-50 px-5 py-4 text-base text-emerald-700">{feedback}</p> : null}

        {loading ? (
          <p className="text-lg text-slate-600">Carregando configuração social...</p>
        ) : (
          <div className="space-y-12">
            {providers.map((provider) => (
              <ProviderSection
                key={provider.provider}
                provider={provider}
                form={forms[provider.provider]}
                saving={savingProvider === provider.provider}
                onChangeField={(key, value) => updateField(provider.provider, key, value)}
                onChangeState={(patch) => updateProviderState(provider.provider, patch)}
                onSave={() => void handleSave(provider)}
              />
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}

function ProviderSection({
  provider,
  form,
  saving,
  onChangeField,
  onChangeState,
  onSave,
}: {
  provider: SocialLoginProviderConfig;
  form?: ProviderFormState;
  saving: boolean;
  onChangeField: (key: string, value: string) => void;
  onChangeState: (patch: Partial<ProviderFormState>) => void;
  onSave: () => void;
}) {
  const groupedFields = useMemo(() => {
    const groups = new Map<string, SocialLoginField[]>();
    for (const field of provider.fields) {
      const current = groups.get(field.group) ?? [];
      current.push(field);
      groups.set(field.group, current);
    }
    return Array.from(groups.entries());
  }, [provider.fields]);

  return (
    <section className="space-y-6 border-b border-slate-900/10 pb-12 last:border-0 last:pb-0">
      <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
        <div className="max-w-4xl">
          <div className="flex flex-wrap items-center gap-3">
            <h4 className="text-3xl font-semibold text-slate-950">{provider.label}</h4>
            <StatusPill status={provider.status} />
          </div>
          <p className="mt-3 text-lg leading-8 text-slate-600">{provider.reason}</p>
          <div className="mt-4 flex flex-wrap gap-3 text-sm font-semibold">
            <a className="rounded-full border border-slate-900/10 px-4 py-2 text-slate-700 hover:border-orange-400 hover:text-orange-700" href={provider.docs_url} target="_blank" rel="noreferrer">
              Documentação oficial
            </a>
            <a className="rounded-full border border-slate-900/10 px-4 py-2 text-slate-700 hover:border-orange-400 hover:text-orange-700" href={provider.console_url} target="_blank" rel="noreferrer">
              Abrir console do provedor
            </a>
            {provider.auth_url ? (
              <a className="rounded-full border border-slate-900/10 px-4 py-2 text-slate-700 hover:border-orange-400 hover:text-orange-700" href={provider.auth_url} target="_blank" rel="noreferrer">
                Testar OAuth
              </a>
            ) : null}
          </div>
        </div>

        <label className="flex items-center gap-3 rounded-full border border-slate-900/10 bg-white px-5 py-3 text-sm font-semibold text-slate-700">
          <input
            type="checkbox"
            checked={form?.login_button_enabled ?? false}
            onChange={(event) => onChangeState({ login_button_enabled: event.target.checked })}
            className="h-4 w-4 accent-slate-950"
          />
          Liberar botão na tela de login
        </label>
      </div>

      <div className="grid gap-6 xl:grid-cols-[0.7fr_1.3fr]">
        <div className="space-y-5">
          <ConfigCard label="Redirect recomendada" value={provider.recommended_redirect_uri} />
          <ConfigCard label="Redirect atual" value={form?.redirect_uri || provider.redirect_uri} editable onChange={(value) => onChangeState({ redirect_uri: value })} />
          <ConfigCard label="Escopos" value={form?.scopesText || provider.scopes.join(", ")} editable onChange={(value) => onChangeState({ scopesText: value })} helper="Separe por vírgula. O sistema converte para o formato correto do provedor." />

          <div className="rounded-[1.6rem] border border-slate-900/10 bg-white/70 p-5">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Status salvo</p>
            <div className="mt-4 space-y-3">
              {provider.credential_status.map((item) => (
                <div key={item.key} className="flex items-center justify-between gap-3 border-b border-slate-900/10 pb-3 last:border-0 last:pb-0">
                  <div>
                    <p className="text-sm font-semibold text-slate-950">{item.label}</p>
                    <p className="text-xs text-slate-500">{item.configured ? item.masked_value ?? "Configurado" : "Não configurado"}</p>
                  </div>
                  <span className={`rounded-full px-3 py-1 text-xs font-semibold ${item.configured ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
                    {item.configured ? "OK" : "Pendente"}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="space-y-6">
          {groupedFields.map(([group, fields]) => (
            <div key={group} className="grid gap-5 border border-slate-900/10 bg-white/70 p-5 md:grid-cols-2">
              <div className="md:col-span-2">
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">{group}</p>
              </div>
              {fields.map((field) => (
                <label key={field.key} className="block">
                  <span className="text-sm font-semibold text-slate-700">
                    {field.label}
                    {field.required ? <span className="ml-1 text-orange-700">*</span> : null}
                  </span>
                  <input
                    type={field.secret ? "password" : "text"}
                    value={form?.credentials?.[field.key] ?? ""}
                    placeholder={field.secret && provider.credential_status.find((item) => item.key === field.key)?.configured ? "Deixe em branco para manter o valor salvo" : field.placeholder ?? ""}
                    onChange={(event) => onChangeField(field.key, event.target.value)}
                    className="mt-2 w-full border border-slate-900/10 bg-white px-4 py-3 text-base outline-none transition focus:border-orange-500"
                  />
                  {field.help_text ? <p className="mt-2 text-sm leading-6 text-slate-500">{field.help_text}</p> : null}
                  {field.help_url ? (
                    <a href={field.help_url} target="_blank" rel="noreferrer" className="mt-2 inline-flex text-sm font-semibold text-orange-700 hover:text-orange-800">
                      Ver ajuda oficial
                    </a>
                  ) : null}
                </label>
              ))}
            </div>
          ))}

          <div className="grid gap-3 md:grid-cols-3">
            {provider.notes.map((note) => (
              <p key={note} className="border border-slate-900/10 bg-white/70 px-4 py-4 text-sm leading-6 text-slate-600">
                {note}
              </p>
            ))}
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <button
          type="button"
          onClick={onSave}
          disabled={saving}
          className="rounded-full bg-slate-950 px-6 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-60"
        >
          {saving ? "Salvando..." : `Salvar ${provider.label}`}
        </button>
        <p className="text-sm text-slate-500">
          Os segredos ficam mascarados na interface. Se o campo secreto já estiver salvo, deixe em branco para manter.
        </p>
      </div>
    </section>
  );
}

function ConfigCard({
  label,
  value,
  editable = false,
  helper,
  onChange,
}: {
  label: string;
  value: string;
  editable?: boolean;
  helper?: string;
  onChange?: (value: string) => void;
}) {
  async function handleCopy() {
    await navigator.clipboard.writeText(value);
  }

  return (
    <div className="border border-slate-900/10 bg-white/70 p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">{label}</p>
          {editable ? (
            <input
              value={value}
              onChange={(event) => onChange?.(event.target.value)}
              className="mt-3 w-full border border-slate-900/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-orange-500"
            />
          ) : (
            <p className="mt-3 break-all font-mono text-sm leading-6 text-slate-800">{value}</p>
          )}
          {helper ? <p className="mt-3 text-sm leading-6 text-slate-500">{helper}</p> : null}
        </div>
        <button type="button" onClick={() => void handleCopy()} className="rounded-full border border-slate-900/10 px-4 py-2 text-xs font-semibold text-slate-700">
          Copiar
        </button>
      </div>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const mapping: Record<string, { label: string; className: string }> = {
    not_configured: { label: "Não configurado", className: "bg-slate-100 text-slate-600" },
    partial: { label: "Parcial", className: "bg-amber-100 text-amber-700" },
    configured: { label: "Configurado", className: "bg-blue-100 text-blue-700" },
    ready_for_oauth: { label: "Pronto para teste", className: "bg-emerald-100 text-emerald-700" },
  };
  const selected = mapping[status] ?? { label: status, className: "bg-slate-100 text-slate-600" };
  return <span className={`rounded-full px-3 py-1 text-xs font-semibold ${selected.className}`}>{selected.label}</span>;
}

function SummaryCard({ title, text }: { title: string; text: string }) {
  return (
    <div className="border border-slate-900/10 bg-white/70 p-5">
      <h4 className="text-lg font-semibold text-slate-950">{title}</h4>
      <p className="mt-2 text-base leading-7 text-slate-600">{text}</p>
    </div>
  );
}
