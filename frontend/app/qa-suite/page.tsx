"use client";

import { useEffect, useRef, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { AccessDeniedPanel } from "@/components/permission-gate";
import {
  fetchQaSuiteResult,
  runQaSuiteSync,
  subscribeToQaSuiteStream,
  type QaLayerResult,
  type QaSuiteResult,
} from "@/lib/api";
import { PERMISSIONS } from "@/lib/permissions";

const LAYER_LABELS: Record<string, string> = {
  pytest: "Backend — Pytest",
  smoke: "API — Smoke Test",
  tsc: "Frontend — TypeScript",
  infra: "Infra — Checks",
};

const STATUS_STYLES: Record<string, string> = {
  passed: "text-emerald-400",
  failed: "text-red-400",
  error: "text-orange-400",
  skipped: "text-slate-400",
  never_run: "text-slate-500",
};

const STATUS_BG: Record<string, string> = {
  passed: "bg-emerald-500/10 border-emerald-500/25",
  failed: "bg-red-500/10 border-red-500/25",
  error: "bg-orange-500/10 border-orange-500/25",
  skipped: "bg-slate-500/10 border-slate-500/25",
};

function formatMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function LayerCard({ layer }: { layer: QaLayerResult }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className={`rounded-xl border p-4 ${STATUS_BG[layer.status] ?? STATUS_BG.skipped}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <span className={`text-lg font-black ${STATUS_STYLES[layer.status] ?? STATUS_STYLES.skipped}`}>
            {layer.status === "passed" ? "✓" : layer.status === "skipped" ? "—" : "✗"}
          </span>
          <div>
            <p className="text-sm font-semibold text-white">{LAYER_LABELS[layer.name] ?? layer.name}</p>
            <p className={`text-xs ${STATUS_STYLES[layer.status] ?? STATUS_STYLES.skipped}`}>
              {layer.status.toUpperCase()}
              {layer.duration_ms > 0 && ` · ${formatMs(layer.duration_ms)}`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          {(layer.passed > 0 || layer.failed > 0) && (
            <div className="text-right">
              <span className="text-emerald-400 text-sm font-semibold">{layer.passed} ok</span>
              {layer.failed > 0 && (
                <span className="ml-2 text-red-400 text-sm font-semibold">{layer.failed} falhas</span>
              )}
            </div>
          )}
          {(layer.output || layer.checks || layer.error) && (
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="text-xs text-slate-400 hover:text-white"
            >
              {expanded ? "▲ ocultar" : "▼ detalhes"}
            </button>
          )}
        </div>
      </div>
      {layer.error && (
        <p className="mt-2 rounded bg-red-900/20 px-3 py-1 text-xs text-red-300">{layer.error}</p>
      )}
      {expanded && layer.checks && (
        <div className="mt-3 space-y-1">
          {layer.checks.map((c, i) => (
            <div key={i} className="flex items-center gap-2 text-xs">
              <span className={c.ok ? "text-emerald-400" : "text-red-400"}>{c.ok ? "✓" : "✗"}</span>
              <span className="text-slate-300">{c.label}</span>
              {c.status_code && <span className="text-slate-500">HTTP {c.status_code}</span>}
              {c.error && <span className="text-red-400">{c.error}</span>}
            </div>
          ))}
        </div>
      )}
      {expanded && layer.output && (
        <pre className="mt-3 max-h-64 overflow-auto rounded bg-black/30 p-3 text-[0.65rem] text-slate-300 whitespace-pre-wrap">
          {layer.output}
        </pre>
      )}
    </div>
  );
}

export default function QaSuitePage() {
  const { can } = useAuth();
  const [result, setResult] = useState<QaSuiteResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [streamLines, setStreamLines] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [selectedLayers, setSelectedLayers] = useState<string[]>([]);
  const logRef = useRef<HTMLDivElement>(null);
  const unsubRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    void load();
    return () => { unsubRef.current?.(); };
  }, []);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [streamLines]);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchQaSuiteResult();
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao carregar resultado.");
    } finally {
      setLoading(false);
    }
  }

  async function handleRunSync() {
    setRunning(true);
    setStreaming(false);
    setStreamLines([]);
    setError(null);
    setFeedback(null);
    try {
      const res = await runQaSuiteSync(selectedLayers.length > 0 ? selectedLayers : undefined);
      setResult(res);
      setFeedback(`QA Suite concluída: ${res.overall_status.toUpperCase()} em ${formatMs(res.total_duration_ms)}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao executar QA Suite.");
    } finally {
      setRunning(false);
    }
  }

  function handleRunStream() {
    unsubRef.current?.();
    setStreaming(true);
    setStreamLines([]);
    setError(null);
    setFeedback(null);

    const unsub = subscribeToQaSuiteStream(
      (line) => setStreamLines((prev) => [...prev, line]),
      (res) => {
        setResult(res);
        setStreaming(false);
        setFeedback(`QA Suite concluída: ${res.overall_status.toUpperCase()} em ${formatMs(res.total_duration_ms)}`);
      },
    );
    unsubRef.current = unsub;
  }

  const LAYERS = ["pytest", "smoke", "tsc", "infra"];
  function toggleLayer(layer: string) {
    setSelectedLayers((prev) =>
      prev.includes(layer) ? prev.filter((l) => l !== layer) : [...prev, layer]
    );
  }

  if (!can(PERMISSIONS.usersView)) {
    return (
      <AppShell active="QA Suite">
        <AccessDeniedPanel />
      </AppShell>
    );
  }

  return (
    <AppShell active="QA Suite" title="QA Suite" subtitle="Testes automatizados para backend, frontend e infraestrutura">
      <div className="content-container py-8">
        {/* Header */}
        <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-white">Agente de Testes — QA Suite</h1>
            <p className="mt-1 text-sm text-slate-400">
              Executa pytest, smoke test de API, TypeScript typecheck e verificações de infraestrutura.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => void load()}
              disabled={loading || running}
              className="btn-ghost btn-sm"
            >
              Atualizar
            </button>
            <button
              type="button"
              onClick={handleRunStream}
              disabled={running || streaming}
              className="btn-secondary btn-sm"
            >
              {streaming ? "Executando..." : "Executar (stream)"}
            </button>
            <button
              type="button"
              onClick={() => void handleRunSync()}
              disabled={running || streaming}
              className="btn-primary btn-sm"
            >
              {running ? "Aguardando..." : "Executar (aguardar)"}
            </button>
          </div>
        </div>

        {/* Layer selector */}
        <div className="mb-5 rounded-xl border border-white/10 bg-white/5 p-4">
          <p className="mb-2 text-[0.7rem] font-semibold uppercase tracking-widest text-slate-400">
            Camadas (vazio = todas)
          </p>
          <div className="flex flex-wrap gap-2">
            {LAYERS.map((layer) => (
              <button
                key={layer}
                type="button"
                onClick={() => toggleLayer(layer)}
                className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                  selectedLayers.includes(layer)
                    ? "border-violet-500 bg-violet-500/15 text-violet-300"
                    : "border-white/10 text-slate-400 hover:border-white/30 hover:text-slate-200"
                }`}
              >
                {LAYER_LABELS[layer] ?? layer}
              </button>
            ))}
          </div>
        </div>

        {feedback && (
          <div className={`mb-4 rounded-xl border px-4 py-3 text-sm ${
            feedback.includes("passed")
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
              : "border-orange-500/30 bg-orange-500/10 text-orange-300"
          }`}>
            {feedback}
          </div>
        )}
        {error && (
          <div className="mb-4 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        {/* Stream log */}
        {(streaming || streamLines.length > 0) && (
          <div className="mb-6">
            <p className="mb-2 text-[0.7rem] font-semibold uppercase tracking-widest text-slate-400">
              Output em tempo real {streaming && <span className="animate-pulse">●</span>}
            </p>
            <div
              ref={logRef}
              className="h-64 overflow-auto rounded-xl border border-white/10 bg-black/40 p-4 font-mono text-[0.68rem] text-slate-300"
            >
              {streamLines.map((line, i) => (
                <div key={i} className={line.includes("✗") || line.includes("ERROR") || line.includes("FAIL") ? "text-red-400" : line.includes("✓") || line.includes("passed") ? "text-emerald-400" : ""}>
                  {line}
                </div>
              ))}
              {streaming && <div className="mt-1 animate-pulse text-slate-500">▋</div>}
            </div>
          </div>
        )}

        {/* Results */}
        {loading && !result ? (
          <div className="py-16 text-center text-slate-400">Carregando resultado...</div>
        ) : !result || result.overall_status === "never_run" ? (
          <div className="rounded-2xl border border-white/10 bg-white/5 p-12 text-center">
            <p className="text-slate-400">Nenhuma execução de testes ainda.</p>
            <p className="mt-2 text-sm text-slate-500">Clique em &quot;Executar&quot; para rodar o QA Suite completo.</p>
          </div>
        ) : (
          <>
            {/* Overall status */}
            <div className="mb-5 flex flex-wrap items-center gap-4 rounded-2xl border border-white/10 bg-white/5 p-5">
              <div>
                <p className="text-[0.7rem] font-semibold uppercase tracking-widest text-slate-400">Status Geral</p>
                <p className={`mt-1 text-2xl font-black ${STATUS_STYLES[result.overall_status] ?? STATUS_STYLES.skipped}`}>
                  {result.overall_status.toUpperCase()}
                </p>
              </div>
              <div>
                <p className="text-[0.7rem] font-semibold uppercase tracking-widest text-slate-400">Duração</p>
                <p className="mt-1 text-lg font-bold text-slate-200">{formatMs(result.total_duration_ms)}</p>
              </div>
              <div>
                <p className="text-[0.7rem] font-semibold uppercase tracking-widest text-slate-400">Camadas</p>
                <p className="mt-1 text-lg font-bold text-slate-200">{result.layers.length}</p>
              </div>
              {result.completed_at && (
                <div className="ml-auto text-right">
                  <p className="text-[0.65rem] text-slate-500">
                    {new Date(result.completed_at).toLocaleString("pt-BR")}
                  </p>
                </div>
              )}
            </div>

            {/* Layer cards */}
            <div className="grid gap-3">
              {result.layers.map((layer) => (
                <LayerCard key={layer.name} layer={layer} />
              ))}
            </div>
          </>
        )}
      </div>
    </AppShell>
  );
}
