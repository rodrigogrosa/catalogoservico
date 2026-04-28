"use client";

import { type FormEvent, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { AccessDeniedPanel, PermissionGate } from "@/components/permission-gate";
import {
  buildPublicationDraft,
  createStore,
  deleteStore,
  fetchProjects,
  fetchStoreConnectors,
  fetchStores,
  startMercadoLivreOAuth,
  type ConnectorField,
  type MarketplaceCode,
  type MarketplaceConnector,
  type ProductPublishDraft,
  type ProjectSummary,
  type StoreIntegration,
} from "@/lib/api";
import { PERMISSIONS } from "@/lib/permissions";

const marketplaceOptions: { code: MarketplaceCode; label: string }[] = [
  { code: "mercado_livre", label: "Mercado Livre" },
  { code: "shopee", label: "Shopee" },
  { code: "meta_instagram", label: "Instagram / Meta Catalog" },
  { code: "custom_store", label: "Loja própria" },
];

export default function StoresPage() {
  const { can } = useAuth();
  const [connectors, setConnectors] = useState<MarketplaceConnector[]>([]);
  const [stores, setStores] = useState<StoreIntegration[]>([]);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [selectedMarketplace, setSelectedMarketplace] = useState<MarketplaceCode>("mercado_livre");
  const [storeName, setStoreName] = useState("");
  const [accountLabel, setAccountLabel] = useState("");
  const [credentials, setCredentials] = useState<Record<string, string>>({});
  const [settingsText, setSettingsText] = useState("{}");
  const [selectedStoreId, setSelectedStoreId] = useState("");
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [draft, setDraft] = useState<ProductPublishDraft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [oauthStartingId, setOauthStartingId] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const selectedConnector = useMemo(
    () => connectors.find((connector) => connector.marketplace === selectedMarketplace),
    [connectors, selectedMarketplace],
  );
  const credentialGroups = useMemo(() => groupConnectorFields(selectedConnector?.required_credentials ?? []), [selectedConnector]);
  const mercadoLivreAuthorizationUrl = useMemo(() => {
    if (selectedMarketplace !== "mercado_livre") return "";
    const clientId = credentials.client_id?.trim();
    const redirectUri = credentials.redirect_uri?.trim();
    if (!clientId || !redirectUri) return "";
    const params = new URLSearchParams({
      response_type: "code",
      client_id: clientId,
      redirect_uri: redirectUri,
    });
    return `https://auth.mercadolivre.com.br/authorization?${params.toString()}`;
  }, [credentials.client_id, credentials.redirect_uri, selectedMarketplace]);

  async function load() {
    setError(null);
    setLoading(true);
    try {
      const [connectorItems, storeItems, projectListResp] = await Promise.all([fetchStoreConnectors(), fetchStores(), fetchProjects()]);
      const projectItems = projectListResp.items;
      setConnectors(connectorItems);
      setStores(storeItems);
      setProjects(projectItems.filter((project) => project.sales_profile));
      setSelectedStoreId((current) => current || storeItems[0]?.id || "");
      setSelectedProjectId((current) => current || projectItems.find((project) => project.sales_profile)?.id || "");
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Falha ao carregar integrações.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function handleCreateStore(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setStatus(null);
    try {
      const settings = JSON.parse(settingsText || "{}") as Record<string, unknown>;
      const created = await createStore({
        name: storeName || marketplaceOptions.find((item) => item.code === selectedMarketplace)?.label || "Nova loja",
        marketplace: selectedMarketplace,
        account_label: accountLabel || undefined,
        credentials,
        settings,
      });
      setStores((items) => [created, ...items]);
      setSelectedStoreId(created.id);
      setStoreName("");
      setAccountLabel("");
      setCredentials({});
      setSettingsText("{}");
      setStatus("Loja cadastrada.");
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Falha ao cadastrar loja.");
    }
  }

  async function handleDeleteStore(id: string) {
    setError(null);
    try {
      await deleteStore(id);
      setStores((items) => items.filter((store) => store.id !== id));
      if (selectedStoreId === id) setSelectedStoreId("");
      setStatus("Loja removida.");
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Falha ao excluir loja.");
    }
  }

  async function handleBuildDraft() {
    if (!selectedStoreId || !selectedProjectId) {
      setError("Selecione uma loja e um produto.");
      return;
    }
    setError(null);
    setDraft(null);
    try {
      setDraft(await buildPublicationDraft(selectedStoreId, selectedProjectId));
    } catch (draftError) {
      setError(draftError instanceof Error ? draftError.message : "Falha ao gerar rascunho.");
    }
  }

  async function handleStartMercadoLivreOAuth(storeId: string) {
    setError(null);
    setStatus(null);
    setOauthStartingId(storeId);
    try {
      const result = await startMercadoLivreOAuth(storeId);
      setStores((items) => items.map((item) => (item.id === result.store.id ? result.store : item)));
      setStatus(`Redirect URI preparada: ${result.redirect_uri}. Cadastre essa URL no DevCenter e autorize a conta vendedora.`);
      window.open(result.authorization_url, "_blank", "noopener,noreferrer");
    } catch (oauthError) {
      setError(oauthError instanceof Error ? oauthError.message : "Falha ao iniciar OAuth Mercado Livre.");
    } finally {
      setOauthStartingId("");
    }
  }

  return (
    <AppShell
      active="Lojas"
      title="Canais de venda e integrações"
      subtitle="Conecte marketplaces, contas e payloads de publicação em uma área comercial pensada para operação diária."
    >
      {!can(PERMISSIONS.storesView) ? (
        <div className="portal-stack">
          <AccessDeniedPanel description="Seu perfil não possui acesso à configuração de lojas e marketplaces." />
        </div>
      ) : (
      <div className="portal-stack">
        {error ? <p className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-base text-red-700">{error}</p> : null}
        {status ? <p className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-base text-emerald-800">{status}</p> : null}

        <PermissionGate permission={PERMISSIONS.storesManage}>
        <form onSubmit={handleCreateStore} className="border-b border-slate-900/10 py-8">
            <p className="section-kicker">Cadastro</p>
            <h2 className="mt-2 text-3xl font-semibold text-slate-950">Cadastrar loja do usuário logado</h2>
            <p className="mt-3 max-w-3xl text-lg leading-8 text-slate-600">
              As credenciais ficam no backend local e a tela mostra apenas máscara/status. Em produção, substitua por vault.
            </p>

            <div className="mt-6 space-y-5">
              <label className="block">
                <span className="text-base font-semibold text-slate-700">Marketplace</span>
                <select
                  value={selectedMarketplace}
                  onChange={(event) => {
                    setSelectedMarketplace(event.target.value as MarketplaceCode);
                    setCredentials({});
                  }}
                  className="mt-2 w-full rounded-[1rem] border border-slate-900/10 bg-white px-5 py-4 text-base outline-none"
                >
                  {marketplaceOptions.map((option) => (
                    <option key={option.code} value={option.code}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <TextInput label="Nome da loja" value={storeName} onChange={setStoreName} placeholder="Minha loja oficial" />
              <TextInput label="Conta / Apelido" value={accountLabel} onChange={setAccountLabel} placeholder="Conta principal" />
            </div>

            {selectedConnector ? (
              <div className="mt-6 border-t border-slate-900/10 pt-5">
                <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Contrato de integração</p>
                    <h3 className="mt-1 text-lg font-semibold text-slate-950">{selectedConnector.label}</h3>
                    <p className="mt-1 text-sm leading-6 text-slate-600">{selectedConnector.auth_type}</p>
                  </div>
                  {selectedConnector.docs_url ? (
                    <a href={selectedConnector.docs_url} target="_blank" rel="noreferrer" className="rounded-full bg-slate-950 px-4 py-2 text-sm font-semibold text-white">
                      Abrir docs
                    </a>
                  ) : null}
                </div>

                {selectedMarketplace === "mercado_livre" ? <MercadoLivreHelp authorizationUrl={mercadoLivreAuthorizationUrl} /> : null}

                <div className="mt-6 space-y-6">
                  {credentialGroups.map((group) => (
                    <section key={group.label} className="border-t border-slate-900/10 pt-5 first:border-t-0 first:pt-0">
                      <div className="mb-4 flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                        <div>
                          <h4 className="text-lg font-semibold text-slate-950">{group.label}</h4>
                          {selectedMarketplace === "mercado_livre" ? (
                            <p className="mt-1 text-sm leading-6 text-slate-600">{mercadoLivreGroupDescription(group.label)}</p>
                          ) : null}
                        </div>
                        {selectedMarketplace === "mercado_livre" && group.label.startsWith("1.") ? (
                          <a
                            href="https://developers.mercadolivre.com.br/devcenter"
                            target="_blank"
                            rel="noreferrer"
                            className="w-fit rounded-full border border-slate-900/10 px-4 py-2 text-sm font-semibold text-slate-700"
                          >
                            Abrir DevCenter
                          </a>
                        ) : null}
                      </div>
                      <div className="space-y-4">
                        {group.fields.map((field) => (
                          <TextInput
                            key={field.key}
                            helpText={field.help_text}
                            helpUrl={field.help_url}
                            label={`${field.label}${field.required ? " *" : ""}`}
                            value={credentials[field.key] ?? ""}
                            onChange={(value) => setCredentials((current) => ({ ...current, [field.key]: value }))}
                            placeholder={field.key}
                            type={field.secret ? "password" : "text"}
                          />
                        ))}
                      </div>
                    </section>
                  ))}
                </div>
              </div>
            ) : null}

            <label className="mt-5 block">
              <span className="text-base font-semibold text-slate-700">Configurações específicas em JSON</span>
              {selectedMarketplace === "mercado_livre" ? <MercadoLivreSettingsHelp /> : null}
              <textarea
                value={settingsText}
                onChange={(event) => setSettingsText(event.target.value)}
                rows={5}
                className="mt-2 w-full rounded-[1rem] border border-slate-900/10 bg-white px-5 py-4 font-mono text-sm outline-none"
                placeholder='{"category_id":"MLB1234","listing_type_id":"gold_special","brand":"Sua marca"}'
              />
            </label>

            <button type="submit" className="mt-6 rounded-full bg-slate-950 px-6 py-4 text-base font-semibold text-white">
              Cadastrar loja
            </button>
        </form>
        </PermissionGate>

        <section className="border-b border-slate-900/10 py-8">
            <p className="section-kicker">Como integra</p>
            <h2 className="mt-2 text-3xl font-semibold text-slate-950">Capacidades por marketplace</h2>
            <div className="mt-5 space-y-3">
              {connectors.map((connector) => (
	                <article key={connector.marketplace} className="border-t border-slate-900/10 py-4 first:border-t-0">
                  <div className="flex items-center justify-between gap-3">
                    <h3 className="text-base font-semibold text-slate-950">{connector.label}</h3>
                    <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">{connector.auth_type}</span>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {connector.capabilities.map((capability) => (
                      <span
                        key={capability.key}
                        className={`rounded-full px-3 py-1 text-xs font-semibold ${capability.implemented ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}
                      >
                        {capability.label}: {capability.implemented ? "pronto" : "adaptador pendente"}
                      </span>
                    ))}
                  </div>
                </article>
              ))}
            </div>
        </section>

        <section className="border-b border-slate-900/10 py-8">
          <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="section-kicker">Lojas cadastradas</p>
              <h2 className="mt-2 text-3xl font-semibold text-slate-950">Contas do usuário atual</h2>
            </div>
            <span className="pill">{loading ? "Carregando..." : `${stores.length} lojas`}</span>
          </div>

          <div className="mt-6 space-y-4">
            {stores.length === 0 && !loading ? <p className="text-base text-slate-600">Nenhuma loja cadastrada ainda.</p> : null}
            {stores.map((store) => (
		              <article key={store.id} className="border-t border-slate-900/10 py-4 first:border-t-0">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">{store.marketplace_label}</p>
                    <h3 className="mt-1 text-lg font-semibold text-slate-950">{store.name}</h3>
                    <p className="mt-1 text-sm text-slate-500">{store.account_label ?? "Sem apelido"} · {store.status}</p>
                  </div>
	                  <button type="button" onClick={() => void handleDeleteStore(store.id)} className="rounded-full border border-red-200 px-3 py-2 text-xs font-semibold text-red-700">
	                    Excluir
	                  </button>
                </div>
	                <div className="mt-4 grid gap-2 sm:grid-cols-2">
                  {store.credential_status.map((credential) => (
                    <div key={credential.key} className="rounded-2xl bg-slate-50 px-3 py-2 text-xs text-slate-600">
                      <span className="font-semibold text-slate-950">{credential.key}</span>: {credential.configured ? credential.masked_value ?? "configurado" : "pendente"}
                    </div>
                  ))}
	                </div>
                  {store.marketplace === "mercado_livre" ? (
                    <div className="mt-4 border-t border-slate-900/10 pt-4">
                      <p className="text-sm leading-6 text-slate-600">
                        OAuth Mercado Livre: {credentialConfigured(store, "access_token") ? "token configurado" : "pendente de autorização da conta vendedora"}.
                      </p>
                      {store.settings.mercado_livre_redirect_uri_to_register ? (
                        <p className="mt-2 break-words font-mono text-xs leading-5 text-slate-500">
                          Redirect URI: {String(store.settings.mercado_livre_redirect_uri_to_register)}
                        </p>
                      ) : null}
                      {store.settings.mercado_livre_notifications_url ? (
                        <p className="mt-2 break-words font-mono text-xs leading-5 text-slate-500">
                          URL de notificações: {String(store.settings.mercado_livre_notifications_url)}
                        </p>
                      ) : null}
                      <p className="mt-2 text-xs leading-5 text-slate-500">
                        Para notificações reais do Mercado Livre, essa URL precisa estar acessível publicamente na internet.
                      </p>
                      <button
                        type="button"
                        onClick={() => void handleStartMercadoLivreOAuth(store.id)}
                        className="mt-3 rounded-full bg-slate-950 px-5 py-3 text-sm font-semibold text-white"
                        disabled={oauthStartingId === store.id}
                      >
                        {oauthStartingId === store.id ? "Preparando OAuth..." : "Autorizar Mercado Livre"}
                      </button>
                    </div>
                  ) : null}
	              </article>
            ))}
          </div>
        </section>

        <section className="border-b border-slate-900/10 py-8">
          <p className="section-kicker">Publicação automática</p>
          <h2 className="mt-2 text-3xl font-semibold text-slate-950">Gerar rascunho de subida de produto</h2>
          <div className="mt-6 space-y-4">
            <select value={selectedStoreId} onChange={(event) => setSelectedStoreId(event.target.value)} className="w-full rounded-[1rem] border border-slate-900/10 bg-white px-5 py-4 text-base">
              <option value="">Selecione uma loja</option>
              {stores.map((store) => (
                <option key={store.id} value={store.id}>
                  {store.name} · {store.marketplace_label}
                </option>
              ))}
            </select>
            <select value={selectedProjectId} onChange={(event) => setSelectedProjectId(event.target.value)} className="w-full rounded-[1rem] border border-slate-900/10 bg-white px-5 py-4 text-base">
              <option value="">Selecione um produto</option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
            <button type="button" onClick={() => void handleBuildDraft()} className="rounded-[1rem] bg-slate-950 px-6 py-4 text-base font-semibold text-white">
              Gerar payload
            </button>
          </div>

          {draft ? (
            <div className="mt-6 space-y-4">
              <div className="rounded-[1.25rem] border border-slate-900/10 bg-white p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Resultado</p>
                <h3 className="mt-2 text-xl font-semibold text-slate-950">{draft.status}</h3>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  Publicação real: {draft.can_publish ? "liberada" : "bloqueada até validar credenciais, imagens públicas e adaptador final."}
                </p>
                <ListBlock title="Bloqueios" items={draft.blockers} tone="danger" />
                <ListBlock title="Próximos passos" items={draft.next_steps} />
              </div>
              <pre className="max-h-[560px] overflow-auto rounded-[1.25rem] bg-slate-950 p-5 text-sm leading-7 text-slate-100">
                {JSON.stringify(draft.payload, null, 2)}
              </pre>
            </div>
          ) : null}
        </section>
      </div>
      )}
    </AppShell>
  );
}

function TextInput({
  helpText,
  helpUrl,
  label,
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  helpText?: string;
  helpUrl?: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <label className="block">
      <span className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
        <span className="text-base font-semibold text-slate-700">{label}</span>
        {helpUrl ? (
          <a href={helpUrl} target="_blank" rel="noreferrer" className="text-sm font-semibold text-orange-700 hover:text-orange-900">
            Ajuda oficial
          </a>
        ) : null}
      </span>
      {helpText ? <span className="mt-1 block text-sm leading-6 text-slate-500">{helpText}</span> : null}
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        type={type}
        placeholder={placeholder}
        className="mt-2 w-full rounded-[1rem] border border-slate-900/10 bg-white px-5 py-4 text-base outline-none transition focus:border-orange-500"
      />
    </label>
  );
}

function MercadoLivreHelp({ authorizationUrl }: { authorizationUrl: string }) {
  return (
    <div className="mt-5 border-y border-orange-200 bg-orange-50/70 py-5">
      <p className="text-sm font-semibold uppercase tracking-[0.18em] text-orange-700">Guia Mercado Livre</p>
      <h4 className="mt-2 text-xl font-semibold text-slate-950">O que precisa para conectar a loja</h4>
      <div className="mt-4 grid gap-4 text-sm leading-6 text-slate-700 lg:grid-cols-3">
        <GuideStep
          title="1. Aplicação"
          text="Copie APP ID e Chave secreta na configuração da aplicação. Cadastre também a Redirect URI."
          href="https://developers.mercadolivre.com.br/devcenter"
          linkLabel="Abrir DevCenter"
        />
        <GuideStep
          title="2. Autorização"
          text="Autorize a aplicação com a conta vendedora principal. O retorno traz um código temporário."
          href={authorizationUrl || "https://developers.mercadolivre.com.br/en_us/authentication-and-authorization"}
          linkLabel={authorizationUrl ? "Gerar código OAuth" : "Ver OAuth"}
        />
        <GuideStep
          title="3. Token"
          text="Troque o código por access_token e refresh_token. O access_token é obrigatório para publicar."
          href="https://developers.mercadolivre.com.br/en_us/authentication-and-authorization"
          linkLabel="Ver troca por token"
        />
      </div>
      {!authorizationUrl ? (
        <p className="mt-4 text-sm leading-6 text-orange-900">
          Preencha APP ID e Redirect URI para o sistema montar o link de autorização automaticamente.
        </p>
      ) : null}
    </div>
  );
}

function GuideStep({ href, linkLabel, text, title }: { href: string; linkLabel: string; text: string; title: string }) {
  return (
    <div className="border-l border-orange-300 pl-4">
      <h5 className="font-semibold text-slate-950">{title}</h5>
      <p className="mt-1">{text}</p>
      <a href={href} target="_blank" rel="noreferrer" className="mt-3 inline-flex rounded-full bg-white px-4 py-2 font-semibold text-orange-800">
        {linkLabel}
      </a>
    </div>
  );
}

function MercadoLivreSettingsHelp() {
  const items = [
    {
      key: "category_id",
      label: "Categoria MLB",
      text: "Use o preditor de categoria pelo título do produto. Ex.: sites/MLB/domain_discovery/search?q=chaveiro%203d.",
      href: "https://developers.mercadolivre.com.br/en_us/getting-started/categories-attributes",
    },
    {
      key: "listing_type_id",
      label: "Tipo de anúncio",
      text: "Consulte quais tipos estão disponíveis para o vendedor e categoria. Normalmente gold_special equivale a Clássico.",
      href: "https://developers.mercadolivre.com.br/en_us/listing-types-item-upgrades-tutorial/",
    },
    {
      key: "attributes",
      label: "Atributos obrigatórios",
      text: "Cada categoria pode exigir atributos como marca, modelo ou GTIN. Consulte /categories/{CATEGORY_ID}/attributes.",
      href: "https://developers.mercadolivre.com.br/en_us/listing-types-item-upgrades-tutorial/attributes",
    },
  ];

  return (
    <div className="mt-3 border-y border-slate-900/10 py-4">
      <p className="text-sm leading-6 text-slate-600">
        Para Mercado Livre, o JSON abaixo guarda configurações comerciais do anúncio. Os campos mínimos do payload final incluem título,
        categoria, preço, moeda, quantidade, compra imediata, condição, tipo de anúncio e imagens.
      </p>
      <div className="mt-3 grid gap-3 lg:grid-cols-3">
        {items.map((item) => (
          <a key={item.key} href={item.href} target="_blank" rel="noreferrer" className="border-l border-slate-900/10 pl-4">
            <p className="text-sm font-semibold text-slate-950">{item.label}</p>
            <p className="mt-1 text-xs leading-5 text-slate-500">{item.text}</p>
            <p className="mt-2 text-xs font-semibold text-orange-700">Abrir documentação</p>
          </a>
        ))}
      </div>
    </div>
  );
}

function groupConnectorFields(fields: ConnectorField[]) {
  const groups = new Map<string, ConnectorField[]>();
  fields.forEach((field) => {
    const label = field.group || "Credenciais";
    groups.set(label, [...(groups.get(label) ?? []), field]);
  });
  return Array.from(groups.entries()).map(([label, groupedFields]) => ({ label, fields: groupedFields }));
}

function mercadoLivreGroupDescription(group: string) {
  if (group.startsWith("1.")) {
    return "Dados que você vê na tela Configuração da aplicação do Mercado Livre.";
  }
  if (group.startsWith("2.")) {
    return "Dados gerados depois que a conta vendedora autoriza o aplicativo via OAuth.";
  }
  if (group.startsWith("3.")) {
    return "Identificação da conta vendedora; normalmente vem no retorno do token como user_id.";
  }
  return "";
}

function credentialConfigured(store: StoreIntegration, key: string) {
  return Boolean(store.credential_status.find((credential) => credential.key === key)?.configured);
}

function ListBlock({ title, items, tone = "neutral" }: { title: string; items: string[]; tone?: "neutral" | "danger" }) {
  if (items.length === 0) return null;
  return (
    <div className="mt-4">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">{title}</p>
      <ul className="mt-2 space-y-2">
        {items.map((item) => (
          <li key={item} className={`rounded-2xl px-3 py-2 text-sm leading-6 ${tone === "danger" ? "bg-red-50 text-red-800" : "bg-slate-50 text-slate-700"}`}>
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}
