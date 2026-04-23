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
  status: "draft_ready" | "blocked" | "not_implemented";
  store_id: string;
  store_name: string;
  marketplace: MarketplaceCode;
  project_id: string;
  can_publish: boolean;
  blockers: string[];
  warnings: string[];
  payload: Record<string, unknown>;
  next_steps: string[];
};

export type StoreOAuthAuthorization = {
  store: StoreIntegration;
  authorization_url: string;
  redirect_uri: string;
  state: string;
  instructions: string[];
};

const BROWSER_API_BASE = "/api/v1";
const PUBLIC_API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? BROWSER_API_BASE;
const SERVER_API_BASE = process.env.SERVER_API_BASE_URL ?? PUBLIC_API_BASE;
const API_BASE = typeof window === "undefined" ? SERVER_API_BASE : BROWSER_API_BASE;
const ORIGIN = process.env.NEXT_PUBLIC_BACKEND_ORIGIN ?? "http://localhost:8000";

export type OAuthProviderStatus = {
  provider: string;
  label: string;
  enabled: boolean;
  auth_url?: string | null;
  reason?: string | null;
};

function authHeaders(): Record<string, string> {
  const token = getStoredAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function buildRequestUrl(path: string): string {
  return `${API_BASE}${path}`;
}

function buildDirectBackendUrl(path: string): string {
  return `${ORIGIN}/api/v1${path}`;
}

type ApiFetchOptions = {
  timeoutMs?: number;
  directToBackend?: boolean;
};

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

async function parseApiError(response: Response, fallback: string): Promise<Error> {
  const requestId = response.headers.get("x-request-id");
  try {
    const payload = await response.json();
    const detail = payload.detail ?? fallback;
    const suffix = requestId ? ` [req ${requestId}]` : "";
    return new Error(`${detail}${suffix}`);
  } catch (error) {
    if (error instanceof Error && error.message !== "Unexpected end of JSON input") {
      return error;
    }
    const suffix = requestId ? ` [req ${requestId}]` : "";
    return new Error(`${fallback}${suffix}`);
  }
}

export function fileUrl(url?: string | null): string | undefined {
  if (!url) return undefined;
  if (url.startsWith("http")) return url;
  if (typeof window !== "undefined") return url;
  return `${ORIGIN}${url}`;
}

export async function fetchProjects(): Promise<ProjectSummary[]> {
  const response = await apiFetch("/projects", { cache: "no-store", headers: authHeaders() });
  if (!response.ok) throw await parseApiError(response, "Falha ao carregar projetos");
  const data = await response.json();
  return data.items;
}

export async function fetchProject(id: string): Promise<ProjectDetail> {
  const response = await apiFetch(`/projects/${id}`, { cache: "no-store", headers: authHeaders() });
  if (!response.ok) throw await parseApiError(response, "Falha ao carregar projeto");
  return response.json();
}

export async function uploadProject(files: File[], projectName?: string): Promise<ProjectDetail> {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  if (projectName) form.append("project_name", projectName);
  const response = await apiFetch("/projects/upload", {
    method: "POST",
    headers: authHeaders(),
    body: form,
  }, {
    directToBackend: typeof window !== "undefined",
    timeoutMs: 10 * 60 * 1000,
  });
  if (!response.ok) {
    throw await parseApiError(response, "Falha ao subir arquivo");
  }
  return response.json();
}

export async function importProjectFromUrl(url: string, projectName?: string): Promise<ProjectDetail> {
  const response = await apiFetch("/projects/import-url", {
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
  const response = await apiFetch(`/projects/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!response.ok) {
    throw await parseApiError(response, "Falha ao excluir projeto");
  }
}

export async function processProject(id: string, payload: ProcessPayload): Promise<ProjectSummary> {
  const response = await apiFetch(`/projects/${id}/process`, {
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

export async function fetchProjectBundle(id: string): Promise<ArtifactReference> {
  const response = await apiFetch(`/projects/${id}/bundle`, { cache: "no-store", headers: authHeaders() });
  if (!response.ok) throw await parseApiError(response, "Falha ao gerar bundle");
  const data = await response.json();
  return data.bundle;
}

export async function compareProjects(baseId: string, otherId: string): Promise<ProjectCompareResponse> {
  const response = await apiFetch(`/projects/${baseId}/compare/${otherId}`, { cache: "no-store", headers: authHeaders() });
  if (!response.ok) throw await parseApiError(response, "Falha ao comparar versões");
  return response.json();
}

export async function loginMaster(username: string, password: string): Promise<AuthSession> {
  const response = await apiFetch("/auth/login", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) throw await parseApiError(response, "Falha ao autenticar.");
  return response.json();
}

export async function fetchCurrentUser(): Promise<AuthUser> {
  const response = await apiFetch("/auth/me", { cache: "no-store", headers: authHeaders() });
  if (!response.ok) throw await parseApiError(response, "Sessao invalida ou expirada.");
  return response.json();
}

export async function fetchOAuthProviders(): Promise<OAuthProviderStatus[]> {
  const response = await apiFetch("/auth/providers", { cache: "no-store" });
  if (!response.ok) throw await parseApiError(response, "Falha ao carregar provedores de login.");
  const payload = await response.json();
  return payload.providers;
}

export async function fetchStoreConnectors(): Promise<MarketplaceConnector[]> {
  const response = await apiFetch("/stores/connectors", { cache: "no-store", headers: authHeaders() });
  if (!response.ok) throw await parseApiError(response, "Falha ao carregar conectores de loja.");
  const payload = await response.json();
  return payload.items;
}

export async function fetchStores(): Promise<StoreIntegration[]> {
  const response = await apiFetch("/stores", { cache: "no-store", headers: authHeaders() });
  if (!response.ok) throw await parseApiError(response, "Falha ao carregar lojas.");
  const payload = await response.json();
  return payload.items;
}

export async function createStore(payload: StorePayload): Promise<StoreIntegration> {
  const response = await apiFetch("/stores", {
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

export async function deleteStore(id: string): Promise<void> {
  const response = await apiFetch(`/stores/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!response.ok) throw await parseApiError(response, "Falha ao excluir loja.");
}

export async function startMercadoLivreOAuth(storeId: string): Promise<StoreOAuthAuthorization> {
  const response = await apiFetch(`/stores/${storeId}/oauth/mercado-livre/start`, {
    method: "POST",
    headers: {
      ...authHeaders(),
      "Content-Type": "application/json",
    },
  });
  if (!response.ok) throw await parseApiError(response, "Falha ao iniciar OAuth Mercado Livre.");
  return response.json();
}

export async function buildPublicationDraft(storeId: string, projectId: string): Promise<ProductPublishDraft> {
  const response = await apiFetch(`/stores/${storeId}/publish/${projectId}`, {
    method: "POST",
    headers: {
      ...authHeaders(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ mode: "draft", stock: 1, image_base_url: process.env.NEXT_PUBLIC_BACKEND_ORIGIN ?? "http://localhost:8000" }),
  });
  if (!response.ok) throw await parseApiError(response, "Falha ao gerar rascunho de publicação.");
  return response.json();
}
