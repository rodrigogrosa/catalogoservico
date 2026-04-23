import type { ProjectMetrics } from "@/lib/project-metrics";

type Props = {
  metrics: ProjectMetrics;
  compact?: boolean;
};

export function ProjectQueuePanel({ metrics, compact = false }: Props) {
  return (
    <section className="border-b border-slate-900/10 py-8">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="section-kicker">Fila</p>
          <h2 className="mt-2 text-3xl font-semibold text-slate-950">Status atual</h2>
        </div>
        <span className="pill">{metrics.processing} rodando</span>
      </div>
      <div className="mt-6 divide-y divide-slate-900/10">
        <QueueRow label="Enviados" value={metrics.uploaded} />
        <QueueRow label="Processando" value={metrics.processing} />
        <QueueRow label="Aguardando resposta" value={metrics.awaiting} />
        <QueueRow label="Finalizados" value={metrics.completed} />
        {!compact ? <QueueRow label="Falhas" value={metrics.failed} /> : null}
        {!compact ? <QueueRow label="Em atenção" value={metrics.needsAttention} /> : null}
      </div>
    </section>
  );
}

function QueueRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between py-4">
      <span className="text-base font-semibold text-slate-700">{label}</span>
      <span className="text-2xl font-semibold text-slate-950">{value}</span>
    </div>
  );
}
