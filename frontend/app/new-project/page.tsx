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
      title="Entrada de novos projetos"
      subtitle="Receba arquivos, links e pacotes complexos em um fluxo de entrada mais limpo, guiado e pronto para operação real."
    >
      <div className="portal-stack pb-12">
        <UploadDropzone onUploaded={handleUploaded} />

        <section className="portal-card rounded-[1.8rem] px-6 py-6">
          <p className="section-kicker">Jornada de processamento</p>
          <h2 className="mt-2 text-3xl font-semibold text-slate-950">O que o portal faz depois do envio</h2>
          <div className="mt-6 grid gap-4 xl:grid-cols-3">
            <StepRow index="01" title="Validação de entrada" text="Detecta formato, integridade e dependências." />
            <StepRow index="02" title="Catálogo versionado" text="Cria projeto e subpastas sem sobrescrever arquivos." />
            <StepRow index="03" title="Processamento guiado" text="A próxima tela mostra etapas e perguntas pendentes." />
          </div>
        </section>

        <section className="portal-card rounded-[1.8rem] px-6 py-6">
          <p className="section-kicker">Destino</p>
          <h2 className="mt-2 text-3xl font-semibold text-slate-950">Biblioteca mestre de arquivos</h2>
          <p className="mt-4 break-words rounded-[1.2rem] bg-slate-950 px-5 py-4 font-mono text-base text-white">
            ~/Downloads/Projetos3d/SnapMaker3d
          </p>
          {lastProject ? <p className="mt-4 text-base text-slate-600">Último item recebido: {lastProject.name}</p> : null}
        </section>
      </div>
    </AppShell>
  );
}

function StepRow({ index, title, text }: { index: string; title: string; text: string }) {
  return (
    <div className="rounded-[1.35rem] border border-slate-900/10 bg-white/72 px-5 py-5">
      <p className="text-sm font-semibold uppercase tracking-[0.2em] text-orange-700">{index}</p>
      <h3 className="mt-2 text-xl font-semibold text-slate-950">{title}</h3>
      <p className="mt-2 text-base leading-7 text-slate-600">{text}</p>
    </div>
  );
}
