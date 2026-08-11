export type ThemeMode = "light" | "dark";

export interface Account {
  id: string;
  name: string;
  email: string;
  plan?: string;
  created_at?: number;
  is_platform_admin: boolean;
  password_login_enabled?: boolean;
  suspended_at?: number;
  active_sessions?: number;
  identities?: Array<{
    provider: string;
    email: string;
    display_name: string;
    created_at: number;
    last_login_at: number;
  }>;
}

export interface AuthResponse {
  token: string;
  account: Account;
}

export type AutomationTriggerKind = "interval" | "daily" | "health_daily" | "webhook";

export interface AutomationRecord {
  id: string;
  owner_id: string;
  project_id?: string | null;
  name: string;
  prompt: string;
  trigger_kind: AutomationTriggerKind;
  interval_min: number;
  at_time: string;
  timezone: string;
  model_ref?: string | null;
  enabled: boolean;
  timeout_sec: number;
  max_attempts: number;
  retry_backoff_sec: number;
  max_total_tokens: number;
  notify_policy: string;
  concurrency_policy: "skip";
  preauthorized_permissions: string[];
  next_run_at?: number | null;
  last_run_at?: number | null;
  last_session_id?: string | null;
  last_status?: string | null;
  version: number;
  created_at: number;
  updated_at: number;
}

export interface AutomationFireRecord {
  id: string;
  automation_id: string;
  owner_id: string;
  fire_key: string;
  trigger_kind: string;
  planned_at: number;
  status: "queued" | "running" | "retry_wait" | "succeeded" | "dead_letter" | "ignored";
  attempt: number;
  max_attempts: number;
  session_id?: string | null;
  run_id?: string | null;
  error_code?: string;
  error_message?: string;
  next_attempt_at?: number | null;
  created_at: number;
  updated_at: number;
  finished_at?: number;
}

export interface AutomationWebhookDeliveryRecord {
  id: string;
  idempotency_key: string;
  status: string;
  fire_id?: string | null;
  error_code?: string;
  fire_status?: string | null;
  received_at: number;
}

export interface AutomationWebhookRecord {
  configured: boolean;
  automation_id: string;
  webhook_id?: string | null;
  endpoint?: string | null;
  secret?: string;
  created_at?: number | null;
  rotated_at?: number | null;
  deliveries: AutomationWebhookDeliveryRecord[];
}

export interface PlatformSettingItem {
  key: string;
  group: "knowledge" | "collaboration" | string;
  label: string;
  description: string;
  value_type: "string" | "integer" | "secret";
  env_name: string;
  secret: boolean;
  minimum?: number | null;
  maximum?: number | null;
  placeholder?: string;
  source: "database" | "environment" | "default";
  configured: boolean;
  value: string | number | null;
  hot_reload: boolean;
}

export interface PlatformSettingAudit {
  id: string;
  setting_key: string;
  actor_id: string;
  action: string;
  before_value: string;
  after_value: string;
  created_at: number;
}

export interface PlatformSettingsPayload {
  items: PlatformSettingItem[];
  deployment_only: string[];
  audit: PlatformSettingAudit[];
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
  skill_markdown?: string;
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

export interface SkillHubBlockData {
  [key: string]: unknown;
  slug: string;
  reason: string;
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
  implementation_type?: "native" | "shell";
  parameters?: Record<string, unknown>;
  scripts?: Partial<Record<"windows" | "linux" | "macos", string>>;
  timeout_seconds?: number;
  output_limit?: number;
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

export type SkillReleaseState =
  | "draft"
  | "testing"
  | "approved"
  | "rolling_out"
  | "published"
  | "withdrawn"
  | "superseded";

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
  audit: Array<{
    id: string;
    action: string;
    actor_id: string;
    details: Record<string, unknown>;
    created_at: number;
  }>;
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
  knowledge_ids: string[];
  role: Role;
  created_at: number;
  updated_at: number;
  archived_at: number;
}

export interface AssetRecord {
  id: string;
  owner_id: string;
  project_id?: string | null;
  session_id?: string | null;
  run_id?: string | null;
  kind: string;
  name: string;
  mime_type: string;
  size: number;
  sha256: string;
  storage_state: "pending" | "uploading" | "committed" | string;
  object_ref: string;
  validation_status: string;
  acceptance_status: string;
  version: number;
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
  status: "todo" | "doing" | "paused" | "review" | "done";
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
  custom_fields: Record<string, string | number | boolean>;
  dependency_ids: string[];
  sprint_id: string;
  critical_path?: boolean;
  sort?: number;
  created_at?: number;
  updated_at?: number;
}

export type WorkItemRunStatus =
  | "queued"
  | "leased"
  | "planning"
  | "running"
  | "waiting_user"
  | "paused"
  | "recoverable"
  | "completed"
  | "succeeded"
  | "failed"
  | "cancelled";

export interface WorkItemRunPlanItem {
  id: string;
  title: string;
  status: "pending" | "in_progress" | "completed" | "blocked" | string;
  order: number;
  depends_on: string[];
  work_item_id?: string;
}

export interface WorkItemRunQueueContext {
  reason: string;
  message: string;
  blocking_run?: {
    id: string;
    session_id: string;
    project_id?: string;
    status: WorkItemRunStatus;
  };
}

export interface WorkItemRunEvent {
  event_id: string;
  sequence: number;
  type: string;
  occurred_at: number;
  device_id: string;
  lease_epoch: number;
  payload: Record<string, unknown>;
}

export interface WorkItemRunArtifact extends AssetRecord {
  path: string;
  preview_path?: string | null;
  is_primary: boolean;
  display_order: number;
  verification: { exists: boolean; hash_matches: boolean };
}

export interface WorkItemRun {
  id: string;
  session_id: string;
  owner_id: string;
  project_id?: string | null;
  work_item_id?: string | null;
  mode: "ask" | "plan" | "exec";
  status: WorkItemRunStatus;
  retry_of?: string | null;
  model_ref?: string | null;
  model_id?: string | null;
  estimated_cost?: number | null;
  cost_currency?: string | null;
  plan: WorkItemRunPlanItem[];
  plan_version: number;
  error_code?: string | null;
  error_message?: string | null;
  prompt_tokens: number;
  cached_prompt_tokens: number;
  completion_tokens: number;
  tool_calls: number;
  target_device_id: string;
  required_capabilities: string[];
  lease_epoch: number;
  recovery_count: number;
  started_at?: number | null;
  ended_at?: number | null;
  created_at: number;
  updated_at: number;
  queue_context?: WorkItemRunQueueContext | null;
  device?: { id: string; name: string } | null;
  artifacts: WorkItemRunArtifact[];
  events: WorkItemRunEvent[];
}

export interface WorkItemLaunch {
  id: string;
  work_item_id: string;
  owner_id: string;
  idempotency_key: string;
  session_id: string | null;
  run_id: string | null;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  error_code: string | null;
  error_message: string | null;
  created_at: number;
  updated_at: number;
  finished_at: number | null;
}

export interface WorkItemDelivery {
  work_item: WorkItem;
  can_write: boolean;
  launches: WorkItemLaunch[];
  runs: WorkItemRun[];
  acceptance: {
    run_id: string;
    artifact_count: number;
    accepted_by: string;
    accepted_at: number;
  } | null;
  next_cursor: string;
}

export interface ProjectCustomField {
  id: string;
  project_id: string;
  name: string;
  field_type: "text" | "number" | "date" | "select" | "boolean";
  options: string[];
  required: boolean;
  sort: number;
}

export interface Sprint {
  id: string;
  project_id: string;
  milestone_id: string;
  name: string;
  goal: string;
  start_date: string;
  end_date: string;
  status: "planned" | "active" | "closed";
  sort: number;
}

export interface BurndownPoint {
  date: string;
  ideal_remaining: number;
  actual_remaining: number;
}

export interface Milestone {
  id: string;
  project_id: string;
  name: string;
  status: string;
  description: string;
  due_date?: string;
  created_at?: number;
}

export type GovernanceRecordType = "risk" | "decision";
export type RiskSeverity = "low" | "medium" | "high" | "critical";

export interface ProjectGovernanceRecord {
  id: string;
  project_id: string;
  record_type: GovernanceRecordType;
  title: string;
  description: string;
  status: "open" | "mitigating" | "closed" | "proposed" | "accepted" | "superseded";
  severity: RiskSeverity | "";
  owner_id: string;
  owner_name?: string;
  response: string;
  rationale: string;
  work_item_id: string;
  work_item_title?: string;
  milestone_id: string;
  milestone_name?: string;
  run_id: string;
  artifact_id: string;
  evidence_label: string;
  created_by: string;
  created_at: number;
  updated_at: number;
  resolved_at: number;
}

export type ProjectHealthStatus = "healthy" | "attention" | "critical";
export interface ProjectHealth {
  status: ProjectHealthStatus;
  source: "server";
  stale: boolean;
  computed_at: number;
  as_of: string;
  summary: {
    total_tasks: number;
    completed_tasks: number;
    completion_percent: number;
    overdue_tasks: number;
    blocked_tasks: number;
    open_milestones: number;
    overdue_milestones: number;
    open_risks: number;
    high_risks: number;
    critical_risks: number;
    pending_decisions: number;
  };
  reasons: Array<{ code: string; count: number; label: string }>;
  milestones: Array<{
    id: string;
    name: string;
    status: string;
    health: ProjectHealthStatus;
    reasons: string[];
    due_date: string;
    overdue: boolean;
    total_tasks: number;
    completed_tasks: number;
    completion_percent: number;
    blocked_tasks: number;
    high_risks: number;
    critical_risks: number;
    pending_decisions: number;
  }>;
}

export interface ProjectHealthTransition {
  id: string;
  project_id: string;
  from_status: ProjectHealthStatus;
  to_status: ProjectHealthStatus;
  direction: "worsened" | "recovered";
  rank_delta: number;
  source: "server";
  snapshot: ProjectHealth;
  created_at: number;
}

export interface ProjectHealthPortfolioItem {
  project: Pick<Project, "id" | "name" | "role" | "updated_at"> & { origin: "server" };
  health: ProjectHealth;
  last_transition: ProjectHealthTransition | null;
}
export interface ProjectHealthPortfolio {
  items: ProjectHealthPortfolioItem[];
  summary: {
    total_projects: number;
    critical_projects: number;
    attention_projects: number;
    healthy_projects: number;
    stale_projects: number;
    overdue_tasks: number;
    blocked_tasks: number;
    critical_risks: number;
    pending_decisions: number;
  };
  source: "server";
  stale: boolean;
  computed_at: number;
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
  tags: string[];
  provider: "weknora" | "legacy";
  provider_status: "ready" | "legacy_pending" | "migrating" | "unavailable";
  provider_error?: string;
  doc_count: number;
}

export interface KnowledgeDocument {
  id: string;
  filename: string;
  size: number;
  doc_type: string;
  vector_status: number;
  parse_status: string;
  fail_msg?: string;
  created_at?: number;
}

export interface TaskTemplate {
  id: string;
  name: string;
  values: Partial<WorkItem>;
}
export interface SavedPlanView {
  id: string;
  name: string;
  filters: Record<string, string>;
}
export interface PmPreferences {
  templates: TaskTemplate[];
  wip: Partial<Record<WorkItem["status"], number>>;
  views: SavedPlanView[];
  shared_updated_at: number;
  views_updated_at: number;
}

export interface KnowledgeSearchHit {
  text: string;
  score?: number | null;
  metadata?: {
    doc_name?: string;
    doc_id?: string;
  };
}

export type CatalogData = Record<string, unknown> | string;
