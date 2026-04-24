"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { AccessDeniedPanel } from "@/components/permission-gate";
import { UploadDropzone } from "@/components/upload-dropzone";
import type { ProjectDetail } from "@/lib/api";
import { PERMISSIONS } from "@/lib/permissions";

export default function NewProjectPage() {
  const router = useRouter();
  const { can } = useAuth();
  const [lastProject, setLastProject] = useState<ProjectDetail | null>(null);

  async function handleUploaded(project?: ProjectDetail) {
    if (!project) return;
    setLastProject(project);
    router.push(`/projects/${project.id}`);
  }

  return (
    <AppShell
      active="Novo projeto"
      title="Importar projeto"
      subtitle="Envio direto, leitura segura e processamento versionado."
    >
      {!can(PERMISSIONS.projectsCreate) ? (
        <div className="portal-stack pb-12">
          <AccessDeniedPanel description="Seu perfil não possui permissão para enviar ou importar novos projetos." />
        </div>
      ) : (
        <div className="portal-stack pb-12">
          <UploadDropzone onUploaded={handleUploaded} compact />

          <section className="grid gap-4 border-t border-slate-900/8 pt-6 lg:grid-cols-[1.25fr_0.9fr]">
            <div>
              <p className="section-kicker">Fluxo</p>
              <h2 className="mt-2 text-2xl font-semibold text-slate-950 md:text-3xl">
                O portal cuida do restante após o envio
              </h2>
              <div className="mt-4 grid gap-3 md:grid-cols-3">
                <StepRow index="01" title="Validar" text="Formato, integridade e dependências." />
                <StepRow index="02" title="Catalogar" text="Versão nova sem sobrescrever arquivos." />
                <StepRow index="03" title="Processar" text="Conversão, relatório e export final." />
              </div>
            </div>

            <div className="rounded-[1.5rem] border border-slate-900/8 bg-white/55 px-5 py-5">
              <p className="section-kicker">Destino padrão</p>
              <p className="mt-3 break-words font-mono text-sm text-slate-700 md:text-base">
                ~/Downloads/Projetos3d/SnapMaker3d
              </p>
              {lastProject ? (
                <p className="mt-4 text-base text-slate-600">
                  Último projeto recebido: <span className="font-semibold text-slate-900">{lastProject.name}</span>
                </p>
              ) : (
                <p className="mt-4 text-base text-slate-600">
                  O projeto importado já segue para a tela de processamento.
                </p>
              )}
            </div>
          </section>
        </div>
      )}
    </AppShell>
  );
}

function StepRow({ index, title, text }: { index: string; title: string; text: string }) {
  return (
    <div className="rounded-[1.2rem] border border-slate-900/8 bg-white/62 px-4 py-4">
      <p className="text-sm font-semibold uppercase tracking-[0.2em] text-orange-700">{index}</p>
      <h3 className="mt-2 text-lg font-semibold text-slate-950">{title}</h3>
      <p className="mt-1 text-sm leading-6 text-slate-600 md:text-base">{text}</p>
    </div>
  );
}
