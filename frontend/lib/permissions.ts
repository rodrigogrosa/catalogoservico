export const PERMISSIONS = {
  dashboardView: "dashboard.view",
  projectsView: "projects.view",
  projectsCreate: "projects.create",
  projectsProcess: "projects.process",
  projectsDelete: "projects.delete",
  projectsDownload: "projects.download",
  catalogView: "catalog.view",
  queueView: "queue.view",
  reportsView: "reports.view",
  knowledgeView: "knowledge.view",
  knowledgeManage: "knowledge.manage",
  storesView: "stores.view",
  storesManage: "stores.manage",
  storesPublish: "stores.publish",
  socialLoginView: "social_login.view",
  socialLoginManage: "social_login.manage",
  usersView: "users.view",
  usersManage: "users.manage",
} as const;

export type PermissionKey = (typeof PERMISSIONS)[keyof typeof PERMISSIONS];

export function hasPermission(permissions: string[] | undefined, permission?: string | null): boolean {
  if (!permission) return true;
  return Boolean(permissions?.includes(permission));
}

export function hasAnyPermission(permissions: string[] | undefined, required: string[]): boolean {
  return required.some((item) => hasPermission(permissions, item));
}
