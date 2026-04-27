"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { AccessDeniedPanel } from "@/components/permission-gate";
import { SalesProductDetail } from "@/components/sales-product-detail";
import { fetchProject, type ProjectDetail } from "@/lib/api";
import { PERMISSIONS } from "@/lib/permissions";

export function CatalogProductPageClient({ id }: { id: string }) {
  const { can } = useAuth();
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void fetchProject(id)
      .then((result) => {
        setProject(result);
        setError(null);
      })
      .catch((loadError) => setError(loadError instanceof Error ? loadError.message : "Falha ao carregar produto."))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <AppShell active="Catálogo" title="Carregando produto" subtitle="Buscando ficha comercial.">
        <section className="panel p-6 text-base text-slate-700">Carregando ficha comercial...</section>
      </AppShell>
    );
  }

  if (!can(PERMISSIONS.catalogView)) {
    return (
      <AppShell active="Catálogo" title="Acesso restrito" subtitle="Seu perfil não tem permissão para abrir a ficha comercial.">
        <AccessDeniedPanel description="Seu perfil não possui acesso ao catálogo comercial." />
      </AppShell>
    );
  }

  if (!project || error) {
    return (
      <AppShell active="Catálogo" title="Produto indisponível" subtitle="Não foi possível carregar a ficha comercial.">
        <div className="mx-auto max-w-3xl space-y-6">
          <Link href="/catalog" className="text-sm font-semibold text-orange-700 underline">
            Voltar para o catálogo
          </Link>
          <section className="panel p-6 md:p-8">
            <p className="section-kicker">Produto indisponível</p>
            <h1 className="mt-3 text-3xl font-semibold text-slate-950">A ficha comercial não abriu.</h1>
            <p className="mt-4 text-base leading-7 text-slate-700">{error ?? "Produto não encontrado."}</p>
          </section>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell active="Catálogo" title={project.name} subtitle="Ficha comercial completa para venda em marketplaces e redes sociais.">
      <div className="mx-auto max-w-7xl space-y-5">
        <Link href="/catalog" className="text-sm font-semibold text-orange-700 underline">
          Voltar para o catálogo
        </Link>
        <SalesProductDetail project={project} />
      </div>
    </AppShell>
  );
}
