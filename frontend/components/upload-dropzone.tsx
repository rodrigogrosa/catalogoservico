"use client";

import { useRef, useState } from "react";

import { importProjectFromUrl, uploadProject, type ProjectDetail } from "@/lib/api";

type Props = {
  onUploaded: (project?: ProjectDetail) => Promise<void> | void;
  compact?: boolean;
};

const accepted = ".stl,.slt,.3mf,.obj,.mtl,.png,.jpg,.jpeg,.step,.stp,.amf,.zip";

export function UploadDropzone({ onUploaded, compact = false }: Props) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [projectName, setProjectName] = useState("");
  const [projectUrl, setProjectUrl] = useState("");
  const [dragActive, setDragActive] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFiles(files: FileList | null) {
    const incoming = files ? Array.from(files) : [];
    if (incoming.length === 0) return;
    setError(null);
    setIsUploading(true);
    try {
      const project = await uploadProject(incoming, projectName || undefined);
      setProjectName("");
      if (inputRef.current) inputRef.current.value = "";
      await onUploaded(project);
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "Falha no upload.");
    } finally {
      setIsUploading(false);
    }
  }

  async function handleImportUrl() {
    const trimmedUrl = projectUrl.trim();
    if (!trimmedUrl) {
      setError("Informe um link direto da Bambu Lab ou de download do arquivo 3D.");
      return;
    }
    if (isMakerWorldModelPageUrl(trimmedUrl)) {
      setError(makerWorldPageMessage());
      return;
    }
    setError(null);
    setIsImporting(true);
    try {
      const project = await importProjectFromUrl(trimmedUrl, projectName || undefined);
      setProjectName("");
      setProjectUrl("");
      await onUploaded(project);
    } catch (importError) {
      setError(importError instanceof Error ? importError.message : "Falha ao importar link.");
    } finally {
      setIsImporting(false);
    }
  }

  return (
    <section className="hero-panel overflow-hidden rounded-[2rem] px-6 py-7 md:px-8 md:py-8">
      <div
        className={`rounded-[1.7rem] border-2 border-dashed px-4 py-6 transition md:px-6 md:py-7 ${dragActive ? "border-orange-500 bg-orange-500/10" : "border-slate-900/10 bg-white/42"}`}
        onDragEnter={(event) => {
          event.preventDefault();
          setDragActive(true);
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => {
          event.preventDefault();
          setDragActive(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          setDragActive(false);
          void handleFiles(event.dataTransfer.files);
        }}
      >
        <div className="space-y-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-3xl">
              <p className="section-kicker">{compact ? "Novo projeto" : "Central de entrada"}</p>
              <h2 className={`mt-2 font-semibold leading-tight text-slate-950 ${compact ? "text-2xl md:text-3xl" : "text-3xl md:text-4xl"}`}>
                {compact
                  ? "Envie um arquivo ou importe por link direto."
                  : "Importe modelos, pacotes Bambu e bibliotecas dependentes."}
              </h2>
              <p className={`mt-3 text-slate-600 ${compact ? "max-w-2xl text-base leading-7" : "max-w-3xl text-base leading-7 md:text-lg"}`}>
                {compact
                  ? "STL, SLT, 3MF, OBJ/MTL, STEP, AMF e ZIP em um fluxo único, seguro e versionado."
                  : "Aceite STL, SLT, 3MF, OBJ/MTL, STEP, AMF e ZIP com uma experiência única de importação, validação e catalogação."}
              </p>
            </div>
            {isUploading || isImporting ? (
              <div className="rounded-2xl border border-orange-500/20 bg-orange-500/10 px-4 py-3 text-sm font-semibold text-orange-900">
                {isImporting ? "Importando link..." : "Enviando arquivo..."}
              </div>
            ) : null}
          </div>

          <div className={`grid gap-4 ${compact ? "xl:grid-cols-[1.2fr_0.9fr]" : ""}`}>
            <div className="space-y-4">
              <div className="grid gap-4 md:grid-cols-[1fr_auto]">
                <input
                  value={projectName}
                  onChange={(event) => setProjectName(event.target.value)}
                  placeholder="Nome do projeto"
                  className="w-full rounded-[1.25rem] border border-slate-900/10 bg-white/90 px-5 py-4 text-lg outline-none transition placeholder:text-slate-400 focus:border-orange-500"
                />
                <button
                  type="button"
                  onClick={() => inputRef.current?.click()}
                  className="rounded-[1.25rem] bg-slate-950 px-7 py-4 text-lg font-semibold text-white transition hover:bg-slate-800"
                >
                  {isUploading ? "Enviando..." : "Selecionar arquivos"}
                </button>
              </div>
              <input
                ref={inputRef}
                type="file"
                accept={accepted}
                multiple
                className="hidden"
                onChange={(event) => void handleFiles(event.target.files)}
              />

              {!compact ? (
                <div className="grid gap-3 md:grid-cols-3">
                  <InfoChip title="Fluxo seguro" text="Sanitiza 3MF, layout e parâmetros críticos antes do processamento." />
                  <InfoChip title="Rastreabilidade" text="Cada saída recebe versão própria e artefatos separados." />
                  <InfoChip title="Compatibilidade imediata" text="SLT é tratado como STL e dependências de OBJ são agrupadas." />
                </div>
              ) : (
                <div className="flex flex-wrap gap-2 text-sm text-slate-600">
                  <MinimalTag text="STL / SLT / 3MF" />
                  <MinimalTag text="OBJ + MTL + texturas" />
                  <MinimalTag text="STEP / AMF / ZIP" />
                </div>
              )}
            </div>

            <div className="rounded-[1.35rem] border border-slate-900/10 bg-white/72 p-4 md:p-5">
              <p className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-500">Importar por link</p>
              <p className="mt-2 text-lg font-semibold text-slate-950">
                {compact ? "Use URL direta do arquivo" : "Ou importar por link de download"}
              </p>
              <div className="mt-3 grid gap-3">
                <input
                  value={projectUrl}
                  onChange={(event) => setProjectUrl(event.target.value)}
                  placeholder="https://... arquivo .3mf, .stl ou .zip"
                  className="w-full rounded-[1.1rem] border border-slate-900/10 bg-white px-4 py-3 text-base outline-none transition placeholder:text-slate-400 focus:border-orange-500"
                />
                <button
                  type="button"
                  onClick={() => void handleImportUrl()}
                  disabled={isImporting || isUploading}
                  className="rounded-[1.1rem] border border-slate-900/10 bg-white px-5 py-3 text-base font-semibold text-slate-900 transition hover:border-orange-500/40 disabled:opacity-60"
                >
                  {isImporting ? "Importando..." : "Importar link"}
                </button>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-500 md:text-base">
                Links de página, como MakerWorld, podem exigir download manual do `.3mf` ou `.zip`.
              </p>
            </div>
          </div>
          {error ? (
            isMakerWorldError(error) ? (
              <MakerWorldImportHelp message={error} url={projectUrl} onSelectFile={() => inputRef.current?.click()} />
            ) : (
              <p className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-base text-red-700">{error}</p>
            )
          ) : null}
        </div>
      </div>
    </section>
  );
}

function isMakerWorldError(message: string) {
  return message.toLowerCase().includes("makerworld");
}

function isMakerWorldModelPageUrl(value: string) {
  try {
    const parsed = new URL(value);
    const host = parsed.hostname.toLowerCase();
    return (host === "makerworld.com" || host.endsWith(".makerworld.com")) && parsed.pathname.includes("/models/");
  } catch {
    return false;
  }
}

function makerWorldPageMessage() {
  return [
    "Esse link do MakerWorld abre a pagina do modelo e destaca o botao Baixar 3MF, mas nao e um link direto do arquivo.",
    "Por seguranca, o backend nao consegue usar a sessao logada do seu navegador nem receber a parte depois de #.",
    "Abra o link, baixe o .3mf ou .zip e envie o arquivo baixado pelo botao Selecionar arquivo.",
  ].join(" ");
}

function MakerWorldImportHelp({ message, onSelectFile, url }: { message: string; onSelectFile: () => void; url: string }) {
  return (
    <div className="rounded-[1.35rem] border border-orange-200 bg-orange-50 px-4 py-4 text-orange-950">
      <p className="text-sm font-semibold uppercase tracking-[0.18em] text-orange-700">Importação assistida de marketplace</p>
      <p className="mt-2 text-base leading-7">{message}</p>
      <div className="mt-4 grid gap-2 text-sm leading-6 text-orange-900 md:grid-cols-2">
        <p className="rounded-2xl bg-white/70 p-3">1. Abra o link no navegador e faça login, se necessário.</p>
        <p className="rounded-2xl bg-white/70 p-3">2. Clique em Baixar 3MF ou All files.</p>
        <p className="rounded-2xl bg-white/70 p-3">3. Envie aqui o arquivo .3mf ou .zip baixado.</p>
        <p className="rounded-2xl bg-white/70 p-3">4. Link direto terminado em .3mf/.zip continua aceito.</p>
      </div>
      <div className="mt-4 flex flex-wrap gap-3">
        {url ? (
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex rounded-full bg-slate-950 px-5 py-3 text-sm font-semibold text-white"
        >
          Abrir página do modelo
        </a>
        ) : null}
        <button
          type="button"
          onClick={onSelectFile}
          className="inline-flex rounded-full border border-orange-300 bg-white px-5 py-3 text-sm font-semibold text-orange-900"
        >
          Enviar arquivo baixado
        </button>
      </div>
    </div>
  );
}

function InfoChip({ title, text }: { title: string; text: string }) {
  return (
    <div className="rounded-[1.25rem] border border-slate-900/10 bg-white/70 px-4 py-4">
      <p className="text-sm font-semibold text-slate-900">{title}</p>
      <p className="mt-1 text-sm leading-6 text-slate-600">{text}</p>
    </div>
  );
}

function MinimalTag({ text }: { text: string }) {
  return (
    <span className="rounded-full border border-slate-900/10 bg-white/70 px-3 py-1.5 text-sm font-medium text-slate-700">
      {text}
    </span>
  );
}
