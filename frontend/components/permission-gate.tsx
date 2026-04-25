"use client";

import type { ReactNode } from "react";

import { useAuth } from "@/components/auth-provider";

export function PermissionGate({
  permission,
  fallback = null,
  children,
}: {
  permission?: string | null;
  fallback?: ReactNode;
  children: ReactNode;
}) {
  const { can } = useAuth();
  if (!can(permission)) {
    return <>{fallback}</>;
  }
  return <>{children}</>;
}

export function AccessDeniedPanel({
  title = "Acesso restrito",
  description = "Seu perfil atual não possui permissão para acessar esta área.",
}: {
  title?: string;
  description?: string;
}) {
  return (
    <section className="portal-card rounded-[1.6rem] px-6 py-8">
      <p className="section-kicker">Permissões</p>
      <h2 className="mt-3 text-3xl font-semibold text-slate-950">{title}</h2>
      <p className="mt-4 max-w-3xl text-lg leading-8 text-slate-600">{description}</p>
    </section>
  );
}
