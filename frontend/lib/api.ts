import { getStoredAuthToken, type AuthSession, type AuthUser } from "@/lib/auth-storage";

export type ProjectQuestion = {
  code: string;
  question: string;
  reason: string;
  severity: "low" | "medium" | "high";
  kind?: "informative" | "recommended" | "blocking";
};

export type ArtifactReference = {
  label: string;
  path: string;
  kind: string;
  sha256?: string | null;
  size_bytes?: number | null;
};

export type ProcessingStage = {
  key: string;
  label: string;
  status: "pending" | "in_progress" | "completed" | "failed" | "skipped" | "blocked";
  message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  duration_ms?: number | null;
};

export type PrintableScore = {
  score: number;
  level: "low" | "medium" | "high";
  blockers: string[];
  warnings: string[];
  recommendations: string[];
};

export type MarketplaceAttribute = {
  marketplace: string;
  title: string;
  category: string;
  description: string;
  short_description?: string | null;
  full_description?: string | null;
  product_context?: string | null;
  character_origin?: string | null;
  registration_attributes: { label: string; value: string }[];
  bullet_points: string[];
  hashtags: string[];
  tags: string[];
  required_fields: string[];
};

export type SalesProfile = {
  pricing_version: string;
  copy_source: string;
  estimated_material_g: number;
  estimated_print_hours: number;
  estimated_base_cost_brl: number;
  suggested_price_50_margin_brl: number;
  reseller_price_brl: number;
  default_margin_percent: number;
  reseller_margin_percent: number;
  currency: string;
  assumptions: string[];
  sales_tips: string[];
  marketplace_attributes: MarketplaceAttribute[];
};

export type InputFileRecord = {
  name: string;
  path: string;
  suffix: string;
  size_bytes: number;
  sha256?: string | null;
  role: string;
  status: string;
};

export type DecisionRecord = {
  stage_key: string;
  action: string;
  reason: string;
  impact?: string | null;
  destructive: boolean;
};

export type StageMetric = {
  stage_key: string;
  status: string;
  started_at: string;
  finished_at: string;
  duration_ms: number;
  memory_mb?: number | null;
  input_size_bytes?: number | null;
};

export type ParameterEquivalenceRecord = {
  parameter: string;
  source_value: unknown;
  target_value: unknown;
  status:
    | "preserved_exactly"
    | "preserved_approximately"
    | "fallback_substitution"
    | "discarded_incompatible"
    | "requires_user_confirmation";
  note?: string | null;
};

export type ExecutionSnapshot = {
  inputs: InputFileRecord[];
  final_parameters: Record<string, unknown>;
  agent_outputs: Record<string, unknown>[];
  prompts: Record<string, string>;
  fallbacks: string[];
  risks: string[];
  artifacts: ArtifactReference[];
};

export type ProjectManifest = {
  project_id: string;
  project_name: string;
  slug: string;
  version: number;
  created_at: string;
  updated_at: string;
  origin?: string | null;
  source_ecosystem: string;
  input_formats: string[];
  pipeline_version: string;
  agent_versions: Record<string, string>;
  original_files: Record<string, unknown>[];
  artifacts: Record<string, unknown>[];
  parameters: Record<string, unknown>;
  automatic_decisions: Record<string, unknown>[];
  questions_asked: Record<string, unknown>[];
  user_answers: Record<string, unknown>[];
  limitations: string[];
  snapshot: Record<string, unknown>;
};

export type ProjectSummary = {
  id: string;
  name: string;
  slug: string;
  version: number;
  status: string;
  input_format: string;
  source_ecosystem: string;
  created_at: string;
  updated_at: string;
  preview_url?: string | null;
  printable_score?: PrintableScore | null;
  sales_profile?: SalesProfile | null;
};

export type ProjectDetail = ProjectSummary & {
  storage_path: string;
  original_filename: string;
  size_bytes: number;
  input_files: InputFileRecord[];
  requested_actions: string[];
  findings: string[];
  risks: string[];
  questions_pending: ProjectQuestion[];
  blocking_questions: ProjectQuestion[];
  metadata: Record<string, unknown>;
  processing_stages: ProcessingStage[];
  stage_metrics: StageMetric[];
  decisions: DecisionRecord[];
  artifacts: ArtifactReference[];
  previews: ArtifactReference[];
  reports: ArtifactReference[];
  logs: ArtifactReference[];
  bundles: ArtifactReference[];
  manifest?: ProjectManifest | null;
  snapshot?: ExecutionSnapshot | null;
  bambu_parameter_equivalence: ParameterEquivalenceRecord[];
};

export type ProcessPayload = {
  repair_mesh: boolean;
  adapt_to_snapmaker: boolean;
  convert_from_bambu: boolean;
  scale_mode: "keep" | "fit_to_bed" | "normalize_units" | "ask";
  unit_mode: "auto" | "mm" | "inch" | "ask";
  hollowing: boolean;
  objective_preset: string;
  orientation_priority: "aesthetics" | "strength" | "speed" | "support_economy";
  target_nozzle_mm: number;
  supports: "auto" | "disabled" | "ask";
  target_material?: string;
  material_preferences: {
    use_case: "decorative" | "functional" | "structural" | "unknown";
    thermal_resistance?: boolean;
    outdoor_use?: boolean;
    flexibility_required?: boolean;
    desired_finish?: string;
    prioritize: "aesthetics" | "speed" | "strength" | "balanced";
  };
  color_preferences: {
    preserve_original_colors: boolean;
    character_variant?: string;
    strategy: "multicolor" | "split_parts" | "paint_after" | "undecided" | "monochrome";
    notes?: string;
  };
  hollowing_preferences: {
    enabled: boolean;
    shell_thickness_mm: number;
    drain_holes: boolean;
    preserve_strength: boolean;
  };
  transform_preferences: {
    reinforce_weak_regions: boolean;
    add_helper_base: boolean;
    simplify_microdetails: boolean;
    allow_destructive_changes: boolean;
    generate_alignment_pins: boolean;
  };
  notes?: string;
};

export type ProjectCompareResponse = {
  base_project_id: string;
  target_project_id: string;
  summary: string[];
  parameter_changes: Record<string, unknown>;
  printable_score_delta: Record<string, unknown>;
  artifacts_added: ArtifactReference[];
};

export type MarketplaceCode = "mercado_livre" | "shopee" | "meta_instagram" | "custom_store";

export type ConnectorField = {
  key: string;
  label: string;
  required: boolean;
  secret: boolean;
  help_text: string;
  help_url: string;
  group: string;
};

export type ConnectorCapability = {
  key: string;
  label: string;
  implemented: boolean;
  notes: string;
};

export type MarketplaceConnector = {
  marketplace: MarketplaceCode;
  label: string;
  docs_url: string;
  auth_type: string;
  required_credentials: ConnectorField[];
  required_product_fields: string[];
  capabilities: ConnectorCapability[];
  implementation_notes: string[];
};

export type StoreCredentialStatus = {
  key: string;
  configured: boolean;
  masked_value?: string | null;
};

export type StoreIntegration = {
  id: string;
  owner_username: string;
  name: string;
  marketplace: MarketplaceCode;
  marketplace_label: string;
  account_label?: string | null;
  status: "draft" | "configured" | "needs_credentials" | "disabled";
  country: string;
  currency: string;
  credential_status: StoreCredentialStatus[];
  settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type StorePayload = {
  name: string;
  marketplace: MarketplaceCode;
  account_label?: string;
  country?: string;
  currency?: string;
  credentials?: Record<string, string>;
  settings?: Record<string, unknown>;
};

export type ProductPublishDraft = {
  status: "draft_ready" | "blocked" | "not_implemented" | "published";
  store_id: string;
  store_name: string;
  marketplace: MarketplaceCode;
  project_id: string;
  can_publish: boolean;
  blockers: string[];
  warnings: string[];
  payload: Record<string, unknown>;
  next_steps: string[];
  published_item_id?: string | null;
  published_permalink?: string | null;
  publication_reference?: Record<string, unknown>;
};

export type StoreOAuthAuthorization = {
  store: StoreIntegration;
  authorization_url: string;
  redirect_uri: string;
  state: string;
  instructions: string[];
};

const DEFAULT_BACKEND_ORIGIN = "http://localhost:8000";

function normalizeOrigin(value?: string | null): string | null {
  if (!value) return null;
  return value.replace(/\/+$/, "");
}

function inferBrowserBackendOrigin(): string | null {
  if (typeof window === "undefined") return null;

  const { protocol, hostname } = window.location;

  if (hostname === "app.euachei3d.com.br") {
    return `${protocol}//api.euachei3d.com.br`;
  }

  if (hostname.startsWith("http--frontend--") && hostname.endsWith(".code.run")) {
    return `${protocol}//${hostname.replace("http--frontend--", "http--backend--")}`;
  }

  if (hostname === "localhost" || hostname === "127.0.0.1") {
    return normalizeOrigin(process.env.NEXT_PUBLIC_BACKEND_ORIGIN) ?? DEFAULT_BACKEND_ORIGIN;
  }

  return null;
}

function backendOrigin(): string {
  if (typeof window !== "undefined") {
    return inferBrowserBackendOrigin()
      ?? normalizeOrigin(process.env.NEXT_PUBLIC_BACKEND_ORIGIN)
      ?? DEFAULT_BACKEND_ORIGIN;
  }

  return normalizeOrigin(process.env.SERVER_BACKEND_ORIGIN)
    ?? normalizeOrigin(process.env.NEXT_PUBLIC_BACKEND_ORIGIN)
    ?? DEFAULT_BACKEND_ORIGIN;
}

function apiBase(): string {
  if (typeof window === "undefined") {
    return normalizeOrigin(process.env.SERVER_API_BASE_URL)
      ?? `${backendOrigin()}/api/v1`;
  }

  const directOrigin = inferBrowserBackendOrigin()
    ?? normalizeOrigin(process.env.NEXT_PUBLIC_BACKEND_ORIGIN);
  if (directOrigin) {
    return `${directOrigin}/api/v1`;
  }
  return "/api/v1";
}

export type OAuthProviderStatus = {
  provider: string;
  label: string;
  enabled: boolean;
  auth_url?: string | null;
  reason?: string | null;
};

export type PermissionDefinition = {
  key: string;
  label: string;
  description: string;
  category: string;
};

export type RoleDefinition = {
  key: string;
  label: string;
  description: string;
  permissions: string[];
};

export type AccessModel = {
  permissions: PermissionDefinition[];
  roles: RoleDefinition[];
};

export type UserRecord = {
  id: string;
  username: string;
  display_name: string;
  role: string;
  role_label: string;
  provider: string;
  status: string;
  permissions: string[];
  granted_permissions: string[];
  revoked_permissions: string[];
  created_at?: string | null;
  updated_at?: string | null;
  last_login_at?: string | null;
};

export type SocialLoginField = {
  key: string;
  label: string;
  required: boolean;
  secret: boolean;
  group: string;
  current_value?: string | null;
  placeholder?: string | null;
  help_text?: string | null;
  help_url?: string | null;
};

export type SocialLoginCredentialStatus = {
  key: string;
  label: string;
  configured: boolean;
  masked_value?: string | null;
};

export type SocialLoginProviderConfig = {
  provider: string;
  label: string;
  status: string;
  enabled: boolean;
  login_button_enabled: boolean;
  auth_url?: string | null;
  reason?: string | null;
  docs_url: string;
  console_url: string;
  recommended_redirect_uri: string;
  redirect_uri: string;
  callback_uri: string;
  scopes: string[];
  fields: SocialLoginField[];
  credential_status: SocialLoginCredentialStatus[];
  notes: string[];
};

export type AiProviderState = {
  key: string;
  label: string;
  provider_type: "local" | "external";
  enabled: boolean;
  description: string;
};

export type AiRuntimeSettings = {
  free_ai_enabled: boolean;
  external_providers_enabled: boolean;
  provider_order: string[];
  providers: AiProviderState[];
  updated_at?: string | null;
  notes: string[];
};

export type UserCreatePayload = {
  username: string;
  display_name: string;
  role: string;
  provider: string;
  password?: string;
  status: string;
  granted_permissions: string[];
  revoked_permissions: string[];
};

export type UserUpdatePayload = {
  display_name?: string;
  role?: string;
  password?: string;
  status?: string;
  granted_permissions?: string[];
  revoked_permissions?: string[];
};

function authHeaders(): Record<string, string> {
  const token = getStoredAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function buildRequestUrl(path: string): string {
  return `${apiBase()}${path}`;
}

function buildDirectBackendUrl(path: string): string {
  return `${backendOrigin()}/api/v1${path}`;
}

type ApiFetchOptions = {
  timeoutMs?: number;
  directToBackend?: boolean;
};

const TRANSIENT_UPSTREAM_STATUS = new Set([502, 503, 504]);

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

async function apiFetch(path: string, init?: RequestInit, options?: ApiFetchOptions): Promise<Response> {
  const url = options?.directToBackend ? buildDirectBackendUrl(path) : buildRequestUrl(path);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), options?.timeoutMs ?? 20000);

  try {
    return await fetch(url, {
      ...init,
      signal: controller.signal,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown network error";
    if (typeof window !== "undefined") {
      console.error("[SnapMaker3d] API request failed", {
        path,
        url,
        method: init?.method ?? "GET",
        message,
        directToBackend: options?.directToBackend ?? false,
      });
    }
    throw new Error(`Falha de rede em ${init?.method ?? "GET"} ${path}: ${message}`);
  } finally {
    clearTimeout(timeout);
  }
}

async function apiFetchResilient(path: string, init?: RequestInit, timeoutMs = 20000): Promise<Response> {
  let primary: Response | null = null;

  try {
    primary = await apiFetch(path, init, { timeoutMs });
  } catch (error) {
    if (typeof window !== "undefined") {
      console.warn("[SnapMaker3d] Proxy request failed before response, retrying request", {
        path,
        method: init?.method ?? "GET",
        message: error instanceof Error ? error.message : String(error),
      });
    }
  }

  if (primary && !TRANSIENT_UPSTREAM_STATUS.has(primary.status)) {
    return primary;
  }

  if (typeof window !== "undefined") {
    console.warn("[SnapMaker3d] Proxy response requires retry", {
      path,
      method: init?.method ?? "GET",
      status: primary?.status ?? null,
    });
  }

  await delay(400);

  try {
    const retry = await apiFetch(path, init, { timeoutMs });
    if (!TRANSIENT_UPSTREAM_STATUS.has(retry.status)) {
      return retry;
    }

    if (typeof window !== "undefined") {
      console.warn("[SnapMaker3d] Proxy still unstable, retrying against direct backend", {
        path,
        method: init?.method ?? "GET",
        status: retry.status,
      });
    }
  } catch (error) {
    if (typeof window !== "undefined") {
      console.warn("[SnapMaker3d] Proxy retry also failed, retrying against direct backend", {
        path,
        method: init?.method ?? "GET",
        message: error instanceof Error ? error.message : String(error),
      });
    }
  }

  return apiFetch(path, init, { timeoutMs, directToBackend: true });
}

async function uploadWithFallback(path: string, init?: RequestInit, timeoutMs = 10 * 60 * 1000): Promise<Response> {
  try {
    const proxiedResponse = await apiFetch(path, init, { timeoutMs });
    if (!proxiedResponse.ok && [502, 503, 504].includes(proxiedResponse.status)) {
      if (typeof window !== "undefined") {
        const bodySnippet = (await proxiedResponse.clone().text()).slice(0, 240);
        console.warn("[SnapMaker3d] Upload via frontend proxy returned upstream error, retrying direct backend", {
          path,
          method: init?.method ?? "POST",
          status: proxiedResponse.status,
          bodySnippet,
        });
      }
      return apiFetch(path, init, { timeoutMs, directToBackend: true });
    }
    return proxiedResponse;
  } catch (proxyError) {
    if (typeof window !== "undefined") {
      console.warn("[SnapMaker3d] Upload via frontend proxy failed, retrying direct backend", {
        path,
        method: init?.method ?? "POST",
        message: proxyError instanceof Error ? proxyError.message : String(proxyError),
      });
    }
    return apiFetch(path, init, { timeoutMs, directToBackend: true });
  }
}

async function parseApiError(response: Response, fallback: string): Promise<Error> {
  const requestId = response.headers.get("x-request-id");
  const suffix = requestId ? ` [req ${requestId}]` : "";
  try {
    const rawText = await response.text();
    if (!rawText.trim()) {
      return new Error(`${fallback}${suffix}`);
    }
    try {
      const payload = JSON.parse(rawText);
      const detail = payload.detail ?? fallback;
      return new Error(`${detail}${suffix}`);
    } catch {
      const compact = rawText.replace(/\s+/g, " ").trim();
      const message =
        compact.length > 180 ? `${compact.slice(0, 177)}...` : compact;
      return new Error(`${fallback}: ${message}${suffix}`);
    }
  } catch (error) {
    return new Error(`${fallback}${suffix}`);
  }
}

export function fileUrl(url?: string | null): string | undefined {
  if (!url) return undefined;
  if (url.startsWith("http")) return url;
  if (typeof window !== "undefined") return url;
  return `${backendOrigin()}${url}`;
}

export type ProjectListResponse = {
  items: ProjectSummary[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
};

export type ProjectListParams = {
  page?: number;
  per_page?: number;
  status?: string;
  search?: string;
  /** When true, route through the Next.js BFF (/api/catalog) instead of the backend directly. */
  bff?: boolean;
};

export async function fetchProjects(params?: ProjectListParams): Promise<ProjectListResponse> {
  const { page = 1, per_page = 20, status, search, bff = false } = params ?? {};
  const qp = new URLSearchParams({ page: String(page), per_page: String(per_page) });
  if (status) qp.set("status", status);
  if (search) qp.set("search", search);

  const url = bff
    ? `/api/catalog?${qp.toString()}`
    : `/projects?${qp.toString()}`;

  const response = await apiFetchResilient(url, { cache: "no-store", headers: authHeaders() }, 60000);
  if (!response.ok) throw await parseApiError(response, "Falha ao carregar projetos");
  return response.json();
}

export async function fetchProject(id: string): Promise<ProjectDetail> {
  const response = await apiFetchResilient(`/projects/${id}`, { cache: "no-store", headers: authHeaders() }, 90000);
  if (!response.ok) throw await parseApiError(response, "Falha ao carregar projeto");
  return response.json();
}

export async function uploadProject(files: File[], projectName?: string): Promise<ProjectDetail> {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  if (projectName) form.append("project_name", projectName);
  const response = await uploadWithFallback("/projects/upload", {
    method: "POST",
    headers: authHeaders(),
    body: form,
  });
  if (!response.ok) {
    throw await parseApiError(response, "Falha ao subir arquivo");
  }
  return response.json();
}

export async function importProjectFromUrl(url: string, projectName?: string): Promise<ProjectDetail> {
  const response = await apiFetchResilient("/projects/import-url", {
    method: "POST",
    headers: {
      ...authHeaders(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ url, project_name: projectName || undefined }),
  });
  if (!response.ok) {
    throw await parseApiError(response, "Falha ao importar link");
  }
  return response.json();
}

export async function deleteProject(id: string): Promise<void> {
  const response = await apiFetchResilient(`/projects/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!response.ok) {
    throw await parseApiError(response, "Falha ao excluir projeto");
  }
}

export async function processProject(id: string, payload: ProcessPayload): Promise<ProjectSummary> {
  const response = await apiFetchResilient(`/projects/${id}/process`, {
    method: "POST",
    headers: {
      ...authHeaders(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw await parseApiError(response, "Falha ao iniciar processamento");
  return response.json();
}

export async function reprocessProject(id: string, payload: ProcessPayload): Promise<ProjectDetail> {
  const response = await apiFetchResilient(`/projects/${id}/reprocess`, {
    method: "POST",
    headers: {
      ...authHeaders(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw await parseApiError(response, "Falha ao criar nova versão para reprocessamento");
  return response.json();
}

export async function fetchProjectVersions(id: string): Promise<ProjectSummary[]> {
  const response = await apiFetchResilient(`/projects/${id}/versions`, {
    cache: "no-store",
    headers: authHeaders(),
  });
  if (!response.ok) throw await parseApiError(response, "Falha ao carregar versões do projeto");
  return response.json();
}

export async function fetchProjectBundle(id: string): Promise<ArtifactReference> {
  const response = await apiFetchResilient(`/projects/${id}/bundle`, { cache: "no-store", headers: authHeaders() });
  if (!response.ok) throw await parseApiError(response, "Falha ao gerar bundle");
  const data = await response.json();
  return data.bundle;
}

export async function fetchProjectPrintFile(id: string): Promise<ArtifactReference> {
  const response = await apiFetchResilient(`/projects/${id}/print-file`, { cache: "no-store", headers: authHeaders() });
  if (!response.ok) throw await parseApiError(response, "Falha ao localizar arquivo final para impressão");
  const data = await response.json();
  return data.print_file;
}

export async function compareProjects(baseId: string, otherId: string): Promise<ProjectCompareResponse> {
  const response = await apiFetchResilient(`/projects/${baseId}/compare/${otherId}`, { cache: "no-store", headers: authHeaders() });
  if (!response.ok) throw await parseApiError(response, "Falha ao comparar versões");
  return response.json();
}

export async function loginMaster(username: string, password: string): Promise<AuthSession> {
  const response = await apiFetchResilient("/auth/login", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ username, password }),
  }, 25000);
  if (!response.ok) throw await parseApiError(response, "Falha ao autenticar.");
  return response.json();
}

export async function fetchCurrentUser(): Promise<AuthUser> {
  const response = await apiFetchResilient("/auth/me", { cache: "no-store", headers: authHeaders() });
  if (!response.ok) throw await parseApiError(response, "Sessao invalida ou expirada.");
  return response.json();
}

export async function fetchAccessModel(): Promise<AccessModel> {
  const response = await apiFetchResilient("/auth/access-model", { cache: "no-store", headers: authHeaders() });
  if (!response.ok) throw await parseApiError(response, "Falha ao carregar modelo de permissões.");
  return response.json();
}

export async function fetchOAuthProviders(): Promise<OAuthProviderStatus[]> {
  const response = await apiFetchResilient("/auth/providers", { cache: "no-store" });
  if (!response.ok) throw await parseApiError(response, "Falha ao carregar provedores de login.");
  const payload = await response.json();
  return payload.providers;
}

export async function fetchSocialLoginProviders(): Promise<SocialLoginProviderConfig[]> {
  const response = await apiFetchResilient("/auth/social-config", { cache: "no-store", headers: authHeaders() });
  if (!response.ok) throw await parseApiError(response, "Falha ao carregar configuração de login social.");
  const payload = await response.json();
  return payload.providers;
}

export async function updateSocialLoginProvider(
  provider: string,
  payload: {
    credentials?: Record<string, string>;
    redirect_uri?: string;
    scopes?: string[];
    login_button_enabled?: boolean;
  },
): Promise<SocialLoginProviderConfig> {
  const response = await apiFetchResilient(`/auth/social-config/${provider}`, {
    method: "PUT",
    headers: {
      ...authHeaders(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw await parseApiError(response, "Falha ao salvar configuração de login social.");
  return response.json();
}

export async function fetchAiRuntimeSettings(): Promise<AiRuntimeSettings> {
  const response = await apiFetchResilient("/ai-settings", { cache: "no-store", headers: authHeaders() });
  if (!response.ok) throw await parseApiError(response, "Falha ao carregar provedores externos de IA.");
  return response.json();
}

export async function updateAiRuntimeSettings(payload: {
  free_ai_enabled?: boolean;
  external_providers_enabled?: boolean;
  provider_order?: string[];
}): Promise<AiRuntimeSettings> {
  const response = await apiFetchResilient("/ai-settings", {
    method: "PUT",
    headers: {
      ...authHeaders(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw await parseApiError(response, "Falha ao salvar provedores externos de IA.");
  return response.json();
}

export async function fetchUsers(): Promise<UserRecord[]> {
  const response = await apiFetchResilient("/users", { cache: "no-store", headers: authHeaders() });
  if (!response.ok) throw await parseApiError(response, "Falha ao carregar usuários.");
  const payload = await response.json();
  return payload.items;
}

export async function createUser(payload: UserCreatePayload): Promise<UserRecord> {
  const response = await apiFetchResilient("/users", {
    method: "POST",
    headers: {
      ...authHeaders(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw await parseApiError(response, "Falha ao criar usuário.");
  return response.json();
}

export async function updateUser(provider: string, username: string, payload: UserUpdatePayload): Promise<UserRecord> {
  const response = await apiFetchResilient(`/users/${provider}/${encodeURIComponent(username)}`, {
    method: "PUT",
    headers: {
      ...authHeaders(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw await parseApiError(response, "Falha ao atualizar usuário.");
  return response.json();
}

export async function deleteUser(provider: string, username: string): Promise<void> {
  const response = await apiFetchResilient(`/users/${provider}/${encodeURIComponent(username)}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!response.ok) throw await parseApiError(response, "Falha ao excluir usuário.");
}

export async function fetchStoreConnectors(): Promise<MarketplaceConnector[]> {
  const response = await apiFetchResilient("/stores/connectors", { cache: "no-store", headers: authHeaders() });
  if (!response.ok) throw await parseApiError(response, "Falha ao carregar conectores de loja.");
  const payload = await response.json();
  return payload.items;
}

export async function fetchStores(): Promise<StoreIntegration[]> {
  const response = await apiFetchResilient("/stores", { cache: "no-store", headers: authHeaders() });
  if (!response.ok) throw await parseApiError(response, "Falha ao carregar lojas.");
  const payload = await response.json();
  return payload.items;
}

export async function createStore(payload: StorePayload): Promise<StoreIntegration> {
  const response = await apiFetchResilient("/stores", {
    method: "POST",
    headers: {
      ...authHeaders(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw await parseApiError(response, "Falha ao cadastrar loja.");
  return response.json();
}

export async function updateStore(id: string, payload: Partial<StorePayload> & { status?: "draft" | "configured" | "needs_credentials" | "disabled" }): Promise<StoreIntegration> {
  const response = await apiFetchResilient(`/stores/${id}`, {
    method: "PUT",
    headers: {
      ...authHeaders(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw await parseApiError(response, "Falha ao atualizar loja.");
  return response.json();
}

export async function deleteStore(id: string): Promise<void> {
  const response = await apiFetchResilient(`/stores/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!response.ok) throw await parseApiError(response, "Falha ao excluir loja.");
}

export async function startMercadoLivreOAuth(storeId: string): Promise<StoreOAuthAuthorization> {
  const response = await apiFetchResilient(`/stores/${storeId}/oauth/mercado-livre/start`, {
    method: "POST",
    headers: {
      ...authHeaders(),
      "Content-Type": "application/json",
    },
  });
  if (!response.ok) throw await parseApiError(response, "Falha ao iniciar OAuth Mercado Livre.");
  return response.json();
}

export async function buildPublicationDraft(
  storeId: string,
  projectId: string,
  options?: { mode?: "draft" | "validate" | "publish"; stock?: number },
): Promise<ProductPublishDraft> {
  const response = await apiFetchResilient(`/stores/${storeId}/publish/${projectId}`, {
    method: "POST",
    headers: {
      ...authHeaders(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ mode: options?.mode ?? "draft", stock: options?.stock ?? 1, image_base_url: backendOrigin() }),
  });
  if (!response.ok) throw await parseApiError(response, "Falha ao gerar rascunho de publicação.");
  return response.json();
}
