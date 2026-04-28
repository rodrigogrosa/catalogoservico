"use client";

import { useCallback, useEffect, useState } from "react";

import { fetchProjects, type ProjectListParams, type ProjectListResponse, type ProjectSummary } from "@/lib/api";
import { cacheProjectSummaries } from "@/lib/project-cache";

type UseProjectsOptions = ProjectListParams;

export function useProjects(options?: UseProjectsOptions) {
  const { page = 1, per_page = 20, status, search } = options ?? {};

  const [response, setResponse] = useState<ProjectListResponse>({
    items: [],
    total: 0,
    page: 1,
    per_page,
    pages: 1,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refreshProjects = useCallback(async () => {
    try {
      setError(null);
      setLoading(true);
      const data = await fetchProjects({ page, per_page, status, search });
      setResponse(data);
      // Warm the project-detail cache so navigating to a project detail
      // page renders instantly without a loading spinner.
      cacheProjectSummaries(data.items);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Falha ao carregar projetos.");
    } finally {
      setLoading(false);
    }
  }, [page, per_page, status, search]);

  useEffect(() => {
    void refreshProjects();
  }, [refreshProjects]);

  return {
    error,
    loading,
    // Backward-compat: expose flat `projects` array so existing consumers don't break.
    projects: response.items,
    total: response.total,
    pages: response.pages,
    currentPage: response.page,
    refreshProjects,
  };
}
