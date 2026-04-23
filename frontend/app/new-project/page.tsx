"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { AppShell } from "@/components/app-shell";
import { UploadDropzone } from "@/components/upload-dropzone";
import type { ProjectDetail } from "@/lib/api";

export default function NewProjectPage() {
  const router = useRouter();
  const [lastProject, setLastProject] = useState<ProjectDetail | null>(null);

  async function handleUploaded(project?: ProjectDetail) {
    if (!project) return;
    setLastProject(project);
    router.push(`/projects/${project.id}`);
  }

  return (
    <AppShell
      active="Novo projeto"
      title="Novo projeto"
      subtitle="Entrada controlada para arquivos 3D, pacotes Bambu e recursos dependentes como OBJ, MTL e texturas."
    >
      <div className="portal-stack">
        <UploadDropzone onUploaded={handleUploaded} />

        <section className="border-b border-slate-900/10 py-8">
          <p className="section-kicker">Fluxo</p>
          <h2 className="mt-2 text-3xl font-semibold text-slate-950">O que acontece após o envio</h2>
          <div className="mt-6 space-y-4">
            <StepRow index="01" title="Validação de entrada" text="Detecta formato, integridade e dependências." />
            <StepRow index="02" title="Catálogo versionado" text="Cria projeto e subpastas sem sobrescrever arquivos." />
            <StepRow index="03" title="Processamento guiado" text="A próxima tela mostra etapas e perguntas pendentes." />
          </div>
        </section>

        <section className="border-b border-slate-900/10 py-8">
          <p className="section-kicker">Saída</p>
          <h2 className="mt-2 text-3xl font-semibold text-slate-950">Pasta obrigatória</h2>
          <p className="mt-4 break-words rounded-2xl bg-white px-5 py-4 font-mono text-base text-slate-700">
            ~/Downloads/Projetos3d/SnapMaker3d
          </p>
          {lastProject ? <p className="mt-4 text-base text-slate-600">Último projeto enviado: {lastProject.name}</p> : null}
        </section>
      </div>
    </AppShell>
  );
}

function StepRow({ index, title, text }: { index: string; title: string; text: string }) {
  return (
    <div className="border-t border-slate-900/10 py-5 first:border-t-0">
      <p className="text-sm font-semibold uppercase tracking-[0.2em] text-orange-700">{index}</p>
      <h3 className="mt-2 text-xl font-semibold text-slate-950">{title}</h3>
      <p className="mt-2 text-base leading-7 text-slate-600">{text}</p>
    </div>
  );
}
