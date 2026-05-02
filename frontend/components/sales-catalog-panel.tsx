"use client";

import Link from "next/link";
import { useMemo } from "react";

import { fileUrl, type ProjectSummary, type SalesProfile } from "@/lib/api";

type Props = {
  items: ProjectSummary[];
  onSyncRequest?: () => void;
  syncing?: boolean;
};

export function SalesCatalogPanel({ items, onSyncRequest, syncing }: Props) {
  const sellableItems = useMemo(() => items.filter((item) => item.sales_profile), [items]);
  const missingCount = items.length - sellableItems.length;

  return (
    <div className="border-b border-slate-900/10 py-8">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <p className="section-kicker">Vitrine</p>
          <h2 className="mt-2 text-2xl font-semibold text-slate-950 md:text-3xl">Produtos prontos para vender</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            Cards simples para navegar rápido. Abra um produto para ver cadastro completo, preço e textos por canal.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="pill">{sellableItems.length} produtos</span>
          {onSyncRequest && missingCount > 0 && (
            <button
              type="button"
              onClick={onSyncRequest}
              disabled={syncing}
              className="rounded-full border border-amber-300 bg-amber-50 px-4 py-2 text-sm font-semibold text-amber-800 transition hover:bg-amber-100 disabled:opacity-50"
            >
              {syncing ? "Sincronizando…" : `Sincronizar fichas (${missingCount} sem ficha)`}
            </button>
          )}
        </div>
      </div>

      <div className="mt-6 divide-y divide-slate-900/10">
        {sellableItems.length === 0 ? (
          <div className="py-6 text-base text-slate-600">
            Nenhum projeto com ficha comercial disponível ainda.{" "}
            {onSyncRequest && (
              <button
                type="button"
                onClick={onSyncRequest}
                disabled={syncing}
                className="font-semibold text-amber-700 underline disabled:opacity-50"
              >
                {syncing ? "Sincronizando…" : "Gerar fichas agora"}
              </button>
            )}
          </div>
        ) : (
          sellableItems.map((project) => <SalesProjectCard key={project.id} project={project} sales={project.sales_profile!} />)
        )}
      </div>
    </div>
  );
}

function SalesProjectCard({ project, sales }: { project: ProjectSummary; sales: SalesProfile }) {
  const imageUrl = fileUrl(project.preview_url);
  const hasImagePreview = imageUrl ? /\.(png|jpe?g|webp)(\?.*)?$/i.test(imageUrl) : false;
  const firstMarketplace = sales.marketplace_attributes[0];
  const description = summarize(
    firstMarketplace?.short_description ??
      firstMarketplace?.description ??
      "Produto impresso em 3D sob demanda, com preço sugerido e ficha comercial pronta para venda.",
  );

  return (
    <article className="grid gap-6 py-7 transition hover:bg-white/35 md:grid-cols-[340px_1fr]">
      <div className="aspect-[4/3] overflow-hidden bg-slate-100">
        {hasImagePreview ? (
          <img src={imageUrl} alt={`Imagem comercial de ${project.name}`} className="h-full w-full object-cover" loading="lazy" />
        ) : (
          <div className="flex h-full items-center justify-center px-4 text-center text-sm text-slate-500">Sem imagem comercial</div>
        )}
      </div>

      <div className="space-y-5">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">{firstMarketplace?.category ?? "Produto 3D"}</p>
          <h3 className="mt-2 text-xl font-semibold leading-tight text-slate-950">{project.name}</h3>
          <p className="mt-2 text-sm leading-6 text-slate-600">{description}</p>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <PriceBox label="Preço sugerido" value={currency(sales.suggested_price_50_margin_brl)} strong />
          <PriceBox label="Revendedor" value={currency(sales.reseller_price_brl)} />
        </div>

        <div className="border-l-4 border-slate-200 pl-4 text-sm leading-6 text-slate-600">
          <p>
            {sales.estimated_material_g}g · {sales.estimated_print_hours}h · custo {currency(sales.estimated_base_cost_brl)}
          </p>
        </div>

        <Link
          href={`/catalog/${project.id}`}
          className="block rounded-full bg-slate-950 px-5 py-3 text-center text-sm font-semibold text-white transition hover:bg-orange-700"
        >
          Abrir produto
        </Link>
      </div>
    </article>
  );
}

function PriceBox({ label, value, strong = false }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="border-l border-slate-900/10 pl-4">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">{label}</p>
      <p className={`mt-1 text-lg font-semibold ${strong ? "text-orange-700" : "text-slate-950"}`}>{value}</p>
    </div>
  );
}

function currency(value: number) {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);
}

function summarize(text: string) {
  return text.length > 150 ? `${text.slice(0, 147).trim()}...` : text;
}
