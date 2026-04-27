"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { AccessDeniedPanel, PermissionGate } from "@/components/permission-gate";
import {
  createUser,
  deleteUser,
  fetchAccessModel,
  fetchUsers,
  updateUser,
  type AccessModel,
  type UserCreatePayload,
  type UserRecord,
  type UserUpdatePayload,
} from "@/lib/api";
import { PERMISSIONS } from "@/lib/permissions";

type FormState = {
  username: string;
  display_name: string;
  role: string;
  provider: string;
  status: string;
  password: string;
  granted_permissions: string[];
  revoked_permissions: string[];
};

const emptyForm: FormState = {
  username: "",
  display_name: "",
  role: "viewer",
  provider: "local",
  status: "active",
  password: "",
  granted_permissions: [],
  revoked_permissions: [],
};

export default function UsersPage() {
  const { can, user } = useAuth();
  const isMaster = user?.role === "master";
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [accessModel, setAccessModel] = useState<AccessModel | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [editingUser, setEditingUser] = useState<UserRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void load();
  }, []);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [access, items] = await Promise.all([fetchAccessModel(), fetchUsers()]);
      setAccessModel(access);
      setUsers(items);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Falha ao carregar usuários.");
    } finally {
      setLoading(false);
    }
  }

  function resetForm() {
    setEditingUser(null);
    setForm(emptyForm);
  }

  function startEdit(record: UserRecord) {
    setEditingUser(record);
    setForm({
      username: record.username,
      display_name: record.display_name,
      role: record.role,
      provider: record.provider,
      status: record.status,
      password: "",
      granted_permissions: record.granted_permissions,
      revoked_permissions: record.revoked_permissions,
    });
  }

  function togglePermission(key: string, listKey: "granted_permissions" | "revoked_permissions") {
    setForm((current) => {
      const currentList = current[listKey];
      const nextList = currentList.includes(key)
        ? currentList.filter((item) => item !== key)
        : [...currentList, key];
      const oppositeKey = listKey === "granted_permissions" ? "revoked_permissions" : "granted_permissions";
      return {
        ...current,
        [listKey]: nextList,
        [oppositeKey]: current[oppositeKey].filter((item) => item !== key),
      };
    });
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setStatusMessage(null);
    try {
      if (editingUser) {
        const payload: UserUpdatePayload = {
          display_name: form.display_name,
          role: form.role,
          status: form.status,
          granted_permissions: form.granted_permissions,
          revoked_permissions: form.revoked_permissions,
          password: form.password || undefined,
        };
        const updated = await updateUser(editingUser.provider, editingUser.username, payload);
        setUsers((current) => current.map((item) => (item.id === updated.id ? updated : item)));
        setStatusMessage(`Usuário ${updated.display_name} atualizado.`);
      } else {
        const payload: UserCreatePayload = {
          username: form.username,
          display_name: form.display_name,
          role: form.role,
          provider: form.provider,
          status: form.status,
          password: form.password || undefined,
          granted_permissions: form.granted_permissions,
          revoked_permissions: form.revoked_permissions,
        };
        const created = await createUser(payload);
        setUsers((current) => [created, ...current]);
        setStatusMessage(`Usuário ${created.display_name} criado.`);
      }
      resetForm();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Falha ao salvar usuário.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(record: UserRecord) {
    const confirmed = window.confirm(`Excluir ${record.display_name}?`);
    if (!confirmed) return;
    setError(null);
    setStatusMessage(null);
    try {
      await deleteUser(record.provider, record.username);
      setUsers((current) => current.filter((item) => item.id !== record.id));
      if (editingUser?.id === record.id) resetForm();
      setStatusMessage(`Usuário ${record.display_name} excluído.`);
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Falha ao excluir usuário.");
    }
  }

  const permissionGroups = useMemo(() => {
    if (!accessModel) return [];
    const groups = new Map<string, AccessModel["permissions"]>();
    for (const permission of accessModel.permissions) {
      const current = groups.get(permission.category) ?? [];
      current.push(permission);
      groups.set(permission.category, current);
    }
    return Array.from(groups.entries());
  }, [accessModel]);

  return (
    <AppShell
      active="Usuários"
      title="Usuários, papéis e permissões"
      subtitle="Toda tela, ação e componente sensível do portal deve ser controlado por permissão explícita."
    >
      {!can(PERMISSIONS.usersView) ? (
        <div className="portal-stack pb-12">
          <AccessDeniedPanel description="Seu perfil não possui acesso à administração de usuários e permissionamento." />
        </div>
      ) : (
        <div className="portal-stack pb-12">
          {error ? <p className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-base text-red-700">{error}</p> : null}
          {statusMessage ? <p className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-base text-emerald-800">{statusMessage}</p> : null}

          <section className="portal-card rounded-[1.8rem] px-6 py-6">
            <p className="section-kicker">Modelo de acesso</p>
            <h2 className="mt-2 text-3xl font-semibold text-slate-950">Papéis padrão e overrides pontuais</h2>
            <p className="mt-3 max-w-4xl text-lg leading-8 text-slate-600">
              O papel define o baseline. Permissões concedidas e revogadas ajustam exceções sem quebrar o padrão do sistema.
            </p>
          </section>

          <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
            <PermissionGate
              permission={PERMISSIONS.usersManage}
              fallback={
                <section className="portal-card rounded-[1.8rem] px-6 py-6">
                  <AccessDeniedPanel
                    title="Modo leitura"
                    description="Seu perfil pode visualizar usuários, mas não pode alterar permissões."
                  />
                </section>
              }
            >
              {isMaster ? (
                <form onSubmit={handleSubmit} className="portal-card rounded-[1.8rem] px-6 py-6">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="section-kicker">{editingUser ? "Editar usuário" : "Novo usuário"}</p>
                    <h2 className="mt-2 text-3xl font-semibold text-slate-950">
                      {editingUser ? editingUser.display_name : "Cadastrar acesso"}
                    </h2>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {editingUser ? (
                      <button type="button" onClick={resetForm} className="portal-action">
                        Novo usuário
                      </button>
                    ) : null}
                    <button type="button" onClick={resetForm} className="portal-action">
                      Limpar formulário
                    </button>
                  </div>
                </div>

                <div className="mt-6 rounded-[1.2rem] border border-slate-900/10 bg-white/80 p-4">
                  <FieldSelect
                    label="Escolher usuário para editar níveis de permissão"
                    value={editingUser?.id ?? ""}
                    onChange={(value) => {
                      if (!value) {
                        resetForm();
                        return;
                      }
                      const selected = users.find((item) => item.id === value);
                      if (selected) startEdit(selected);
                    }}
                    options={[
                      { value: "", label: "Criar novo usuário" },
                      ...users.map((item) => ({
                        value: item.id,
                        label: `${item.display_name} (${item.username})`,
                      })),
                    ]}
                  />
                  <p className="mt-2 text-sm text-slate-500">
                    Selecione um usuário para editar permissões. Para criar, mantenha “Criar novo usuário”.
                  </p>
                </div>

                <div className="mt-6 grid gap-4 md:grid-cols-2">
                  <TextInput label="Nome de login" value={form.username} disabled={Boolean(editingUser)} onChange={(value) => setForm((current) => ({ ...current, username: value }))} />
                  <TextInput label="Nome de exibição" value={form.display_name} onChange={(value) => setForm((current) => ({ ...current, display_name: value }))} />
                  <FieldSelect label="Papel base" value={form.role} onChange={(value) => setForm((current) => ({ ...current, role: value }))} options={(accessModel?.roles ?? []).map((role) => ({ value: role.key, label: role.label }))} />
                  <FieldSelect
                    label="Provedor"
                    value={form.provider}
                    disabled={Boolean(editingUser)}
                    onChange={(value) => setForm((current) => ({ ...current, provider: value }))}
                    options={[
                      { value: "local", label: "Local" },
                      { value: "google", label: "Google" },
                      { value: "apple", label: "Apple" },
                      { value: "instagram", label: "Instagram" },
                    ]}
                  />
                  <FieldSelect
                    label="Status"
                    value={form.status}
                    onChange={(value) => setForm((current) => ({ ...current, status: value }))}
                    options={[
                      { value: "active", label: "Ativo" },
                      { value: "disabled", label: "Desabilitado" },
                    ]}
                  />
                  <TextInput
                    label={form.provider === "local" ? "Senha local" : "Senha (opcional)"}
                    type="password"
                    value={form.password}
                    onChange={(value) => setForm((current) => ({ ...current, password: value }))}
                    placeholder={editingUser ? "Preencha apenas para trocar" : "Obrigatória para usuário local"}
                  />
                </div>

                <div className="mt-6 space-y-5">
                  <h3 className="text-xl font-semibold text-slate-950">Overrides de permissão</h3>
                  {permissionGroups.map(([category, permissions]) => (
                    <section key={category} className="rounded-[1.4rem] border border-slate-900/10 bg-white/72 p-4">
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">{category}</p>
                      <div className="mt-4 grid gap-3">
                        {permissions.map((permission) => (
                          <div key={permission.key} className="grid gap-3 rounded-[1rem] border border-slate-900/10 bg-white p-4 md:grid-cols-[1fr_auto_auto] md:items-center">
                            <div>
                              <p className="font-semibold text-slate-950">{permission.label}</p>
                              <p className="mt-1 text-sm leading-6 text-slate-600">{permission.description}</p>
                              <p className="mt-1 font-mono text-xs text-slate-400">{permission.key}</p>
                            </div>
                            <ToggleChip
                              label="Conceder"
                              active={form.granted_permissions.includes(permission.key)}
                              tone="success"
                              onClick={() => togglePermission(permission.key, "granted_permissions")}
                            />
                            <ToggleChip
                              label="Revogar"
                              active={form.revoked_permissions.includes(permission.key)}
                              tone="danger"
                              onClick={() => togglePermission(permission.key, "revoked_permissions")}
                            />
                          </div>
                        ))}
                      </div>
                    </section>
                  ))}
                </div>

                <button type="submit" disabled={saving} className="mt-6 rounded-[1.2rem] bg-slate-950 px-6 py-4 text-base font-semibold text-white disabled:opacity-60">
                  {saving ? "Salvando..." : editingUser ? "Salvar alterações" : "Criar usuário"}
                </button>
              </form>
              ) : (
                <section className="portal-card rounded-[1.8rem] px-6 py-6">
                  <AccessDeniedPanel
                    title="Somente master altera permissões"
                    description="Seu perfil pode visualizar usuários, porém criar, editar ou excluir acessos é exclusivo do usuário master."
                  />
                </section>
              )}
            </PermissionGate>

            <section className="portal-card rounded-[1.8rem] px-6 py-6">
              <p className="section-kicker">Acessos atuais</p>
              <h2 className="mt-2 text-3xl font-semibold text-slate-950">Usuários cadastrados</h2>
              {loading ? (
                <p className="mt-5 text-base text-slate-600">Carregando usuários...</p>
              ) : (
                <div className="mt-6 space-y-4">
                  <UserRow
                    key={`master-${user?.username}`}
                    current
                    record={{
                      id: "master",
                      username: user?.username ?? "rodrigogrosa",
                      display_name: "Rodrigo Rosa",
                      role: "master",
                      role_label: "Master",
                      provider: "master",
                      status: "active",
                      permissions: accessModel?.roles.find((role) => role.key === "master")?.permissions ?? [],
                      granted_permissions: [],
                      revoked_permissions: [],
                    }}
                    onEdit={undefined}
                    onDelete={undefined}
                    canManage={false}
                  />
                  {users.map((record) => (
                    <UserRow
                      key={record.id}
                      record={record}
                      canManage={Boolean(can(PERMISSIONS.usersManage) && isMaster)}
                      onEdit={() => startEdit(record)}
                      onDelete={() => void handleDelete(record)}
                    />
                  ))}
                </div>
              )}
            </section>
          </div>
        </div>
      )}
    </AppShell>
  );
}

function UserRow({
  record,
  current = false,
  canManage,
  onEdit,
  onDelete,
}: {
  record: UserRecord;
  current?: boolean;
  canManage: boolean;
  onEdit?: () => void;
  onDelete?: () => void;
}) {
  return (
    <article className="rounded-[1.35rem] border border-slate-900/10 bg-white/78 p-5">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h3 className="text-xl font-semibold text-slate-950">{record.display_name}</h3>
            <span className="pill">{record.role_label}</span>
            {current ? <span className="pill">Sessão atual</span> : null}
          </div>
          <p className="mt-2 text-sm text-slate-500">
            {record.username} · {record.provider} · {record.status}
          </p>
          <p className="mt-3 text-sm leading-6 text-slate-600">{record.permissions.length} permissões efetivas.</p>
        </div>
        {canManage && !current ? (
          <div className="flex flex-wrap gap-3">
            <button type="button" onClick={onEdit} className="portal-action">
              Editar
            </button>
            <button type="button" onClick={onDelete} className="portal-action border-red-200 bg-red-50 text-red-700">
              Excluir
            </button>
          </div>
        ) : null}
      </div>
    </article>
  );
}

function TextInput({
  label,
  value,
  onChange,
  placeholder,
  disabled,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  type?: string;
}) {
  return (
    <label className="block">
      <span className="text-sm font-semibold text-slate-700">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        className="mt-2 w-full rounded-[1rem] border border-slate-900/10 bg-white px-4 py-3 text-base outline-none disabled:cursor-not-allowed disabled:bg-slate-100"
      />
    </label>
  );
}

function FieldSelect({
  label,
  value,
  onChange,
  options,
  disabled,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  disabled?: boolean;
}) {
  return (
    <label className="block">
      <span className="text-sm font-semibold text-slate-700">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
        className="mt-2 w-full rounded-[1rem] border border-slate-900/10 bg-white px-4 py-3 text-base outline-none disabled:cursor-not-allowed disabled:bg-slate-100"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function ToggleChip({
  label,
  active,
  tone,
  onClick,
}: {
  label: string;
  active: boolean;
  tone: "success" | "danger";
  onClick: () => void;
}) {
  const activeClass =
    tone === "success"
      ? "border-emerald-300 bg-emerald-50 text-emerald-700"
      : "border-red-300 bg-red-50 text-red-700";
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full border px-4 py-2 text-sm font-semibold ${active ? activeClass : "border-slate-200 bg-white text-slate-500"}`}
    >
      {label}
    </button>
  );
}
