"use client";

import { useEffect, useState } from "react";

import { fetchProjects, type ProjectSummary } from "@/lib/api";

export function useProjects() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function refreshProjects() {
    try {
      setError(null);
      setLoading(true);
      const items = await fetchProjects();
      setProjects(items);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Falha ao carregar projetos.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refreshProjects();
  }, []);

  return { error, loading, projects, refreshProjects };
}
