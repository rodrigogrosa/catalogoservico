import type { ProjectSummary } from "@/lib/api";

export type ProjectMetrics = {
  awaiting: number;
  completed: number;
  processing: number;
  uploaded: number;
  failed: number;
  needsAttention: number;
  total: number;
};

export function buildProjectMetrics(items: ProjectSummary[]): ProjectMetrics {
  const processing = items.filter((item) => item.status === "processing").length;
  const awaiting = items.filter((item) => item.status === "awaiting_user").length;
  const completed = items.filter((item) => item.status === "completed").length;
  const uploaded = items.filter((item) => item.status === "uploaded").length;
  const failed = items.filter((item) => item.status === "failed").length;
  return {
    awaiting,
    completed,
    failed,
    processing,
    uploaded,
    total: items.length,
    needsAttention: awaiting + failed + items.filter((item) => item.printable_score?.level === "high").length,
  };
}

export function latestProjects(items: ProjectSummary[], limit = 6): ProjectSummary[] {
  return [...items]
    .sort((left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime())
    .slice(0, limit);
}
