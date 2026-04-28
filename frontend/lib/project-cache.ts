/**
 * In-memory project summary cache.
 *
 * Populated whenever the catalog loads a page of projects.
 * Consumed by the project detail page to render immediately (no spinner)
 * while the full ProjectDetail fetch completes in the background.
 *
 * The cache lives in module scope (singleton per tab) and is intentionally
 * NOT persisted to sessionStorage — it only needs to survive the navigation
 * from catalog → project detail within the same SPA session.
 */

import type { ProjectDetail, ProjectSummary } from "@/lib/api";

const _cache = new Map<string, ProjectSummary>();

/** Store a batch of summaries (called after every catalog fetch). */
export function cacheProjectSummaries(items: ProjectSummary[]): void {
  for (const item of items) {
    _cache.set(item.id, item);
  }
}

/** Retrieve a cached summary, or null if not cached. */
export function getCachedProjectSummary(id: string): ProjectSummary | null {
  return _cache.get(id) ?? null;
}

/**
 * Build a ProjectDetail stub from a ProjectSummary.
 * All fields required by ProjectDetailView that are absent from ProjectSummary
 * are filled with safe empty defaults so the overview tab renders instantly.
 * The caller replaces this stub with the real response once the fetch resolves.
 */
export function summaryToPartialDetail(s: ProjectSummary): ProjectDetail {
  return {
    ...s,
    storage_path: "",
    original_filename: "",
    size_bytes: 0,
    input_files: [],
    requested_actions: [],
    findings: [],
    risks: [],
    questions_pending: [],
    blocking_questions: [],
    metadata: {},
    processing_stages: [],
    stage_metrics: [],
    decisions: [],
    artifacts: [],
    previews: [],
    reports: [],
    logs: [],
    bundles: [],
    bambu_parameter_equivalence: [],
    manifest: null,
    snapshot: null,
  };
}
