import { apiRequest, consoleApi } from "./api";
import type { LocalAgentDevice } from "./types";

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
};
