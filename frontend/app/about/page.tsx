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
          {/* Posicionamento */}
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

          {/* Áreas + Destino padrão */}
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
            <div className="portal-card rounded-[1.6rem] px-6 py-6 md:px-8 md:py-7">
              <p className="section-kicker">Destino padrão</p>
              <p className="mt-4 font-mono text-sm font-medium text-slate-800">
                ~/Downloads/Projetos3d/SnapMaker3d
              </p>
              <p className="mt-3 text-base leading-7 text-slate-600">
                Todos os artefatos ficam versionados em subpastas por projeto.
                Cada versão mantém histórico separado para original, processado,
                export, relatórios, previews e logs — sem sobrescrever arquivos anteriores.
              </p>
            </div>
          </section>

          {/* Fluxo — numbered steps */}
          <section className="py-6">
            <div className="portal-card rounded-[1.6rem] px-6 py-6 md:px-8 md:py-8">
              <p className="section-kicker">Fluxo</p>
              <h3 className="mt-2 text-xl font-semibold text-slate-800">
                O portal cuida do restante após o envio
              </h3>

              <ol className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {[
                  { n: "01", title: "Validar",    desc: "Formato, integridade e dependências." },
                  { n: "02", title: "Catalogar",  desc: "Versão nova sem sobrescrever arquivos." },
                  { n: "03", title: "Converter",  desc: "Adaptação Bambu → Snapmaker com sanidade de parâmetros." },
                  { n: "04", title: "Exportar",   desc: "Geração de arquivo final, previews e manifesto." },
                  { n: "05", title: "Reportar",   desc: "Relatórios de diagnóstico e rastreabilidade." },
                  { n: "06", title: "Publicar",   desc: "Conteúdo pronto para catálogo e marketplaces." },
                ].map((step) => (
                  <li key={step.n} className="flex gap-4">
                    <span className="mt-0.5 shrink-0 font-mono text-2xl font-black leading-none text-slate-200">
                      {step.n}
                    </span>
                    <div>
                      <p className="text-sm font-semibold text-slate-900">{step.title}</p>
                      <p className="mt-1 text-sm leading-6 text-slate-500">{step.desc}</p>
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          </section>

          {/* Fila */}
          <section className="py-2">
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
