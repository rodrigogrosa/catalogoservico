"use client";

import { useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { AccessDeniedPanel } from "@/components/permission-gate";
import {
  fetchReviewReport,
  triggerReview,
  triggerReviewSync,
  type ReviewFinding,
  type ReviewReport,
} from "@/lib/api";
import { PERMISSIONS } from "@/lib/permissions";

const SEVERITY_STYLES: Record<string, string> = {
  critical: "bg-red-500/15 text-red-300 border-red-500/30",
  high: "bg-orange-500/15 text-orange-300 border-orange-500/30",
  medium: "bg-yellow-500/15 text-yellow-300 border-yellow-500/30",
  low: "bg-slate-500/15 text-slate-300 border-slate-500/30",
};

const CATEGORY_LABEL: Record<string, string> = {
  error: "Erro",
  performance: "Performance",
  scalability: "Escalabilidade",
  test: "Testes",
  quality: "Qualidade",
  security: "Segurança",
};

function healthColor(score: number | null): string {
  if (score === null) return "text-slate-400";
  if (score >= 80) return "text-emerald-400";
  if (score >= 60) return "text-yellow-400";
  if (score >= 40) return "text-orange-400";
  return "text-red-400";
}

function FindingCard({ finding }: { finding: ReviewFinding }) {
  return (
    <div className={`rounded-xl border p-4 ${SEVERITY_STYLES[finding.severity] ?? SEVERITY_STYLES.low}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <span className="text-sm font-semibold">{finding.title}</span>
        <div className="flex gap-2 shrink-0">
          <span className="rounded-full border px-2 py-0.5 text-[0.65rem] font-semibold uppercase tracking-wide">
            {finding.severity}
          </span>
          <span className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[0.65rem] text-slate-400">
            {CATEGORY_LABEL[finding.category] ?? finding.category}
          </span>
        </div>
      </div>
      <p className="mt-1 text-xs text-slate-300">{finding.detail}</p>
      <p className="mt-2 text-xs text-slate-400">
        <span className="font-medium text-slate-300">Sugestão: </span>
        {finding.suggestion}
      </p>
      {finding.source && (
        <p className="mt-1 text-[0.65rem] text-slate-500">Fonte: {finding.source}</p>
      )}
    </div>
  );
}

export default function ReviewPage() {
  const { can } = useAuth();
  const [report, setReport] = useState<ReviewReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filterSeverity, setFilterSeverity] = useState<string>("all");
  const [filterCategory, setFilterCategory] = useState<string>("all");

  useEffect(() => {
    void load();
  }, []);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchReviewReport();
      setReport(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao carregar relatório.");
    } finally {
      setLoading(false);
    }
  }

  async function handleTrigger(sync: boolean) {
    setTriggering(true);
    setFeedback(null);
    setError(null);
    try {
      if (sync) {
        const result = await triggerReviewSync();
        setReport(result);
        setFeedback("Revisão completa concluída.");
      } else {
        await triggerReview();
        setFeedback("Revisão iniciada em background. Atualize a página em ~30 segundos.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao iniciar revisão.");
    } finally {
      setTriggering(false);
    }
  }

  if (!can(PERMISSIONS.usersView)) {
    return (
      <AppShell active="Revisor">
        <AccessDeniedPanel />
      </AppShell>
    );
  }

  const findings = report?.findings ?? [];
  const filteredFindings = findings.filter((f) => {
    const severityOk = filterSeverity === "all" || f.severity === filterSeverity;
    const categoryOk = filterCategory === "all" || f.category === filterCategory;
    return severityOk && categoryOk;
  });

  const criticalCount = findings.filter((f) => f.severity === "critical").length;
  const highCount = findings.filter((f) => f.severity === "high").length;
  const mediumCount = findings.filter((f) => f.severity === "medium").length;
  const lowCount = findings.filter((f) => f.severity === "low").length;

  return (
    <AppShell active="Revisor" title="Super Revisor de Qualidade" subtitle="Análise contínua de saúde, performance e escalabilidade do sistema">
      <div className="content-container py-8">
        {/* Header */}
        <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-white">Super Revisor de Qualidade</h1>
            <p className="mt-1 text-sm text-slate-400">
              O agente revisor monitora logs, manifests e performance e executa melhorias automáticas a cada 30 minutos.
            </p>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => void load()}
              disabled={loading}
              className="btn-ghost btn-sm"
            >
              {loading ? "Carregando..." : "Atualizar"}
            </button>
            <button
              type="button"
              onClick={() => void handleTrigger(false)}
              disabled={triggering}
              className="btn-secondary btn-sm"
            >
              {triggering ? "Iniciando..." : "Revisar agora (bg)"}
            </button>
            <button
              type="button"
              onClick={() => void handleTrigger(true)}
              disabled={triggering}
              className="btn-primary btn-sm"
            >
              {triggering ? "Analisando..." : "Revisar agora (aguardar)"}
            </button>
          </div>
        </div>

        {feedback && (
          <div className="mb-4 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300">
            {feedback}
          </div>
        )}
        {error && (
          <div className="mb-4 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        {loading && !report ? (
          <div className="py-16 text-center text-slate-400">Carregando relatório...</div>
        ) : !report || report.health_score === null ? (
          <div className="rounded-2xl border border-white/10 bg-white/5 p-12 text-center">
            <p className="text-slate-400">Nenhuma revisão foi executada ainda.</p>
            <p className="mt-2 text-sm text-slate-500">Clique em &quot;Revisar agora&quot; para iniciar a primeira análise.</p>
          </div>
        ) : (
          <>
            {/* Scoreboard */}
            <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-6">
              <div className="col-span-2 rounded-2xl border border-white/10 bg-white/5 p-5">
                <p className="text-[0.7rem] font-semibold uppercase tracking-widest text-slate-400">Saúde Geral</p>
                <p className={`mt-2 text-4xl font-black ${healthColor(report.health_score)}`}>
                  {report.health_score}
                  <span className="text-lg font-normal text-slate-400">/100</span>
                </p>
                <p className="mt-1 text-xs text-slate-400">Provedor: {report.provider}</p>
              </div>
              {[
                { label: "Críticos", count: criticalCount, style: "text-red-400" },
                { label: "Altos", count: highCount, style: "text-orange-400" },
                { label: "Médios", count: mediumCount, style: "text-yellow-400" },
                { label: "Baixos", count: lowCount, style: "text-slate-400" },
              ].map((item) => (
                <div key={item.label} className="rounded-2xl border border-white/10 bg-white/5 p-5">
                  <p className="text-[0.7rem] font-semibold uppercase tracking-widest text-slate-400">{item.label}</p>
                  <p className={`mt-2 text-3xl font-black ${item.style}`}>{item.count}</p>
                </div>
              ))}
            </div>

            {/* Summary */}
            <div className="mb-6 rounded-2xl border border-white/10 bg-white/5 p-5">
              <p className="text-[0.7rem] font-semibold uppercase tracking-widest text-slate-400 mb-2">Resumo</p>
              <p className="text-sm text-slate-200">{report.summary}</p>
              {report.priority_actions.length > 0 && (
                <div className="mt-4">
                  <p className="text-[0.7rem] font-semibold uppercase tracking-widest text-slate-400 mb-2">Ações Prioritárias</p>
                  <ul className="space-y-1">
                    {report.priority_actions.map((action, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-slate-300">
                        <span className="mt-0.5 shrink-0 text-emerald-400">→</span>
                        {action}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {report.auto_fixes_applied.length > 0 && (
                <div className="mt-4">
                  <p className="text-[0.7rem] font-semibold uppercase tracking-widest text-slate-400 mb-2">Correções Automáticas Aplicadas</p>
                  <ul className="space-y-1">
                    {report.auto_fixes_applied.map((fix, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-emerald-300">
                        <span className="mt-0.5 shrink-0">✓</span>
                        {fix}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            {/* Filters */}
            {findings.length > 0 && (
              <div className="mb-4 flex flex-wrap gap-2">
                <select
                  value={filterSeverity}
                  onChange={(e) => setFilterSeverity(e.target.value)}
                  className="select-field"
                >
                  <option value="all">Severidade: todas</option>
                  <option value="critical">Crítica</option>
                  <option value="high">Alta</option>
                  <option value="medium">Média</option>
                  <option value="low">Baixa</option>
                </select>
                <select
                  value={filterCategory}
                  onChange={(e) => setFilterCategory(e.target.value)}
                  className="select-field"
                >
                  <option value="all">Categoria: todas</option>
                  {Object.entries(CATEGORY_LABEL).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
                <span className="self-center text-xs text-slate-500">
                  {filteredFindings.length} de {findings.length} achados
                </span>
              </div>
            )}

            {/* Findings */}
            {filteredFindings.length === 0 ? (
              <div className="rounded-2xl border border-white/10 bg-white/5 p-8 text-center text-slate-400">
                {findings.length === 0
                  ? "Nenhum problema identificado. Sistema saudável."
                  : "Nenhum achado corresponde aos filtros selecionados."}
              </div>
            ) : (
              <div className="grid gap-3">
                {filteredFindings.map((finding, i) => (
                  <FindingCard key={i} finding={finding} />
                ))}
              </div>
            )}

            {/* Stats footer */}
            {report.raw_stats && Object.keys(report.raw_stats).length > 0 && (
              <div className="mt-6 rounded-2xl border border-white/10 bg-white/5 p-4">
                <p className="mb-2 text-[0.7rem] font-semibold uppercase tracking-widest text-slate-400">Estatísticas</p>
                <div className="flex flex-wrap gap-4">
                  {Object.entries(report.raw_stats).map(([k, v]) => (
                    <div key={k}>
                      <p className="text-[0.65rem] text-slate-500">{k}</p>
                      <p className="text-sm font-semibold text-slate-300">{String(v)}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <p className="mt-4 text-[0.68rem] text-slate-500">
              Última revisão: {report.completed_at ? new Date(report.completed_at).toLocaleString("pt-BR") : "—"}
            </p>
          </>
        )}
      </div>
    </AppShell>
  );
}
