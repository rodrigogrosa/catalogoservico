"use client";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { AccessDeniedPanel } from "@/components/permission-gate";
import { PERMISSIONS } from "@/lib/permissions";

export default function AboutPage() {
  const { can } = useAuth();

  return (
    <AppShell
      active="Sobre"
      title="Sobre o portal"
      subtitle="Visão rápida de posicionamento, áreas de atuação e fluxo operacional do EuAchei3D."
    >
      {!can(PERMISSIONS.dashboardView) ? (
        <div className="portal-stack pb-12">
          <AccessDeniedPanel description="Seu perfil não possui acesso à seção Sobre." />
        </div>
      ) : (
        <div className="portal-stack pb-12">
          <section className="py-8 md:py-10">
            <div className="portal-card rounded-[1.6rem] px-6 py-6 md:px-8 md:py-8">
              <p className="section-kicker">Posicionamento</p>
              <h3 className="mt-3 text-3xl font-semibold text-slate-950">Portal de operação + catálogo + publicação</h3>
              <p className="mt-3 text-lg leading-8 text-slate-600">
                A plataforma foi desenhada para transformar um arquivo 3D em produto pronto para imprimir e pronto para vender,
                com rastreabilidade de ponta a ponta.
              </p>
            </div>
          </section>

          <section className="grid gap-6 py-2 lg:grid-cols-2">
            <TopicCard
              title="Áreas do portal"
              points={[
                "Operação: upload, processamento, diagnóstico e export.",
                "Catálogo: portfólio visual, detalhes técnicos e versão comercial.",
                "Lojas: integração com marketplace e publicação assistida.",
                "Configuração: usuários, permissões, login social e provedores de IA.",
              ]}
            />
            <TopicCard
              title="Destino padrão"
              points={[
                "Todos os artefatos gerados ficam versionados em:",
                "~/Downloads/Projetos3d/SnapMaker3d",
                "Cada projeto mantém histórico em subpastas próprias para original, processado, export, relatórios, previews e logs.",
              ]}
            />
          </section>

          <section className="grid gap-6 py-6 lg:grid-cols-2">
            <TopicCard
              title="Fluxo"
              points={[
                "1. Entrada: upload de arquivo ou importação por link.",
                "2. Análise: validação de formato, malha e metadados.",
                "3. Conversão: adaptação Bambu/Snapmaker com sanidade de parâmetros.",
                "4. Saída: geração de arquivo final, previews, manifesto e relatórios.",
                "5. Comercial: preparação de conteúdo para catálogo e marketplaces.",
              ]}
            />
            <TopicCard
              title="Fila de processamento"
              points={[
                "Cada execução é acompanhada por etapas visíveis para o usuário.",
                "Status padrão: pendente, em andamento, concluído ou atenção.",
                "A fila permite rastrear bloqueios e entender exatamente em qual etapa o projeto está.",
              ]}
            />
          </section>
        </div>
      )}
    </AppShell>
  );
}

function TopicCard({ title, points }: { title: string; points: string[] }) {
  return (
    <article className="portal-card rounded-[1.6rem] px-6 py-6 md:px-8 md:py-7">
      <p className="section-kicker">{title}</p>
      <ul className="mt-4 space-y-3 text-base leading-7 text-slate-700">
        {points.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </article>
  );
}
