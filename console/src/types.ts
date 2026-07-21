export type ThemeMode = "light" | "dark";

export interface Account {
  id: string;
  name: string;
  email: string;
  plan?: string;
  created_at?: number;
  is_platform_admin: boolean;
}

export interface AuthResponse {
  token: string;
  account: Account;
}

export interface SkillFile {
  path: string;
  content: string;
}

export interface SkillData {
  slug: string;
  name: string;
  icon: string;
  category_slug: string;
  category: string;
  description: string;
  instructions: string;
  tools: string[];
  permissions?: string[];
  files: SkillFile[];
  source: string;
  min_app_version?: string;
}

export interface SkillCategoryData {
  [key: string]: unknown;
  slug: string;
  name: string;
  icon: string;
  description: string;
}

export interface CatalogItem<T> {
  id: string;
  category: string;
  kind: string;
  data: T;
  sort: number;
  enabled: boolean;
  version: number;
  created_at?: number;
  updated_at?: number;
}

export interface SkillTool {
  name: string;
  label?: string;
  description?: string;
  permissions?: string[];
  min_app_version?: string;
  contract_version?: string;
  category?: string;
  risk_level?: "low" | "medium" | "high" | "critical";
  exposure?: "skill" | "contextual" | "automatic" | "internal";
  enabled?: boolean;
  bindable?: boolean;
  sort?: number;
  created_at?: number;
  updated_at?: number;
}

export interface ToolCatalogAudit {
  id: string;
  tool_name: string;
  actor_id: string;
  action: string;
  before_data: SkillTool;
  after_data: SkillTool;
  created_at: number;
}

export type SkillReleaseState = "draft" | "testing" | "approved" | "rolling_out" | "published" | "withdrawn" | "superseded";

export interface SkillRelease {
  id: string;
  catalog_item_id?: string;
  slug: string;
  version: number;
  state: SkillReleaseState;
  data: SkillData;
  sort: number;
  content_hash: string;
  base_release_id: string;
  min_app_version: string;
  rollout_channel: string;
  rollout_percent: number;
  effective_at: number;
  author_id: string;
  reviewer_id: string;
  test_status: "pending" | "passed" | "failed";
  test_report: Record<string, unknown>;
  diff: {
    changed_fields: string[];
    tools_added: string[];
    tools_removed: string[];
    permissions_before: string[];
    permissions_after: string[];
  };
  metrics: {
    installs: number;
    install_failures: number;
    runs: number;
    run_failures: number;
    rollbacks: number;
  };
  audit: Array<{ id: string; action: string; actor_id: string; details: Record<string, unknown>; created_at: number }>;
  created_at: number;
  published_at?: number;
}

export type Role = "Owner" | "Admin" | "Member" | "Viewer";

export interface Project {
  id: string;
  name: string;
  org_id?: string | null;
  owner_id: string;
  instruction: string;
  connectors: string[];
  experts: string[];
  skills: string[];
  role: Role;
  created_at: number;
  updated_at: number;
}

export interface Organization {
  id: string;
  name: string;
  owner_id: string;
  role: Role;
  created_at: number;
}

export interface Member {
  account_id: string;
  name: string;
  role: Role;
  email?: string;
}

export interface WorkItem {
  id: string;
  project_id: string;
  title: string;
  description: string;
  status: "todo" | "doing" | "paused" | "done";
  priority: "" | "low" | "medium" | "high" | "urgent";
  source: string;
  assignee: string;
  assignee_name?: string;
  due_date: string;
  start_date: string;
  labels: string[];
  parent_id: string;
  milestone_id: string;
  estimate_h: number;
  spent_h: number;
  sort?: number;
  created_at?: number;
  updated_at?: number;
}

export interface Milestone {
  id: string;
  project_id: string;
  name: string;
  status: string;
  due_date?: string;
  created_at?: number;
}

export interface Activity {
  id?: string;
  actor?: string;
  kind: string;
  detail?: string;
  created_at: number;
}

export interface CommentRecord {
  id: string;
  body: string;
  author_name?: string;
  account_name?: string;
  created_at: number;
}

export interface TimelineEvent {
  id: string;
  actor?: string;
  actor_name?: string;
  kind: string;
  title?: string;
  summary?: string;
  detail?: string;
  created_at: number;
}

export interface NotificationRecord {
  id: string;
  kind: string;
  title?: string;
  body?: string;
  message?: string;
  read: boolean;
  created_at: number;
}

export interface KnowledgeBase {
  id: string;
  name: string;
  description: string;
  icon: string;
  embedding_id: number;
  embedding_dim: number;
  knowledge_type: number;
  sentence_size: number;
  contextual: number;
  tags: string[];
  doc_count: number;
}

export interface KnowledgeDocument {
  id: string;
  filename: string;
  size: number;
  doc_type: string;
  vector_status: number;
  fail_msg?: string;
  created_at?: number;
}

export type CatalogData = Record<string, unknown> | string;
