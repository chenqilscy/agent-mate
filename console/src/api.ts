import type {
  Account, Activity, AuthResponse, CatalogData, CatalogItem, CommentRecord,
  KnowledgeBase, KnowledgeDocument, Member, Milestone, NotificationRecord,
  Organization, PlatformSettingsPayload, Project, ProjectCustomField, SkillData, SkillRelease, SkillTool, Sprint, TimelineEvent, ToolCatalogAudit, WorkItem, BurndownPoint,
} from "./types";

const TOKEN_KEY = "agentmate.console.token";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function setToken(token: string): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export async function apiRequest<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const token = getToken();
  const response = await fetch(`/api${path}`, {
    method,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  let data: unknown = null;
  try {
    data = await response.json();
  } catch {
    // Some successful endpoints intentionally have no useful body.
  }

  if (!response.ok) {
    const detail = data && typeof data === "object" && "detail" in data
      ? (data as { detail: unknown }).detail
      : null;
    const message = typeof detail === "string"
      ? detail
      : detail
        ? JSON.stringify(detail)
        : `HTTP ${response.status}`;
    throw new ApiError(message, response.status);
  }
  return data as T;
}

export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const token = getToken();
  const separator = path.includes("?") ? "&" : "?";
  const response = await fetch(`/api${path}${separator}filename=${encodeURIComponent(file.name)}`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: file,
  });
  let data: unknown = null;
  try { data = await response.json(); } catch { /* response detail is optional */ }
  if (!response.ok) {
    const detail = data && typeof data === "object" && "detail" in data ? (data as { detail: unknown }).detail : null;
    throw new ApiError(typeof detail === "string" ? detail : `HTTP ${response.status}`, response.status);
  }
  return data as T;
}

export async function apiDownload(path: string, filename: string): Promise<void> {
  const token = getToken();
  const response = await fetch(`/api${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!response.ok) throw new ApiError(`HTTP ${response.status}`, response.status);
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url; anchor.download = filename; anchor.click();
  URL.revokeObjectURL(url);
}

export const consoleApi = {
  me: () => apiRequest<{ account: Account }>("GET", "/me"),
  login: (name: string, password: string) =>
    apiRequest<AuthResponse>("POST", "/auth/login", { name, password }),
  register: (name: string, password: string) =>
    apiRequest<AuthResponse>("POST", "/auth/register", { name, password }),
  logout: () => apiRequest<{ ok: boolean }>("POST", "/auth/logout"),
  skills: () =>
    apiRequest<{ items: CatalogItem<SkillData>[] }>("GET", "/catalog/APP_SKILLS?all=true"),
  skillTools: () => apiRequest<{ tools: SkillTool[] }>("GET", "/catalog/skill-tools"),
  tools: (all = false) => apiRequest<{ tools: SkillTool[] }>("GET", `/catalog/tools${all ? "?all=true" : ""}`),
  updateTool: (name: string, patch: Partial<Pick<SkillTool, "label" | "description" | "category" | "risk_level" | "enabled" | "bindable" | "min_app_version" | "sort">>) =>
    apiRequest<{ tool: SkillTool }>("PATCH", `/catalog/tools/${encodeURIComponent(name)}`, patch),
  toolAudit: (name: string) =>
    apiRequest<{ audit: ToolCatalogAudit[] }>("GET", `/catalog/tools/${encodeURIComponent(name)}/audit`),
  updateSkill: (id: string, patch: { data?: SkillData; sort?: number; enabled?: boolean }) =>
    apiRequest<{ ok: boolean }>("PATCH", `/catalog/item/${encodeURIComponent(id)}`, patch),
  skillReleases: (catalogItemId = "") =>
    apiRequest<{ releases: SkillRelease[] }>("GET", `/catalog/skill-releases${catalogItemId ? `?catalog_item_id=${encodeURIComponent(catalogItemId)}` : ""}`),
  createSkillRelease: (data: SkillData, sort: number, catalogItemId = "", minAppVersion = "0.0.0") =>
    apiRequest<{ release: SkillRelease }>("POST", "/catalog/skill-releases", { data, sort, catalog_item_id: catalogItemId, min_app_version: minAppVersion }),
  submitSkillReleaseTest: (id: string, body: { passed: boolean; client_run_id: string; app_version: string; supported_tools: Record<string, string>; trace_id?: string; artifacts?: string[]; error?: string }) =>
    apiRequest<{ release: SkillRelease }>("POST", `/catalog/skill-releases/${encodeURIComponent(id)}/test-result`, body),
  approveSkillRelease: (id: string) =>
    apiRequest<{ release: SkillRelease }>("POST", `/catalog/skill-releases/${encodeURIComponent(id)}/approve`),
  publishSkillRelease: (id: string, body: { rollout_percent: number; rollout_channel: string; effective_at?: number }) =>
    apiRequest<{ release: SkillRelease }>("POST", `/catalog/skill-releases/${encodeURIComponent(id)}/publish`, body),
  pauseSkillRelease: (id: string) =>
    apiRequest<{ release: SkillRelease }>("POST", `/catalog/skill-releases/${encodeURIComponent(id)}/pause`),
  withdrawSkillRelease: (id: string) =>
    apiRequest<{ release: SkillRelease }>("POST", `/catalog/skill-releases/${encodeURIComponent(id)}/withdraw`),
  rollbackSkillRelease: (id: string) =>
    apiRequest<{ release: SkillRelease }>("POST", `/catalog/skill-releases/${encodeURIComponent(id)}/rollback`),
  projects: () => apiRequest<{ projects: Project[] }>("GET", "/projects"),
  project: (id: string) => apiRequest<Project>("GET", `/projects/${encodeURIComponent(id)}`),
  createProject: (body: Partial<Project> & { name: string }) => apiRequest<Project>("POST", "/projects", body),
  updateProject: (id: string, body: Partial<Project>) => apiRequest<Project>("PATCH", `/projects/${encodeURIComponent(id)}`, body),
  projectMembers: (id: string) => apiRequest<{ members: Member[] }>("GET", `/projects/${encodeURIComponent(id)}/members`),
  addProjectMember: (id: string, name: string, role: string) => apiRequest<{ ok: boolean }>("POST", `/projects/${encodeURIComponent(id)}/members`, { name, role }),
  updateProjectMember: (id: string, accountId: string, role: string) => apiRequest<{ ok: boolean }>("PATCH", `/projects/${encodeURIComponent(id)}/members/${encodeURIComponent(accountId)}`, { role }),
  removeProjectMember: (id: string, accountId: string) => apiRequest<{ ok: boolean }>("DELETE", `/projects/${encodeURIComponent(id)}/members/${encodeURIComponent(accountId)}`),
  inviteProjectMember: (id: string, role: string) => apiRequest<{ code: string }>("POST", `/projects/${encodeURIComponent(id)}/invites`, { role }),
  workItems: (id: string) => apiRequest<{ items: WorkItem[] }>("GET", `/projects/${encodeURIComponent(id)}/work-items`),
  createWorkItem: (id: string, body: Partial<WorkItem> & { title: string }) => apiRequest<WorkItem>("POST", `/projects/${encodeURIComponent(id)}/work-items`, body),
  updateWorkItem: (id: string, workId: string, body: Partial<WorkItem>) => apiRequest<WorkItem>("PATCH", `/projects/${encodeURIComponent(id)}/work-items/${encodeURIComponent(workId)}`, body),
  deleteWorkItem: (id: string, workId: string) => apiRequest<{ ok: boolean }>("DELETE", `/projects/${encodeURIComponent(id)}/work-items/${encodeURIComponent(workId)}`),
  milestones: (id: string) => apiRequest<{ milestones: Milestone[] }>("GET", `/projects/${encodeURIComponent(id)}/milestones`),
  createMilestone: (id: string, body: { name: string; due_date?: string }) => apiRequest<Milestone>("POST", `/projects/${encodeURIComponent(id)}/milestones`, body),
  activity: (id: string) => apiRequest<{ activity: Activity[] }>("GET", `/projects/${encodeURIComponent(id)}/activity`),
  customFields: (id: string) => apiRequest<{ fields: ProjectCustomField[] }>("GET", `/projects/${encodeURIComponent(id)}/custom-fields`),
  createCustomField: (id: string, body: Pick<ProjectCustomField, "name" | "field_type" | "options" | "required">) => apiRequest<ProjectCustomField>("POST", `/projects/${encodeURIComponent(id)}/custom-fields`, body),
  deleteCustomField: (id: string, fieldId: string) => apiRequest<{ ok: boolean }>("DELETE", `/projects/${encodeURIComponent(id)}/custom-fields/${encodeURIComponent(fieldId)}`),
  sprints: (id: string) => apiRequest<{ sprints: Sprint[] }>("GET", `/projects/${encodeURIComponent(id)}/sprints`),
  createSprint: (id: string, body: Pick<Sprint, "name" | "goal" | "start_date" | "end_date" | "status">) => apiRequest<Sprint>("POST", `/projects/${encodeURIComponent(id)}/sprints`, body),
  updateSprint: (id: string, sprintId: string, body: Partial<Sprint>) => apiRequest<Sprint>("PATCH", `/projects/${encodeURIComponent(id)}/sprints/${encodeURIComponent(sprintId)}`, body),
  deleteSprint: (id: string, sprintId: string) => apiRequest<{ ok: boolean }>("DELETE", `/projects/${encodeURIComponent(id)}/sprints/${encodeURIComponent(sprintId)}`),
  sprintBurndown: (id: string, sprintId: string) => apiRequest<{ total: number; points: BurndownPoint[] }>("GET", `/projects/${encodeURIComponent(id)}/sprints/${encodeURIComponent(sprintId)}/burndown`),
  exportPmCsv: (id: string) => apiDownload(`/projects/${encodeURIComponent(id)}/pm-export.csv`, `project-${id}-pm.csv`),
  comments: (id: string) => apiRequest<{ comments: CommentRecord[] }>("GET", `/projects/${encodeURIComponent(id)}/comments`),
  createComment: (id: string, body: string) => apiRequest<CommentRecord>("POST", `/projects/${encodeURIComponent(id)}/comments`, { body }),
  timeline: (id: string) => apiRequest<{ events: TimelineEvent[] }>("GET", `/projects/${encodeURIComponent(id)}/timeline`),
  presence: (id: string) => apiRequest<{ presence: Member[] }>("GET", `/projects/${encodeURIComponent(id)}/presence`),
  organizations: () => apiRequest<{ orgs: Organization[] }>("GET", "/orgs"),
  createOrganization: (name: string) => apiRequest<Organization>("POST", "/orgs", { name }),
  organizationMembers: (id: string) => apiRequest<{ members: Member[] }>("GET", `/orgs/${encodeURIComponent(id)}/members`),
  addOrganizationMember: (id: string, name: string, role: string) => apiRequest<{ ok: boolean }>("POST", `/orgs/${encodeURIComponent(id)}/members`, { name, role }),
  accounts: () => apiRequest<{ accounts: Account[] }>("GET", "/accounts"),
  createAccount: (body: { name: string; password: string; email?: string; plan?: string; is_platform_admin?: boolean }) => apiRequest<{ account: Account }>("POST", "/accounts", body),
  updateAccount: (id: string, body: Partial<Account>) => apiRequest<{ account: Account }>("PATCH", `/accounts/${encodeURIComponent(id)}`, body),
  resetPassword: (id: string, password: string) => apiRequest<{ ok: boolean }>("POST", `/accounts/${encodeURIComponent(id)}/password`, { password }),
  deleteAccount: (id: string) => apiRequest<{ ok: boolean }>("DELETE", `/accounts/${encodeURIComponent(id)}`),
  notifications: () => apiRequest<{ notifications: NotificationRecord[]; unread: number }>("GET", "/notifications"),
  markNotificationsRead: (ids?: string[]) => apiRequest<{ ok: boolean }>("POST", "/notifications/read", ids ? { ids } : {}),
  platformSettings: () => apiRequest<PlatformSettingsPayload>("GET", "/admin/settings"),
  savePlatformSettings: (values: Record<string, unknown>, clear: string[] = []) =>
    apiRequest<PlatformSettingsPayload>("PUT", "/admin/settings", { values, clear }),
  testPlatformSettings: (group: string) =>
    apiRequest<{ ok: boolean; version?: string; embedding_models?: number; error?: string }>("POST", "/admin/settings/test", { group }),
  catalog: <T extends CatalogData = CatalogData>(category?: string, all = false) => apiRequest<{ items: CatalogItem<T>[] }>("GET", `/catalog${category ? `/${encodeURIComponent(category)}` : ""}${all ? "?all=true" : ""}`),
  createCatalogItem: <T extends CatalogData>(category: string, data: T, sort = 0) => apiRequest<{ id: string }>("POST", "/catalog", { category, data, sort }),
  updateCatalogItem: <T extends CatalogData>(id: string, patch: { data?: T; sort?: number; enabled?: boolean }) => apiRequest<{ ok: boolean }>("PATCH", `/catalog/item/${encodeURIComponent(id)}`, patch),
  deleteCatalogItem: (id: string) => apiRequest<{ ok: boolean }>("DELETE", `/catalog/item/${encodeURIComponent(id)}`),
  knowledgeBases: (id: string) => apiRequest<{ items: KnowledgeBase[]; configured: boolean }>("GET", `/projects/${encodeURIComponent(id)}/knowledge-bases`),
  createKnowledgeBase: (id: string, body: Partial<KnowledgeBase> & { name: string }) => apiRequest<KnowledgeBase>("POST", `/projects/${encodeURIComponent(id)}/knowledge-bases`, body),
  updateKnowledgeBase: (id: string, kbId: string, body: Partial<KnowledgeBase>) => apiRequest<KnowledgeBase>("PATCH", `/projects/${encodeURIComponent(id)}/knowledge-bases/${encodeURIComponent(kbId)}`, body),
  deleteKnowledgeBase: (id: string, kbId: string) => apiRequest<{ ok: boolean }>("DELETE", `/projects/${encodeURIComponent(id)}/knowledge-bases/${encodeURIComponent(kbId)}`),
  migrateKnowledgeBase: (id: string, kbId: string) => apiRequest<KnowledgeBase>("POST", `/projects/${encodeURIComponent(id)}/knowledge-bases/${encodeURIComponent(kbId)}/migrate`, {}),
  knowledgeDocuments: (id: string, kbId: string) => apiRequest<{ items: KnowledgeDocument[] }>("GET", `/projects/${encodeURIComponent(id)}/knowledge-bases/${encodeURIComponent(kbId)}/documents`),
  uploadKnowledgeDocument: (id: string, kbId: string, file: File) => apiUpload<KnowledgeDocument>(`/projects/${encodeURIComponent(id)}/knowledge-bases/${encodeURIComponent(kbId)}/documents`, file),
  deleteKnowledgeDocument: (id: string, kbId: string, docId: string) => apiRequest<{ ok: boolean }>("DELETE", `/projects/${encodeURIComponent(id)}/knowledge-bases/${encodeURIComponent(kbId)}/documents/${encodeURIComponent(docId)}`),
};
