import { apiRequest, consoleApi } from "./api";
import type { LocalAgentDevice, Project } from "./types";

export interface WorkspaceActionItem {
  id: string;
  project_id: string;
  title: string;
  status: string;
  priority: string;
  due_date?: string | null;
  updated_at?: number;
  project: { id: string; name: string; role: string };
  action_signals: string[];
  action_reason: string;
}

export interface WorkspaceActionItemsResponse {
  as_of: string;
  computed_at: number;
  source: "server";
  items: WorkspaceActionItem[];
  unassigned: WorkspaceActionItem[];
  summary: Record<string, number> & {
    assigned: number;
    unassigned: number;
    backlog: number;
  };
}

export interface WorkspaceRun {
  id: string;
  session_id: string;
  project_id?: string | null;
  work_item_id?: string | null;
  status: string;
  created_at: number;
  updated_at: number;
  error_message?: string | null;
  queue_context?: { message?: string } | null;
  request_snapshot?: Record<string, unknown>;
}

export interface WorkspaceSession {
  id: string;
  title: string;
  project_id?: string | null;
  work_item_id?: string | null;
  updated_at: number;
}

export type WorkspaceTurnMode = "ask" | "plan" | "exec";

export interface WorkspaceTurnRequest {
  text: string;
  title: string;
  project_id: string | null;
  kind: "chat" | "projexec";
  mode: WorkspaceTurnMode;
  workspace: string;
  target_device_id: string;
  required_capabilities: string[];
  request_snapshot: Record<string, unknown>;
}

export interface WorkspaceTurnResponse {
  session: WorkspaceSession & { version: number };
  user_message: { id: string; session_id: string; role: "user"; content: string };
  run: WorkspaceRun & { version: number };
  duplicate: boolean;
}

async function createTurn(
  body: WorkspaceTurnRequest,
  idempotencyKey: string,
): Promise<WorkspaceTurnResponse> {
  const response = await fetch("/api/turns", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey,
      "X-AgentMate-Protocol-Version": "2",
      "X-AgentMate-Console-Session": "1",
    },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => null) as
    | WorkspaceTurnResponse
    | { detail?: unknown }
    | null;
  if (!response.ok) {
    const detail = data && "detail" in data ? data.detail : null;
    throw new Error(
      typeof detail === "string"
        ? detail
        : detail
          ? JSON.stringify(detail)
          : `HTTP ${response.status}`,
    );
  }
  return data as WorkspaceTurnResponse;
}

export const workspaceApi = {
  actionItems: (asOf: string) =>
    apiRequest<WorkspaceActionItemsResponse>(
      "GET",
      `/work-items/action-items?as_of=${encodeURIComponent(asOf)}`,
    ),
  runs: () =>
    apiRequest<{ runs: WorkspaceRun[] }>("GET", "/runs?limit=100"),
  sessions: () =>
    apiRequest<{ sessions: WorkspaceSession[] }>("GET", "/sessions?limit=100"),
  devices: (): Promise<{ devices: LocalAgentDevice[]; protocol_version: number }> =>
    consoleApi.devices(),
  projects: (): Promise<{ projects: Project[] }> => consoleApi.projects(),
  createTurn,
};
