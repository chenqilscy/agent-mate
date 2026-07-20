import type { Account, AuthResponse, CatalogItem, SkillData, SkillTool } from "./types";

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
  createSkill: (data: SkillData, sort: number) =>
    apiRequest<{ id: string }>("POST", "/catalog", { category: "APP_SKILLS", data, sort }),
  updateSkill: (id: string, patch: { data?: SkillData; sort?: number; enabled?: boolean }) =>
    apiRequest<{ ok: boolean }>("PATCH", `/catalog/item/${encodeURIComponent(id)}`, patch),
  archiveSkill: (id: string) =>
    apiRequest<{ ok: boolean; archived?: boolean }>("DELETE", `/catalog/item/${encodeURIComponent(id)}`),
};
