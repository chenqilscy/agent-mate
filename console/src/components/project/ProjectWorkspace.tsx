import {
  Alert,
  App,
  Avatar,
  Badge,
  Button,
  Card,
  Checkbox,
  Col,
  Drawer,
  Dropdown,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Progress,
  Row,
  Segmented,
  Select,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Timeline,
  Typography,
} from "antd";
import {
  CalendarOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  EditOutlined,
  DeleteOutlined,
  DownloadOutlined,
  FlagOutlined,
  MoreOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  SaveOutlined,
  StopOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import { ProTable } from "@ant-design/pro-components";
import type { ProColumns } from "@ant-design/pro-components";
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { consoleApi } from "../../api";
import type {
  Activity,
  BurndownPoint,
  CommentRecord,
  Member,
  Milestone,
  Project,
  ProjectCustomField,
  ProjectHealth,
  Sprint,
  WorkItem,
} from "../../types";
import { CompatList as List } from "../CompatList";
import { MarkdownEditor } from "../MarkdownEditor";
import { WorkItemExecution } from "./WorkItemExecution";
import { ProjectExecutionAnalyticsPanel } from "./ProjectExecutionAnalytics";

const STATUS_OPTIONS = [
  { value: "todo", label: "待办" },
  { value: "doing", label: "进行中" },
  { value: "paused", label: "暂停" },
  { value: "review", label: "待验收" },
  { value: "done", label: "完成" },
] as const;
const PRIORITY_OPTIONS = [
  { value: "", label: "无" },
  { value: "low", label: "低" },
  { value: "medium", label: "中" },
  { value: "high", label: "高" },
  { value: "urgent", label: "紧急" },
] as const;
const PRIORITY_COLORS: Record<string, string> = {
  low: "default",
  medium: "blue",
  high: "orange",
  urgent: "red",
};
const STATUS_META: Record<
  WorkItem["status"],
  { label: string; color: string }
> = {
  todo: { label: "待办", color: "default" },
  doing: { label: "进行中", color: "processing" },
  paused: { label: "暂停", color: "warning" },
  review: { label: "待验收", color: "purple" },
  done: { label: "完成", color: "success" },
};
const SPRINT_STATUS_META: Record<
  Sprint["status"],
  { label: string; color: string; order: number }
> = {
  active: { label: "当前", color: "processing", order: 0 },
  planned: { label: "计划中", color: "blue", order: 1 },
  closed: { label: "已结束", color: "default", order: 2 },
};

function orderSprints(sprints: Sprint[]) {
  return [...sprints].sort((left, right) => {
    const statusOrder =
      SPRINT_STATUS_META[left.status].order -
      SPRINT_STATUS_META[right.status].order;
    if (statusOrder) return statusOrder;
    if (left.status === "closed")
      return right.end_date.localeCompare(left.end_date);
    return left.start_date.localeCompare(right.start_date);
  });
}

type TaskDraft = Partial<WorkItem> & { title: string };
type TaskCreateDefaults = Partial<
  Pick<WorkItem, "milestone_id" | "sprint_id" | "start_date" | "due_date">
>;
type QuickPlanKind = "milestone" | "sprint";
type TaskEditorStep = "content" | "plan" | "advanced";
type PlanningSettingsSection = "milestones" | "sprints" | "fields";
type ProjectTaskListScope = "backlog" | "all";
type CustomFieldOptionEditorProps = {
  value?: string[];
  onChange?: (value: string[]) => void;
};
export type ProjectWorkspaceTab =
  | "overview"
  | "plan"
  | "backlog"
  | "tasks"
  | "workload"
  | "milestones"
  | "sprints"
  | "gantt"
  | "iterations"
  | "governance"
  | "knowledge"
  | "assets"
  | "collab"
  | "config";
interface QuickPlanDraft {
  name: string;
  description?: string;
  due_date?: string;
  goal?: string;
  milestone_id?: string;
  start_date?: string;
  end_date?: string;
  status?: string;
}

function CustomFieldOptionEditor({
  value = [],
  onChange,
}: CustomFieldOptionEditorProps) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const options = Array.isArray(value) ? value : [];

  function addOptions() {
    const candidates = draft
      .split(/[,，\n]/)
      .map((item) => item.trim())
      .filter(Boolean);
    if (!candidates.length) return;
    const next = [...options];
    for (const candidate of candidates) {
      if (candidate.length > 80) {
        setError(`选项“${candidate.slice(0, 20)}…”超过 80 个字符`);
        return;
      }
      if (next.includes(candidate)) {
        setError(`选项“${candidate}”已存在`);
        return;
      }
      if (next.length >= 50) {
        setError("最多添加 50 个选项");
        return;
      }
      next.push(candidate);
    }
    onChange?.(next);
    setDraft("");
    setError("");
  }

  return (
    <div className="project-field-option-editor">
      <Space.Compact block>
        <Input
          aria-label="选项名称"
          value={draft}
          maxLength={4000}
          placeholder="输入选项，按 Enter 或点击添加"
          onChange={(event) => {
            setDraft(event.target.value);
            if (error) setError("");
          }}
          onPressEnter={(event) => {
            event.preventDefault();
            addOptions();
          }}
        />
        <Button
          icon={<PlusOutlined />}
          disabled={!draft.trim() || options.length >= 50}
          onClick={addOptions}
        >
          添加
        </Button>
      </Space.Compact>
      <Typography.Text type={error ? "danger" : "secondary"}>
        {error || `已添加 ${options.length}/50；可用逗号批量添加`}
      </Typography.Text>
      <Space size={[6, 8]} wrap aria-label="已添加选项">
        {options.length ? (
          options.map((option, index) => (
            <Tag
              key={`${option}-${index}`}
              closable
              onClose={(event) => {
                event.preventDefault();
                onChange?.(options.filter((_item, itemIndex) => itemIndex !== index));
                setError("");
              }}
            >
              {option}
            </Tag>
          ))
        ) : (
          <Typography.Text type="secondary">尚未添加选项</Typography.Text>
        )}
      </Space>
    </div>
  );
}
type SprintFormDraft = Pick<
  Sprint,
  "name" | "goal" | "milestone_id" | "start_date" | "end_date" | "status"
> & {
  sync_task_milestone?: boolean;
};
interface TaskTemplate {
  id: string;
  name: string;
  values: Partial<WorkItem>;
}
type GroupMode = "none" | "assignee" | "milestone";
interface SavedPlanView {
  id: string;
  name: string;
  filters: {
    group?: string;
    assignee?: string;
    source?: string;
    search?: string;
  };
}

interface ProjectWorkContextValue {
  project: Project;
  items: WorkItem[];
  roots: WorkItem[];
  members: Member[];
  milestones: Milestone[];
  health: ProjectHealth | null;
  customFields: ProjectCustomField[];
  sprints: Sprint[];
  selectedSprintId: string;
  setSelectedSprintId: (sprintId: string) => void;
  activity: Activity[];
  loading: boolean;
  savingTaskIds: ReadonlySet<string>;
  selected: string[];
  setSelected: (ids: string[]) => void;
  reload: () => Promise<void>;
  navigateToTab: (tab: ProjectWorkspaceTab) => void;
  openTask: (
    task: WorkItem | null,
    defaults?: TaskCreateDefaults,
    readOnly?: boolean,
  ) => void;
  patchTask: (task: WorkItem, patch: Partial<WorkItem>) => Promise<void>;
  deleteTask: (task: WorkItem) => Promise<void>;
  batchPatch: (patch: Partial<WorkItem>) => Promise<void>;
  templates: TaskTemplate[];
  wip: Partial<Record<WorkItem["status"], number>>;
  savedViews: SavedPlanView[];
  savePreferences: (patch: {
    templates?: TaskTemplate[];
    wip?: Partial<Record<WorkItem["status"], number>>;
    views?: SavedPlanView[];
  }) => Promise<void>;
  openTemplate: (templateId: string, defaults?: TaskCreateDefaults) => void;
  deleteTemplate: (templateId: string) => Promise<void>;
}

const ProjectWorkContext = createContext<ProjectWorkContextValue | null>(null);

function errorText(reason: unknown, fallback: string): string {
  return reason instanceof Error ? reason.message : fallback;
}

function canWrite(project: Project): boolean {
  return project.role !== "Viewer" && !project.archived_at;
}

function taskDescriptionSummary(value: string): string {
  return value
    .replace(/```[\s\S]*?```/g, " 代码 ")
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/^\s*[-*+]\s+(?:\[[ xX]\]\s*)?/gm, "")
    .replace(/^\s*>\s?/gm, "")
    .replace(/[*_~`]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function isDescendant(items: WorkItem[], parentId: string, candidateId: string): boolean {
  const parents = new Map(items.map((item) => [item.id, item.parent_id]));
  let cursor = candidateId;
  const seen = new Set<string>();
  while (cursor && !seen.has(cursor)) {
    if (cursor === parentId) return true;
    seen.add(cursor);
    cursor = parents.get(cursor) || "";
  }
  return false;
}

function useProjectWork(): ProjectWorkContextValue {
  const value = useContext(ProjectWorkContext);
  if (!value)
    throw new Error(
      "Project workspace must be used inside ProjectWorkProvider",
    );
  return value;
}

export function ProjectWorkProvider({
  project,
  onNavigateTab,
  children,
}: {
  project: Project;
  onNavigateTab: (tab: ProjectWorkspaceTab) => void;
  children: ReactNode;
}) {
  const { message } = App.useApp();
  const [items, setItems] = useState<WorkItem[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const [health, setHealth] = useState<ProjectHealth | null>(null);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [customFields, setCustomFields] = useState<ProjectCustomField[]>([]);
  const [sprints, setSprints] = useState<Sprint[]>([]);
  const [selectedSprintId, setSelectedSprintId] = useState("");
  const [loading, setLoading] = useState(true);
  const [savingTaskIds, setSavingTaskIds] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<string[]>([]);
  const [editing, setEditing] = useState<WorkItem | null | undefined>(
    undefined,
  );
  const [templateOpen, setTemplateOpen] = useState(false);
  const [quickPlanKind, setQuickPlanKind] = useState<QuickPlanKind | null>(null);
  const [taskComments, setTaskComments] = useState<CommentRecord[]>([]);
  const [taskActivity, setTaskActivity] = useState<Activity[]>([]);
  const [templates, setTemplates] = useState<TaskTemplate[]>([]);
  const [wip, setWip] = useState<Partial<Record<WorkItem["status"], number>>>(
    {},
  );
  const [savedViews, setSavedViews] = useState<SavedPlanView[]>([]);
  const preferenceRevisions = useRef({ shared: 0, views: 0 });
  const [taskDirty, setTaskDirty] = useState(false);
  const [taskSaving, setTaskSaving] = useState(false);
  const [taskEditorReadOnly, setTaskEditorReadOnly] = useState(false);
  const [taskEditorStep, setTaskEditorStep] =
    useState<TaskEditorStep>("content");
  const [quickPlanSaving, setQuickPlanSaving] = useState(false);
  const [form] = Form.useForm<TaskDraft>();
  const [templateForm] = Form.useForm<{ name: string }>();
  const [commentForm] = Form.useForm<{ body: string }>();
  const [quickPlanForm] = Form.useForm<QuickPlanDraft>();
  const watchedTaskTitle = Form.useWatch("title", form);
  const watchedMilestoneId = Form.useWatch("milestone_id", form);
  const watchedSprintId = Form.useWatch("sprint_id", form);
  const watchedStartDate = Form.useWatch("start_date", form);
  const watchedDueDate = Form.useWatch("due_date", form);
  const watchedParentId = Form.useWatch("parent_id", form);
  const watchedDependencyIds =
    Form.useWatch("dependency_ids", form) || [];
  const watchedSprint = sprints.find(
    (sprint) => sprint.id === watchedSprintId,
  );
  const watchedMilestone = milestones.find(
    (milestone) => milestone.id === watchedMilestoneId,
  );
  const taskPlanWarnings = [
    watchedSprint?.milestone_id &&
    watchedSprint.milestone_id !== (watchedMilestoneId || "")
      ? "当前任务的里程碑与 Sprint 所属里程碑不同；允许保留，但请确认这是有意安排。"
      : "",
    watchedSprint &&
    watchedStartDate &&
    watchedStartDate < watchedSprint.start_date
      ? `任务开始日期早于 ${watchedSprint.name} 的开始日期。`
      : "",
    watchedSprint && watchedDueDate && watchedDueDate > watchedSprint.end_date
      ? `任务截止日期晚于 ${watchedSprint.name} 的结束日期。`
      : "",
    watchedMilestone?.due_date &&
    watchedDueDate &&
    watchedDueDate > watchedMilestone.due_date
      ? `任务截止日期晚于里程碑 ${watchedMilestone.name} 的截止日期。`
      : "",
  ].filter(Boolean);

  async function reload() {
    setLoading(true);
    const results = await Promise.allSettled([
      consoleApi.workItems(project.id),
      consoleApi.projectMembers(project.id),
      consoleApi.milestones(project.id),
      consoleApi.projectHealth(project.id),
      consoleApi.activity(project.id),
      consoleApi.customFields(project.id),
      consoleApi.sprints(project.id),
      consoleApi.pmPreferences(project.id),
    ]);
    const [
      work,
      memberResult,
      milestoneResult,
      healthResult,
      activityResult,
      fieldResult,
      sprintResult,
      preferenceResult,
    ] = results;
    if (work.status === "fulfilled") {
      setItems(work.value.items || []);
      setSelected((current) =>
        current.filter((id) => work.value.items.some((item) => item.id === id)),
      );
    }
    if (memberResult.status === "fulfilled")
      setMembers(memberResult.value.members || []);
    if (milestoneResult.status === "fulfilled")
      setMilestones(milestoneResult.value.milestones || []);
    if (healthResult.status === "fulfilled") setHealth(healthResult.value);
    if (activityResult.status === "fulfilled")
      setActivity(activityResult.value.activity || []);
    if (fieldResult.status === "fulfilled")
      setCustomFields(fieldResult.value.fields || []);
    if (sprintResult.status === "fulfilled") {
      const nextSprints = sprintResult.value.sprints || [];
      setSprints(nextSprints);
      setSelectedSprintId((current) => {
        if (current && nextSprints.some((sprint) => sprint.id === current))
          return current;
        return nextSprints.find((sprint) => sprint.status === "active")?.id || "";
      });
    }
    if (preferenceResult.status === "fulfilled") {
      setTemplates(preferenceResult.value.templates || []);
      setWip(preferenceResult.value.wip || {});
      setSavedViews(preferenceResult.value.views || []);
      preferenceRevisions.current = {
        shared: preferenceResult.value.shared_updated_at,
        views: preferenceResult.value.views_updated_at,
      };
    }
    const failed = results.filter(
      (result) => result.status === "rejected",
    ).length;
    if (failed)
      message.warning(
        `有 ${failed} 项项目数据暂时加载失败，已保留其他可用区域`,
      );
    setLoading(false);
  }

  async function refreshActivitySilently() {
    try {
      const result = await consoleApi.activity(project.id);
      setActivity(result.activity || []);
    } catch {
      // 行内保存已经成功时，活动流刷新失败不应反向覆盖任务状态。
    }
  }

  const syncWorkItemProjection = useCallback(
    (updated: WorkItem) => {
      setItems((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
      setEditing((current) =>
        current?.id === updated.id ? updated : current,
      );
      if (editing?.id === updated.id)
        form.setFieldValue("status", updated.status);
    },
    [editing?.id, form],
  );

  useEffect(() => {
    void reload();
  }, [project.id]);

  function loadTaskEditor(
    task: WorkItem | null,
    defaults: TaskCreateDefaults = {},
    readOnly = false,
  ) {
    setTaskDirty(false);
    setTaskEditorReadOnly(readOnly);
    setTaskEditorStep("content");
    setEditing(task);
    form.resetFields();
    form.setFieldsValue(
      task || {
        title: "",
        description: "",
        status: "todo",
        priority: "",
        source: "console",
        assignee: "",
        milestone_id: "",
        start_date: "",
        due_date: "",
        estimate_h: 0,
        spent_h: 0,
        labels: [],
        parent_id: "",
        custom_fields: {},
        dependency_ids: [],
        sprint_id: "",
        ...defaults,
      },
    );
    setTaskComments([]);
    setTaskActivity([]);
    commentForm.resetFields();
    if (task)
      void Promise.allSettled([
        consoleApi.workItemComments(project.id, task.id),
        consoleApi.workItemActivity(project.id, task.id),
      ]).then(([comments, taskEvents]) => {
        if (comments.status === "fulfilled")
          setTaskComments(comments.value.comments || []);
        if (taskEvents.status === "fulfilled")
          setTaskActivity(taskEvents.value.activity || []);
      });
  }

  function confirmDiscard(action: () => void, title: string) {
    if (!taskDirty || !canWrite(project)) {
      action();
      return;
    }
    Modal.confirm({
      title,
      content: "当前修改尚未保存，放弃后无法恢复。",
      okText: "放弃修改",
      cancelText: "继续编辑",
      okButtonProps: { danger: true },
      onOk: action,
    });
  }

  function openTask(
    task: WorkItem | null,
    defaults: TaskCreateDefaults = {},
    readOnly = false,
  ) {
    confirmDiscard(
      () => loadTaskEditor(task, defaults, readOnly),
      "切换任务并放弃修改？",
    );
  }

  function openChild(parent: WorkItem) {
    confirmDiscard(() => {
      loadTaskEditor(null);
      form.setFieldValue("parent_id", parent.id);
    }, "新建子任务并放弃修改？");
  }

  function closeTaskEditor() {
    if (taskSaving) return;
    confirmDiscard(() => {
      setTaskDirty(false);
      setTaskEditorReadOnly(false);
      setEditing(undefined);
    }, "关闭并放弃修改？");
  }

  function openQuickPlan(kind: QuickPlanKind) {
    quickPlanForm.resetFields();
    quickPlanForm.setFieldsValue({
      status: kind === "milestone" ? "open" : "planned",
      milestone_id: kind === "sprint" ? watchedMilestoneId || "" : undefined,
    });
    setQuickPlanKind(kind);
  }

  async function saveQuickPlan(values: QuickPlanDraft) {
    setQuickPlanSaving(true);
    try {
      if (quickPlanKind === "milestone") {
        const created = await consoleApi.createMilestone(project.id, {
          name: values.name,
          description: values.description || "",
          due_date: values.due_date || "",
          status: values.status || "open",
        });
        setMilestones((current) => [...current, created]);
        form.setFieldValue("milestone_id", created.id);
        setTaskDirty(true);
        message.success("里程碑已创建并选中");
      } else if (quickPlanKind === "sprint") {
        const created = await consoleApi.createSprint(project.id, {
          name: values.name,
          goal: values.goal || "",
          milestone_id: values.milestone_id || "",
          start_date: values.start_date || "",
          end_date: values.end_date || "",
          status: (values.status as Sprint["status"]) || "planned",
        });
        setSprints((current) => [...current, created]);
        form.setFieldValue("sprint_id", created.id);
        if (created.milestone_id)
          form.setFieldValue("milestone_id", created.milestone_id);
        setTaskDirty(true);
        message.success("Sprint 已创建并选中");
      }
      setQuickPlanKind(null);
    } catch (reason) {
      message.error(errorText(reason, "计划对象创建失败"));
    } finally {
      setQuickPlanSaving(false);
    }
  }

  function openTemplate(
    templateId: string,
    defaults: TaskCreateDefaults = {},
  ) {
    const template = templates.find((item) => item.id === templateId);
    if (!template) return;
    const values = { ...template.values };
    if (
      values.assignee &&
      !members.some((member) => member.account_id === values.assignee)
    )
      values.assignee = "";
    if (
      values.milestone_id &&
      !milestones.some((item) => item.id === values.milestone_id)
    )
      values.milestone_id = "";
    if (
      values.sprint_id &&
      !sprints.some((item) => item.id === values.sprint_id)
    )
      values.sprint_id = "";
    values.dependency_ids = (values.dependency_ids || []).filter((id) =>
      items.some((item) => item.id === id),
    );
    values.custom_fields = Object.fromEntries(
      Object.entries(values.custom_fields || {}).filter(([id]) =>
        customFields.some((field) => field.id === id),
      ),
    );
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      title: "",
      description: "",
      status: "todo",
      priority: "",
      source: "console",
      assignee: "",
      milestone_id: "",
      start_date: "",
      due_date: "",
      estimate_h: 0,
      spent_h: 0,
      labels: [],
      parent_id: "",
      custom_fields: {},
      dependency_ids: [],
      sprint_id: "",
      ...values,
      ...defaults,
    });
    setTaskDirty(true);
  }

  async function saveTemplate({ name }: { name: string }) {
    const fields: Partial<WorkItem> & { title?: string } = {
      ...form.getFieldsValue(),
    };
    delete fields.title;
    const template: TaskTemplate = {
      id: globalThis.crypto?.randomUUID?.() || `template-${Date.now()}`,
      name: name.trim().slice(0, 40),
      values: fields,
    };
    await savePreferences({ templates: [...templates, template] });
    setTemplateOpen(false);
    templateForm.resetFields();
    message.success("任务模板已保存到项目");
  }

  async function deleteTemplate(templateId: string) {
    await savePreferences({
      templates: templates.filter((item) => item.id !== templateId),
    });
    message.success("任务模板已删除");
  }

  async function savePreferences(patch: {
    templates?: TaskTemplate[];
    wip?: Partial<Record<WorkItem["status"], number>>;
    views?: SavedPlanView[];
  }) {
    try {
      const result = await consoleApi.updatePmPreferences(project.id, {
        ...patch,
        ...((patch.templates || patch.wip)
          ? { expected_shared_updated_at: preferenceRevisions.current.shared }
          : {}),
        ...(patch.views
          ? { expected_views_updated_at: preferenceRevisions.current.views }
          : {}),
      });
      setTemplates(result.templates || []);
      setWip(result.wip || {});
      setSavedViews(result.views || []);
      preferenceRevisions.current = {
        shared: result.shared_updated_at,
        views: result.views_updated_at,
      };
    } catch (reason) {
      const stale = errorText(reason, "").includes("409");
      if (stale) await reload();
      message.error(stale ? "计划配置已在另一端更新，已刷新，请重试" : errorText(reason, "计划配置保存失败"));
      throw reason;
    }
  }

  async function patchTask(task: WorkItem, patch: Partial<WorkItem>) {
    if (savingTaskIds.has(task.id)) return;
    setItems((current) =>
      current.map((item) => (item.id === task.id ? { ...item, ...patch } : item)),
    );
    setSavingTaskIds((current) => new Set(current).add(task.id));
    try {
      const updated = await consoleApi.updateWorkItem(
        project.id,
        task.id,
        patch,
      );
      setItems((current) =>
        current.map((item) => (item.id === task.id ? updated : item)),
      );
      void refreshActivitySilently();
    } catch (reason) {
      setItems((current) =>
        current.map((item) => (item.id === task.id ? task : item)),
      );
      message.error(errorText(reason, "任务更新失败"));
    } finally {
      setSavingTaskIds((current) => {
        const next = new Set(current);
        next.delete(task.id);
        return next;
      });
    }
  }

  async function deleteTask(task: WorkItem) {
    try {
      await consoleApi.deleteWorkItem(project.id, task.id);
      message.success("任务已删除");
      await reload();
    } catch (reason) {
      message.error(errorText(reason, "任务删除失败"));
    }
  }

  async function batchPatch(patch: Partial<WorkItem>) {
    if (!selected.length) return;
    const ids = selected.filter((id) => !savingTaskIds.has(id));
    if (!ids.length) return;
    const originals = new Map(
      items
        .filter((item) => ids.includes(item.id))
        .map((item) => [item.id, item]),
    );
    setItems((current) =>
      current.map((item) => (ids.includes(item.id) ? { ...item, ...patch } : item)),
    );
    setSavingTaskIds((current) => new Set([...current, ...ids]));
    const results = await Promise.allSettled(
      ids.map((id) => consoleApi.updateWorkItem(project.id, id, patch)),
    );
    const failedIds = new Set<string>();
    const returned = new Map<string, WorkItem>();
    results.forEach((result, index) => {
      const id = ids[index];
      if (result.status === "fulfilled") returned.set(id, result.value);
      else failedIds.add(id);
    });
    setItems((current) =>
      current.map(
        (item) =>
          returned.get(item.id) ||
          (failedIds.has(item.id) ? originals.get(item.id) || item : item),
      ),
    );
    setSavingTaskIds((current) => {
      const next = new Set(current);
      ids.forEach((id) => next.delete(id));
      return next;
    });
    if (failedIds.size) {
      setSelected([...failedIds]);
      message.error(
        `${ids.length - failedIds.size} 项已更新，${failedIds.size} 项失败并已回滚`,
      );
    } else {
      message.success(`已更新 ${ids.length} 个任务`);
      setSelected([]);
    }
    if (returned.size) void refreshActivitySilently();
  }

  async function saveTask(values: TaskDraft) {
    setTaskSaving(true);
    try {
      const body: TaskDraft = {
        ...values,
        labels: Array.isArray(values.labels) ? values.labels : [],
        assignee: values.assignee || "",
        milestone_id: values.milestone_id || "",
        sprint_id: values.sprint_id || "",
        parent_id: values.parent_id || "",
        dependency_ids: Array.isArray(values.dependency_ids) ? values.dependency_ids : [],
        start_date: values.start_date || "",
        due_date: values.due_date || "",
      };
      if (editing)
        await consoleApi.updateWorkItem(project.id, editing.id, body);
      else await consoleApi.createWorkItem(project.id, body);
      message.success(editing ? "任务已保存" : "任务已创建");
      setTaskDirty(false);
      setEditing(undefined);
      await reload();
    } catch (reason) {
      message.error(errorText(reason, "任务保存失败"));
    } finally {
      setTaskSaving(false);
    }
  }

  const roots = useMemo(() => items.filter((item) => !item.parent_id), [items]);
  const value = useMemo<ProjectWorkContextValue>(
    () => ({
      project,
      items,
      roots,
      members,
      milestones,
      health,
      customFields,
      sprints,
      selectedSprintId,
      setSelectedSprintId,
      activity,
      loading,
      savingTaskIds,
      selected,
      setSelected,
      reload,
      navigateToTab: onNavigateTab,
      openTask,
      patchTask,
      deleteTask,
      batchPatch,
      templates,
      wip,
      savedViews,
      savePreferences,
      openTemplate,
      deleteTemplate,
    }),
    [
      project,
      items,
      roots,
      members,
      milestones,
      health,
      customFields,
      sprints,
      selectedSprintId,
      activity,
      loading,
      savingTaskIds,
      taskDirty,
      selected,
      onNavigateTab,
      templates,
      wip,
      savedViews,
    ],
  );

  return (
    <ProjectWorkContext.Provider value={value}>
      {children}
      <Drawer
        width="min(1120px, 100vw)"
        open={editing !== undefined}
        title={
          <Space size={8} wrap>
            <span>
              {editing
                ? `任务 · ${watchedTaskTitle || editing.title}`
                : "新建任务"}
            </span>
            {taskDirty && <Badge status="warning" text="未保存" />}
            {watchedMilestone && (
              <Tag color="blue">{watchedMilestone.name}</Tag>
            )}
            {watchedSprint && <Tag color="cyan">{watchedSprint.name}</Tag>}
            {taskEditorReadOnly && <Tag>只读历史任务</Tag>}
            {editing === null && !watchedSprint && <Tag>待规划</Tag>}
          </Space>
        }
        onClose={closeTaskEditor}
        maskClosable={!taskSaving}
        closable={!taskSaving}
        destroyOnHidden
        extra={
          canWrite(project) && !taskEditorReadOnly && (
            <Space>
              {editing && (
                <Button
                  icon={<SaveOutlined />}
                  disabled={taskSaving}
                  onClick={() => setTemplateOpen(true)}
                >
                  存为模板
                </Button>
              )}
              <Button
                type="primary"
                loading={taskSaving}
                disabled={!taskDirty || taskSaving}
                onClick={() => form.submit()}
              >
                保存
              </Button>
            </Space>
          )
        }
      >
        <Form
          form={form}
          layout="vertical"
          disabled={!canWrite(project) || taskEditorReadOnly}
          onValuesChange={() => setTaskDirty(true)}
          onFinishFailed={({ errorFields }) => {
            const names = errorFields.map(({ name }) =>
              String(name[0] || ""),
            );
            if (names.includes("title") || names.includes("description"))
              setTaskEditorStep("content");
            else if (
              names.some((name) =>
                [
                  "milestone_id",
                  "sprint_id",
                  "start_date",
                  "due_date",
                  "parent_id",
                  "dependency_ids",
                ].includes(name),
              )
            )
              setTaskEditorStep("plan");
            else setTaskEditorStep("advanced");
          }}
          onFinish={saveTask}
        >
          <Tabs
            className="task-editor-tabs"
            activeKey={taskEditorStep}
            onChange={(key) => setTaskEditorStep(key as TaskEditorStep)}
            items={[
              {
                key: "content",
                label: "1 内容与属性",
                forceRender: true,
                children: (
                  <div className="task-editor-content-layout">
                    <Card
                      size="small"
                      title="任务内容"
                      className="task-editor-section task-editor-content-card"
                    >
                      <Form.Item
                        name="title"
                        label="标题"
                        rules={[{ required: true, whitespace: true }]}
                      >
                        <Input
                          maxLength={300}
                          placeholder="用一句话说明要完成什么"
                        />
                      </Form.Item>
                      <Form.Item
                        name="description"
                        label="任务内容"
                        extra="建议写清背景、目标、实施要点和验收标准。"
                      >
                        <MarkdownEditor
                          disabled={!canWrite(project) || taskEditorReadOnly}
                        />
                      </Form.Item>
                    </Card>
                    <Card
                      size="small"
                      title="任务属性"
                      className="task-editor-section"
                    >
                      <Form.Item name="status" label="状态">
                        <Select options={[...STATUS_OPTIONS]} />
                      </Form.Item>
                      <Form.Item name="priority" label="优先级">
                        <Select options={[...PRIORITY_OPTIONS]} />
                      </Form.Item>
                      <Form.Item name="assignee" label="负责人">
                        <Select
                          allowClear
                          showSearch
                          optionFilterProp="label"
                          placeholder="未指派"
                          options={members.map((member) => ({
                            value: member.account_id,
                            label: member.name,
                          }))}
                        />
                      </Form.Item>
                      <Alert
                        type="info"
                        showIcon
                        message="先写清任务，再安排计划"
                        description="标题和内容用于说明要做什么；负责人和优先级用于明确当前执行责任。"
                      />
                    </Card>
                  </div>
                ),
              },
              {
                key: "plan",
                label: "2 计划与关系",
                forceRender: true,
                children: (
                  <div className="task-editor-plan">
                    <Alert
                      className="task-plan-summary"
                      type="info"
                      showIcon
                      message="当前计划摘要"
                      description={
                        <Space size={[6, 6]} wrap>
                          {watchedMilestoneId && (
                            <Tag color="blue">
                              里程碑：
                              {milestones.find(
                                (item) => item.id === watchedMilestoneId,
                              )?.name || "未识别"}
                            </Tag>
                          )}
                          {watchedSprintId && (
                            <Tag color="cyan">
                              Sprint：
                              {sprints.find(
                                (item) => item.id === watchedSprintId,
                              )?.name || "未识别"}
                            </Tag>
                          )}
                          {(watchedStartDate || watchedDueDate) && (
                            <Tag>
                              时间：{watchedStartDate || "未设置"} →{" "}
                              {watchedDueDate || "未设置"}
                            </Tag>
                          )}
                          {watchedParentId && (
                            <Tag color="purple">
                              父任务：
                              {items.find(
                                (item) => item.id === watchedParentId,
                              )?.title || "未识别"}
                            </Tag>
                          )}
                          {watchedDependencyIds.length > 0 && (
                            <Tag color="orange">
                              前置依赖：{watchedDependencyIds.length} 项
                            </Tag>
                          )}
                          {!watchedMilestoneId &&
                            !watchedSprintId &&
                            !watchedStartDate &&
                            !watchedDueDate &&
                            !watchedParentId &&
                            watchedDependencyIds.length === 0 && (
                              <Typography.Text type="secondary">
                                尚未设置计划归属、时间或任务关系
                              </Typography.Text>
                            )}
                        </Space>
                      }
                    />
                    {taskPlanWarnings.length > 0 && (
                      <Alert
                        type="warning"
                        showIcon
                        message="计划范围需要确认"
                        description={
                          <ul className="task-plan-warning-list">
                            {taskPlanWarnings.map((warning) => (
                              <li key={warning}>{warning}</li>
                            ))}
                          </ul>
                        }
                      />
                    )}
                    <div className="task-editor-plan-grid">
                      <Card
                        size="small"
                        title="计划归属与时间"
                        className="task-editor-section"
                      >
                        <Row gutter={12}>
                          <Col xs={24} sm={12}>
                            <Form.Item name="milestone_id" label="里程碑">
                              <Select
                                allowClear
                                showSearch
                                optionFilterProp="label"
                                options={milestones.map((milestone) => ({
                                  value: milestone.id,
                                  label: milestone.name,
                                }))}
                                popupRender={(menu) => (
                                  <>
                                    {menu}
                                    {canWrite(project) &&
                                      !taskEditorReadOnly && (
                                      <Button
                                        type="text"
                                        block
                                        icon={<PlusOutlined />}
                                        className="task-plan-create"
                                        onMouseDown={(event) =>
                                          event.preventDefault()
                                        }
                                        onClick={() =>
                                          openQuickPlan("milestone")
                                        }
                                      >
                                        新建里程碑
                                      </Button>
                                    )}
                                  </>
                                )}
                              />
                            </Form.Item>
                          </Col>
                          <Col xs={24} sm={12}>
                            <Form.Item name="sprint_id" label="Sprint / 周期">
                              <Select
                                allowClear
                                showSearch
                                optionFilterProp="label"
                                onChange={(value) => {
                                  const sprint = sprints.find(
                                    (item) => item.id === value,
                                  );
                                  if (sprint?.milestone_id)
                                    form.setFieldValue(
                                      "milestone_id",
                                      sprint.milestone_id,
                                    );
                                  setTaskDirty(true);
                                }}
                                options={sprints.map((sprint) => ({
                                  value: sprint.id,
                                  label: sprint.milestone_id
                                    ? `${sprint.name} · ${
                                        milestones.find(
                                          (milestone) =>
                                            milestone.id ===
                                            sprint.milestone_id,
                                        )?.name || "未识别里程碑"
                                      }`
                                    : sprint.name,
                                }))}
                                popupRender={(menu) => (
                                  <>
                                    {menu}
                                    {canWrite(project) &&
                                      !taskEditorReadOnly && (
                                      <Button
                                        type="text"
                                        block
                                        icon={<PlusOutlined />}
                                        className="task-plan-create"
                                        onMouseDown={(event) =>
                                          event.preventDefault()
                                        }
                                        onClick={() =>
                                          openQuickPlan("sprint")
                                        }
                                      >
                                        新建 Sprint
                                      </Button>
                                    )}
                                  </>
                                )}
                              />
                            </Form.Item>
                          </Col>
                        </Row>
                        <Row gutter={12}>
                          <Col xs={24} sm={12}>
                            <Form.Item name="start_date" label="开始日期">
                              <Input type="date" />
                            </Form.Item>
                          </Col>
                          <Col xs={24} sm={12}>
                            <Form.Item
                              name="due_date"
                              label="截止日期"
                              dependencies={["start_date"]}
                              rules={[
                                ({ getFieldValue }) => ({
                                  validator: async (_rule, dueDate) => {
                                    const startDate =
                                      getFieldValue("start_date");
                                    if (
                                      !startDate ||
                                      !dueDate ||
                                      startDate <= dueDate
                                    )
                                      return;
                                    throw new Error(
                                      "截止日期不能早于开始日期",
                                    );
                                  },
                                }),
                              ]}
                            >
                              <Input type="date" />
                            </Form.Item>
                          </Col>
                        </Row>
                      </Card>
                      <Card
                        size="small"
                        title="任务逻辑关系"
                        className="task-editor-section"
                      >
                        <Form.Item
                          name="parent_id"
                          label="父任务"
                          extra="父任务表示层级归属，不代表执行先后。"
                        >
                          <Select
                            allowClear
                            showSearch
                            optionFilterProp="label"
                            options={items
                              .filter(
                                (item) =>
                                  item.id !== editing?.id &&
                                  (!editing ||
                                    !isDescendant(items, editing.id, item.id)),
                              )
                              .map((item) => ({
                                value: item.id,
                                label: `${item.title} · ${STATUS_META[item.status].label}`,
                              }))}
                          />
                        </Form.Item>
                        <Form.Item
                          name="dependency_ids"
                          label="前置依赖"
                          extra="所选任务完成后，本任务才具备开始条件；系统会拒绝依赖环。"
                        >
                          <Select
                            mode="multiple"
                            allowClear
                            showSearch
                            optionFilterProp="label"
                            options={items
                              .filter((item) => item.id !== editing?.id)
                              .map((item) => ({
                                value: item.id,
                                label: `${item.title} · ${STATUS_META[item.status].label} · ${item.assignee_name || "未指派"}${item.due_date ? ` · ${item.due_date}` : ""}`,
                              }))}
                          />
                        </Form.Item>
                        {editing &&
                          items.some((item) =>
                            item.dependency_ids?.includes(editing.id),
                          ) && (
                            <div className="task-blocks-summary">
                              <Typography.Text type="secondary">
                                本任务阻塞：
                              </Typography.Text>
                              <Space size={[4, 4]} wrap>
                                {items
                                  .filter((item) =>
                                    item.dependency_ids?.includes(editing.id),
                                  )
                                  .map((item) => (
                                    <Tag key={item.id}>{item.title}</Tag>
                                  ))}
                              </Space>
                            </div>
                          )}
                      </Card>
                    </div>
                  </div>
                ),
              },
              {
                key: "advanced",
                label: "3 更多信息",
                forceRender: true,
                children: (
                  <Card
                    size="small"
                    title="执行与补充信息"
                    className="task-editor-section"
                  >
                    <div className="task-editor-advanced-grid">
                      <div>
                        <Row gutter={12}>
                          <Col xs={24} sm={12}>
                            <Form.Item name="estimate_h" label="预估工时">
                              <InputNumber
                                min={0}
                                className="full-width"
                                addonAfter="h"
                              />
                            </Form.Item>
                          </Col>
                          <Col xs={24} sm={12}>
                            <Form.Item name="spent_h" label="投入工时">
                              <InputNumber
                                min={0}
                                className="full-width"
                                addonAfter="h"
                              />
                            </Form.Item>
                          </Col>
                        </Row>
                        <Form.Item name="labels" label="标签">
                          <Select mode="tags" tokenSeparators={[","]} />
                        </Form.Item>
                      </div>
                      <div>
                        <Form.Item name="source" label="来源">
                          <Input maxLength={80} />
                        </Form.Item>
                        {customFields.map((field) => (
                          <Form.Item
                            key={field.id}
                            name={["custom_fields", field.id]}
                            label={field.name}
                            rules={
                              field.required ? [{ required: true }] : undefined
                            }
                          >
                            {field.field_type === "number" ? (
                              <InputNumber className="full-width" />
                            ) : field.field_type === "boolean" ? (
                              <Select
                                allowClear
                                options={[
                                  { value: true, label: "是" },
                                  { value: false, label: "否" },
                                ]}
                              />
                            ) : field.field_type === "select" ? (
                              <Select
                                allowClear
                                options={field.options.map((fieldValue) => ({
                                  value: fieldValue,
                                  label: fieldValue,
                                }))}
                              />
                            ) : (
                              <Input
                                type={
                                  field.field_type === "date" ? "date" : "text"
                                }
                                maxLength={500}
                              />
                            )}
                          </Form.Item>
                        ))}
                      </div>
                    </div>
                  </Card>
                ),
              },
            ]}
          />
          {editing && (
            <Card
              size="small"
              title={
                <Space>
                  子任务
                  <Tag>
                    {
                      items.filter((item) => item.parent_id === editing.id)
                        .length
                    }
                  </Tag>
                </Space>
              }
              extra={
                canWrite(project) && !taskEditorReadOnly && (
                  <Button
                    type="link"
                    icon={<PlusOutlined />}
                    onClick={() => openChild(editing)}
                  >
                    新增子任务
                  </Button>
                )
              }
            >
              <List
                dataSource={items.filter(
                  (item) => item.parent_id === editing.id,
                )}
                locale={{ emptyText: "暂无子任务" }}
                renderItem={(child) => (
                  <List.Item
                    actions={[
                      <Button
                        key="open"
                        type="link"
                        onClick={() => openTask(child)}
                      >
                        详情
                      </Button>,
                      ...(canWrite(project) && !taskEditorReadOnly
                        ? [
                            <Popconfirm
                              key="delete"
                              title="删除此子任务？"
                              onConfirm={() => deleteTask(child)}
                            >
                              <Button type="link" danger>
                                删除
                              </Button>
                            </Popconfirm>,
                          ]
                        : []),
                    ]}
                  >
                    <Checkbox
                      disabled={
                        !canWrite(project) ||
                        taskEditorReadOnly ||
                        savingTaskIds.has(child.id)
                      }
                      aria-label={`${child.title} 完成状态`}
                      checked={child.status === "done"}
                      onChange={(event) =>
                        void patchTask(child, {
                          status: event.target.checked ? "done" : "todo",
                        })
                      }
                    >
                      {child.title}
                    </Checkbox>
                  </List.Item>
                )}
              />
            </Card>
          )}
          {editing && (
            <Card size="small" title="任务协作" className="section-card">
              <List
                dataSource={taskComments}
                locale={{ emptyText: "暂无任务评论" }}
                renderItem={(comment) => (
                  <List.Item>
                    <List.Item.Meta
                      title={
                        comment.author_name || comment.account_name || "成员"
                      }
                      description={
                        <>
                          <Typography.Paragraph>
                            {comment.body}
                          </Typography.Paragraph>
                          <Typography.Text type="secondary">
                            {comment.created_at
                              ? new Date(
                                  comment.created_at * 1000,
                                ).toLocaleString()
                              : ""}
                          </Typography.Text>
                        </>
                      }
                    />
                  </List.Item>
                )}
              />
              {canWrite(project) && !taskEditorReadOnly && (
                <Form
                  form={commentForm}
                  layout="inline"
                  onFinish={async ({ body }) => {
                    try {
                      await consoleApi.createWorkItemComment(
                        project.id,
                        editing.id,
                        body,
                      );
                      commentForm.resetFields();
                      setTaskComments(
                        (
                          await consoleApi.workItemComments(
                            project.id,
                            editing.id,
                          )
                        ).comments || [],
                      );
                    } catch (reason) {
                      message.error(errorText(reason, "评论发送失败"));
                    }
                  }}
                >
                  <Form.Item
                    name="body"
                    className="flex-field"
                    rules={[{ required: true, whitespace: true }]}
                  >
                    <Input placeholder="评论，可 @成员" />
                  </Form.Item>
                  <Button type="primary" htmlType="submit">
                    发送
                  </Button>
                </Form>
              )}
              {taskActivity.length > 0 && (
                <Timeline
                  className="section-card"
                  items={taskActivity.slice(0, 12).map((event) => ({
                    children: `${event.actor || "系统"} ${event.detail || event.kind}`,
                  }))}
                />
              )}
            </Card>
          )}
        </Form>
        {editing && (
          <WorkItemExecution
            project={project}
            workItem={editing}
            onWorkItemUpdated={syncWorkItemProjection}
          />
        )}
      </Drawer>
      <Modal
        title="存为任务模板"
        open={templateOpen}
        onCancel={() => setTemplateOpen(false)}
        onOk={() => templateForm.submit()}
        destroyOnHidden
      >
        <Form form={templateForm} layout="vertical" onFinish={saveTemplate}>
          <Form.Item
            name="name"
            label="模板名称"
            rules={[{ required: true, whitespace: true }]}
          >
            <Input maxLength={40} />
          </Form.Item>
        </Form>
      </Modal>
      <Modal
        title={quickPlanKind === "milestone" ? "新建里程碑" : "新建 Sprint"}
        open={quickPlanKind !== null}
        onCancel={() => setQuickPlanKind(null)}
        onOk={() => quickPlanForm.submit()}
        confirmLoading={quickPlanSaving}
        maskClosable={!quickPlanSaving}
        closable={!quickPlanSaving}
        destroyOnHidden
      >
        <Form form={quickPlanForm} layout="vertical" onFinish={saveQuickPlan}>
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, whitespace: true }]}
          >
            <Input maxLength={120} autoFocus />
          </Form.Item>
          {quickPlanKind === "milestone" ? (
            <>
              <Form.Item name="description" label="说明">
                <Input.TextArea rows={3} maxLength={1000} />
              </Form.Item>
              <Form.Item name="due_date" label="截止日期">
                <Input type="date" />
              </Form.Item>
            </>
          ) : (
            <>
              <Form.Item name="milestone_id" label="所属里程碑">
                <Select
                  allowClear
                  placeholder="未关联里程碑"
                  options={milestones.map((milestone) => ({
                    value: milestone.id,
                    label: milestone.name,
                  }))}
                />
              </Form.Item>
              <Form.Item name="goal" label="Sprint 目标">
                <Input.TextArea rows={3} maxLength={1000} />
              </Form.Item>
              <Row gutter={12}>
                <Col span={12}>
                  <Form.Item
                    name="start_date"
                    label="开始日期"
                    rules={[{ required: true }]}
                  >
                    <Input type="date" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item
                    name="end_date"
                    label="结束日期"
                    dependencies={["start_date", "milestone_id"]}
                    rules={[
                      { required: true },
                      ({ getFieldValue }) => ({
                        validator(_, value) {
                          const start = getFieldValue("start_date");
                          return !value || !start || value >= start
                            ? Promise.resolve()
                            : Promise.reject(new Error("结束日期不能早于开始日期"));
                        },
                      }),
                      ({ getFieldValue }) => ({
                        warningOnly: true,
                        validator(_, value) {
                          const milestone = milestones.find(
                            (item) =>
                              item.id === getFieldValue("milestone_id"),
                          );
                          return !value ||
                            !milestone?.due_date ||
                            value <= milestone.due_date
                            ? Promise.resolve()
                            : Promise.reject(
                                new Error(
                                  `结束日期晚于里程碑截止日期 ${milestone.due_date}`,
                                ),
                              );
                        },
                      }),
                    ]}
                  >
                    <Input type="date" />
                  </Form.Item>
                </Col>
              </Row>
            </>
          )}
        </Form>
      </Modal>
    </ProjectWorkContext.Provider>
  );
}

export function ProjectWorkspaceActions({
  activeTab,
}: {
  activeTab: ProjectWorkspaceTab;
}) {
  const { project, openTask } = useProjectWork();
  if (
    !canWrite(project) ||
    activeTab === "plan" ||
    activeTab === "backlog" ||
    activeTab === "tasks" ||
    activeTab === "milestones" ||
    activeTab === "sprints" ||
    activeTab === "iterations" ||
    activeTab === "governance"
    || activeTab === "assets"
  )
    return null;
  return (
    <Button
      type="primary"
      icon={<PlusOutlined />}
      onClick={() => openTask(null)}
    >
      新建任务
    </Button>
  );
}

export function ProjectOverview() {
  const {
    project,
    items,
    roots,
    milestones,
    health,
    activity,
    loading,
    navigateToTab,
    openTask,
  } = useProjectWork();
  const [liveHealth, setLiveHealth] = useState<ProjectHealth | null>(health);
  useEffect(() => {
    let active = true;
    consoleApi.projectHealth(project.id).then((result) => {
      if (active) setLiveHealth(result);
    }).catch(() => {});
    return () => { active = false; };
  }, [project.id]);
  const effectiveHealth = liveHealth || health;
  const done = roots.filter((item) => item.status === "done").length;
  const doing = roots.filter((item) => item.status === "doing").length;
  const overdue = roots.filter(
    (item) =>
      item.due_date && item.due_date < today() && item.status !== "done",
  ).length;
  const percent = roots.length ? Math.round((done / roots.length) * 100) : 0;
  const healthMeta = effectiveHealth?.status === "critical"
    ? { label: "严重", color: "error" as const, type: "error" as const }
    : effectiveHealth?.status === "attention"
      ? { label: "需关注", color: "warning" as const, type: "warning" as const }
      : { label: "健康", color: "success" as const, type: "success" as const };
  return (
    <div className="tab-stack">
      {!loading && !roots.length && (
        <Alert
          showIcon
          type="info"
          title="项目尚无任务"
          description={
            canWrite(project)
              ? "使用右上角“新建任务”即可开始；里程碑和 Sprint 可按需稍后配置。"
              : "此项目尚未创建任务，你可以查看现有的计划配置。"
          }
          action={(
            <Button size="small" onClick={() => navigateToTab("milestones")}>
              {canWrite(project) ? "按需配置计划" : "查看计划"}
            </Button>
          )}
        />
      )}
      <Card
        title="项目健康"
        loading={loading && !effectiveHealth}
        extra={<Space wrap><Tag color={healthMeta.color}>{healthMeta.label}</Tag><Typography.Text type="secondary">Server 实时计算</Typography.Text></Space>}
      >
        <Alert
          showIcon
          type={healthMeta.type}
          title={effectiveHealth?.reasons.length ? effectiveHealth.reasons.map((reason) => `${reason.label} ${reason.count}`).join("；") : "当前没有需要介入的项目风险信号"}
          description={effectiveHealth ? (
            <Space wrap>
              <Tag>阻塞任务 {effectiveHealth.summary.blocked_tasks}</Tag>
              <Tag>逾期任务 {effectiveHealth.summary.overdue_tasks}</Tag>
              <Tag>逾期里程碑 {effectiveHealth.summary.overdue_milestones}</Tag>
              <Tag color={effectiveHealth.summary.critical_risks ? "red" : undefined}>严重风险 {effectiveHealth.summary.critical_risks}</Tag>
              <Tag color={effectiveHealth.summary.high_risks ? "orange" : undefined}>高风险 {effectiveHealth.summary.high_risks}</Tag>
              <Tag>待决策 {effectiveHealth.summary.pending_decisions}</Tag>
              {(effectiveHealth.summary.open_risks || effectiveHealth.summary.pending_decisions) > 0 && <Button type="link" size="small" onClick={() => navigateToTab("governance")}>查看治理台账</Button>}
            </Space>
          ) : "正在读取项目健康数据"}
        />
      </Card>
      <ProjectExecutionAnalyticsPanel
        project={project}
        items={items}
        onOpenTask={(item) => openTask(item, {}, project.role === "Viewer")}
      />
      <Row gutter={[16, 16]}>
        <Col xs={12} xl={6}>
          <Card loading={loading}>
            <Statistic
              title="任务总数"
              value={roots.length}
              prefix={<FlagOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} xl={6}>
          <Card loading={loading}>
            <Statistic
              title="进行中"
              value={doing}
              prefix={<ClockCircleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} xl={6}>
          <Card loading={loading}>
            <Statistic
              title="已完成"
              value={done}
              prefix={<CheckCircleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} xl={6}>
          <Card loading={loading}>
            <Statistic
              title="已逾期"
              value={overdue}
              prefix={<CalendarOutlined />}
            />
          </Card>
        </Col>
      </Row>
      <Card
        title="整体进度"
        extra={
          <Typography.Text type="secondary">
            {done}/{roots.length}
          </Typography.Text>
        }
      >
        <Progress
          percent={percent}
          status={percent === 100 ? "success" : "active"}
        />
      </Card>
      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <MilestoneCard
            project={project}
            roots={roots}
            milestones={milestones}
            health={effectiveHealth}
            editable={false}
          />
        </Col>
        <Col xs={24} xl={12}>
          <Card title="近期活动" className="project-overview-card">
            {activity.length ? (
              <Timeline
                items={activity.slice(0, 12).map((item) => ({
                  children: (
                    <>
                      <Typography.Text strong>
                        {item.actor || "系统"}
                      </Typography.Text>{" "}
                      {item.detail || item.kind}
                      <div>
                        <Typography.Text type="secondary">
                          {item.created_at
                            ? new Date(item.created_at * 1000).toLocaleString()
                            : ""}
                        </Typography.Text>
                      </div>
                    </>
                  ),
                }))}
              />
            ) : (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="暂无任务活动"
              />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
}

function MilestoneCard({
  project,
  roots,
  milestones,
  health,
  editable = true,
  onCreateSprint,
}: {
  project: Project;
  roots: WorkItem[];
  milestones: Milestone[];
  health?: ProjectHealth | null;
  editable?: boolean;
  onCreateSprint?: (milestone: Milestone) => void;
}) {
  const { message } = App.useApp();
  const { reload, navigateToTab, sprints } = useProjectWork();
  const [open, setOpen] = useState(false);
  const [editingMilestone, setEditingMilestone] = useState<Milestone | null>(
    null,
  );
  const [form] = Form.useForm<Partial<Milestone> & { name: string }>();
  return (
    <Card
      title="里程碑"
      className={
        editable
          ? "project-overview-card project-settings-panel"
          : "project-overview-card"
      }
      extra={
        editable && canWrite(project) && (
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              setEditingMilestone(null);
              form.resetFields();
              form.setFieldsValue({ status: "open" });
              setOpen(true);
            }}
          >
            新建里程碑
          </Button>
        )
      }
    >
      {milestones.length ? (
        <List
          dataSource={milestones}
          renderItem={(milestone) => {
            const related = roots.filter(
              (item) => item.milestone_id === milestone.id,
            );
            const completed = related.filter(
              (item) => item.status === "done",
            ).length;
            const relatedSprints = sprints.filter(
              (sprint) => sprint.milestone_id === milestone.id,
            );
            const signal = health?.milestones.find((item) => item.id === milestone.id);
            return (
              <List.Item
                className={
                  editable && canWrite(project)
                    ? "project-settings-row is-clickable"
                    : "project-settings-row"
                }
                onClick={(event) => {
                  if (
                    !editable ||
                    !canWrite(project) ||
                    (event.target as HTMLElement).closest("button")
                  )
                    return;
                  setEditingMilestone(milestone);
                  form.setFieldsValue(milestone);
                  setOpen(true);
                }}
                actions={
                  editable && canWrite(project)
                    ? [
                        ...(onCreateSprint
                          ? [
                              <Button
                                key="new-sprint"
                                type="link"
                                size="small"
                                icon={<PlusOutlined />}
                                onClick={() => onCreateSprint(milestone)}
                              >
                                新建 Sprint
                              </Button>,
                            ]
                          : []),
                        <Popconfirm
                          key="delete"
                          title="删除此里程碑？"
                          description="关联任务会被解绑，但不会删除。"
                          onConfirm={async () => {
                            await consoleApi.deleteMilestone(
                              project.id,
                              milestone.id,
                            );
                            await reload();
                          }}
                        >
                          <Button
                            type="text"
                            danger
                            icon={<DeleteOutlined />}
                            aria-label={`删除里程碑 ${milestone.name}`}
                          />
                        </Popconfirm>,
                      ]
                    : []
                }
              >
                <List.Item.Meta
                  title={
                    <Space>
                      <Typography.Text strong>
                        {milestone.name}
                      </Typography.Text>
                      {milestone.status === "closed" && (
                        <Tag color="green">已关闭</Tag>
                      )}
                      {signal && milestone.status !== "closed" && (
                        <Tag color={signal.health === "critical" ? "red" : signal.health === "attention" ? "orange" : "green"}>
                          {signal.health === "critical" ? "严重" : signal.health === "attention" ? "需关注" : "健康"}
                        </Tag>
                      )}
                    </Space>
                  }
                  description={
                    <>
                      <Progress
                        size="small"
                        percent={
                          related.length
                            ? Math.round((completed / related.length) * 100)
                            : 0
                        }
                      />
                      <Typography.Text type="secondary">
                        {signal?.due_date || milestone.due_date
                          ? `截止 ${signal?.due_date || milestone.due_date}`
                          : "未设截止日期"}
                        {` · ${relatedSprints.length} 个 Sprint`}
                      </Typography.Text>
                      {signal?.reasons.length ? <div><Typography.Text type={signal.health === "critical" ? "danger" : "warning"}>{signal.reasons.map((reason) => ({ critical_risk: "严重风险", overdue: "已逾期", blocked_work: "阻塞任务", high_risk: "高风险", pending_decision: "待决策" })[reason] || reason).join(" · ")}</Typography.Text></div> : null}
                    </>
                  }
                />
              </List.Item>
            );
          }}
        />
      ) : (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="还没有里程碑"
        >
          {!editable && roots.length > 0 && (
            <Button onClick={() => navigateToTab("backlog")}>
              {canWrite(project) ? "前往 Backlog 规划" : "查看 Backlog"}
            </Button>
          )}
        </Empty>
      )}
      <Modal
        title={editingMilestone ? "编辑里程碑" : "新增里程碑"}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => form.submit()}
        destroyOnHidden
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={async (values) => {
            try {
              if (editingMilestone)
                await consoleApi.updateMilestone(
                  project.id,
                  editingMilestone.id,
                  values,
                );
              else await consoleApi.createMilestone(project.id, values);
              message.success(
                editingMilestone ? "里程碑已更新" : "里程碑已创建",
              );
              setOpen(false);
              setEditingMilestone(null);
              form.resetFields();
              await reload();
            } catch (reason) {
              message.error(errorText(reason, "创建失败"));
            }
          }}
        >
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, whitespace: true }]}
          >
            <Input />
          </Form.Item>
          <Form.Item name="due_date" label="截止日期">
            <Input type="date" />
          </Form.Item>
          <Form.Item name="description" label="说明">
            <Input.TextArea rows={3} maxLength={5000} />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select
              options={[
                { value: "open", label: "开放" },
                { value: "closed", label: "已关闭" },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}

export function ProjectPlan() {
  const {
    project,
    items,
    roots,
    members,
    milestones,
    sprints,
    loading,
    savingTaskIds,
    selected,
    setSelected,
    selectedSprintId,
    setSelectedSprintId,
    navigateToTab,
    openTask,
    patchTask,
    batchPatch,
    templates,
    wip,
    savedViews,
    savePreferences,
    openTemplate,
    deleteTemplate,
    reload,
  } = useProjectWork();
  const { message, modal } = App.useApp();
  const [changingSprintId, setChangingSprintId] = useState("");
  const selectedSprint = sprints.find(
    (sprint) => sprint.id === selectedSprintId,
  );
  const activeSprint = sprints.find((sprint) => sprint.status === "active");
  const suggestedSprint = orderSprints(sprints).find(
    (sprint) => sprint.status === "planned",
  );
  const canEditSelectedSprint =
    canWrite(project) && selectedSprint?.status !== "closed";
  const selectedMilestone = milestones.find(
    (milestone) => milestone.id === selectedSprint?.milestone_id,
  );
  const sprintItems = useMemo(
    () =>
      selectedSprint
        ? items.filter((item) => item.sprint_id === selectedSprint.id)
        : [],
    [items, selectedSprint],
  );
  const sprintRoots = useMemo(
    () => sprintItems.filter((item) => !item.parent_id),
    [sprintItems],
  );
  const sprintDone = sprintRoots.filter((item) => item.status === "done").length;
  const sprintPercent = sprintRoots.length
    ? Math.round((sprintDone / sprintRoots.length) * 100)
    : 0;
  useEffect(() => {
    setSelected([]);
  }, [selectedSprintId]);
  const [group, setGroup] = useState<GroupMode>("none");
  const [assignee, setAssignee] = useState("");
  const [source, setSource] = useState("");
  const [search, setSearch] = useState("");
  const [batchStatus, setBatchStatus] = useState<WorkItem["status"]>("doing");
  const [wipOpen, setWipOpen] = useState(false);
  const [viewOpen, setViewOpen] = useState(false);
  const [templateId, setTemplateId] = useState("");
  const [selectedView, setSelectedView] = useState("");
  const [viewForm] = Form.useForm<{ name: string }>();
  const sources = useMemo(
    () => [...new Set(sprintRoots.map((item) => item.source).filter(Boolean))],
    [sprintRoots],
  );
  const filtered = useMemo(
    () =>
      sprintRoots.filter((item) => {
        if (assignee && item.assignee !== assignee) return false;
        if (source && item.source !== source) return false;
        if (
          search &&
          !`${item.title} ${item.description || ""} ${(item.labels || []).join(" ")}`
            .toLowerCase()
            .includes(search.toLowerCase())
        )
          return false;
        return true;
      }),
    [sprintRoots, assignee, source, search],
  );
  const lanes = useMemo(
    () => makeLanes(filtered, group, members, milestones),
    [filtered, group, members, milestones],
  );
  const hasPlanFilters =
    group !== "none" || Boolean(assignee || source || search);

  function clearPlanFilters() {
    setGroup("none");
    setAssignee("");
    setSource("");
    setSearch("");
    setSelectedView("");
  }

  function toggleSelected(id: string, checked: boolean) {
    setSelected(
      checked
        ? [...new Set([...selected, id])]
        : selected.filter((value) => value !== id),
    );
  }

  function startSprint(sprint: Sprint) {
    modal.confirm({
      title: `开始 Sprint“${sprint.name}”？`,
      content:
        activeSprint && activeSprint.id !== sprint.id
          ? `当前 Sprint“${activeSprint.name}”会结束，任务仍保留在原 Sprint 中。`
          : "开始后，它会成为项目唯一的当前 Sprint，并作为任务看板的默认执行范围。",
      okText: activeSprint ? "切换当前 Sprint" : "开始 Sprint",
      cancelText: "取消",
      onOk: async () => {
        setChangingSprintId(sprint.id);
        try {
          await consoleApi.updateSprint(project.id, sprint.id, {
            status: "active",
          });
          setSelectedSprintId(sprint.id);
          await reload();
          message.success(`已开始 ${sprint.name}`);
        } catch (reason) {
          message.error(errorText(reason, "Sprint 启动失败"));
          throw reason;
        } finally {
          setChangingSprintId("");
        }
      },
    });
  }

  async function saveWip(values: Record<string, number | null>) {
    const next: Partial<Record<WorkItem["status"], number>> = {};
    for (const option of STATUS_OPTIONS) {
      const value = values[option.value];
      if (typeof value === "number" && value > 0) next[option.value] = value;
    }
    await savePreferences({ wip: next });
    setWipOpen(false);
  }

  function applyView(name: string) {
    setSelectedView(name);
    const view = savedViews.find((item) => item.name === name);
    if (!view) return;
    setGroup((view.filters.group as GroupMode) || "none");
    setAssignee(view.filters.assignee || "");
    setSource(view.filters.source || "");
    setSearch(view.filters.search || "");
  }

  if (loading) return <Card loading />;
  const sprintOptions = orderSprints(sprints).map((sprint) => ({
    value: sprint.id,
    label: `${sprint.name} · ${SPRINT_STATUS_META[sprint.status].label}`,
  }));
  const sprintScopeHeader = (
    <Card className="project-sprint-scope" styles={{ body: { padding: 14 } }}>
      <div className="project-sprint-scope-head">
        <div>
          <Typography.Title level={5}>Sprint 执行范围</Typography.Title>
          <Typography.Text type="secondary">
            状态、WIP、拖拽和完成率只统计当前选择的 Sprint。
          </Typography.Text>
        </div>
        <Space wrap>
          <Select
            aria-label="Sprint 执行范围"
            showSearch
            optionFilterProp="label"
            value={selectedSprintId || undefined}
            placeholder="选择 Sprint"
            options={sprintOptions}
            onChange={setSelectedSprintId}
          />
          {selectedSprint?.status === "planned" && canWrite(project) && (
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              loading={changingSprintId === selectedSprint.id}
              onClick={() => startSprint(selectedSprint)}
            >
              开始 Sprint
            </Button>
          )}
          <Button onClick={() => navigateToTab("sprints")}>Sprint 管理</Button>
        </Space>
      </div>
      {selectedSprint && (
        <div className="project-sprint-scope-summary">
          <Space size={[6, 6]} wrap>
            <Tag color={SPRINT_STATUS_META[selectedSprint.status].color}>
              {SPRINT_STATUS_META[selectedSprint.status].label}
            </Tag>
            {selectedMilestone && <Tag>{selectedMilestone.name}</Tag>}
            <Typography.Text type="secondary">
              {selectedSprint.start_date} — {selectedSprint.end_date}
            </Typography.Text>
            <Typography.Text type="secondary">
              {sprintDone}/{sprintRoots.length} 已完成
            </Typography.Text>
            {selectedSprint.status === "closed" && (
              <Typography.Text type="secondary">
                历史 Sprint 仅供查看
              </Typography.Text>
            )}
          </Space>
          <Progress percent={sprintPercent} showInfo={false} />
        </div>
      )}
    </Card>
  );
  if (!selectedSprint) {
    return (
      <div className="project-plan">
        {sprintScopeHeader}
        <Card>
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="尚无当前 Sprint"
          >
            <Space wrap>
              <Typography.Text type="secondary">
                项目看板不会回退到全项目任务。请开始一个计划中的 Sprint，建立明确的执行范围。
              </Typography.Text>
              {suggestedSprint && canWrite(project) ? (
                <Button
                  type="primary"
                  icon={<PlayCircleOutlined />}
                  loading={changingSprintId === suggestedSprint.id}
                  onClick={() => startSprint(suggestedSprint)}
                >
                  开始 {suggestedSprint.name}
                </Button>
              ) : (
                <Button
                  type={canWrite(project) ? "primary" : "default"}
                  onClick={() => navigateToTab("sprints")}
                >
                  {canWrite(project) ? "创建 Sprint" : "查看 Sprint 计划"}
                </Button>
              )}
            </Space>
          </Empty>
        </Card>
      </div>
    );
  }
  return (
    <div className="project-plan">
      {sprintScopeHeader}
      <Card className="project-plan-toolbar" styles={{ body: { padding: 12 } }}>
        <div className="project-plan-toolbar-row">
          <div
            className="project-plan-toolbar-group project-plan-toolbar-actions"
            role="group"
            aria-label="任务操作"
          >
            <Typography.Text
              className="project-plan-toolbar-label"
              type="secondary"
            >
              任务
            </Typography.Text>
            <Space wrap>
            {canEditSelectedSprint && (
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={() =>
                  openTask(null, {
                    sprint_id: selectedSprint.id,
                    milestone_id: selectedSprint.milestone_id,
                  })
                }
              >
                新建 Sprint 任务
              </Button>
            )}
            {canEditSelectedSprint && (
              <Select
                aria-label="任务模板"
                value={templateId || undefined}
                placeholder="选择任务模板"
                onChange={setTemplateId}
                options={templates.map((template) => ({
                  value: template.id,
                  label: template.name,
                }))}
              />
            )}
            {canEditSelectedSprint && (
              <Button
                disabled={!templateId}
                onClick={() =>
                  openTemplate(templateId, {
                    sprint_id: selectedSprint.id,
                    milestone_id: selectedSprint.milestone_id,
                  })
                }
              >
                使用模板
              </Button>
            )}
            {canEditSelectedSprint && (
              <Button
                aria-label="删除任务模板"
                danger
                icon={<DeleteOutlined />}
                disabled={!templateId}
                onClick={() => {
                  void deleteTemplate(templateId);
                  setTemplateId("");
                }}
                />
            )}
            </Space>
          </div>
          <div
            className="project-plan-toolbar-group project-plan-toolbar-filter"
            role="group"
            aria-label="任务筛选"
          >
            <Typography.Text
              className="project-plan-toolbar-label"
              type="secondary"
            >
              筛选
            </Typography.Text>
            <Space wrap>
            <Select
              aria-label="泳道分组"
              value={group}
              onChange={(value) => {
                setGroup(value);
                setSelectedView("");
              }}
              options={[
                { value: "none", label: "不分组" },
                { value: "assignee", label: "按负责人泳道" },
                { value: "milestone", label: "按里程碑泳道" },
              ]}
            />
            <Select
              aria-label="负责人筛选"
              allowClear
              value={assignee || undefined}
              placeholder="全部负责人"
              onChange={(value) => {
                setAssignee(value || "");
                setSelectedView("");
              }}
              options={members.map((member) => ({
                value: member.account_id,
                label: member.name,
              }))}
            />
            <Select
              aria-label="来源筛选"
              allowClear
              value={source || undefined}
              placeholder="全部来源"
              onChange={(value) => {
                setSource(value || "");
                setSelectedView("");
              }}
              options={sources.map((value) => ({ value, label: value }))}
            />
            <Input.Search
              aria-label="搜索任务"
              allowClear
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setSelectedView("");
              }}
              placeholder="搜索任务"
            />
              <Button disabled={!hasPlanFilters} onClick={clearPlanFilters}>
                清除筛选
              </Button>
            </Space>
          </div>
          <div
            className="project-plan-toolbar-group project-plan-toolbar-view"
            role="group"
            aria-label="视图设置"
          >
            <Typography.Text
              className="project-plan-toolbar-label"
              type="secondary"
            >
              视图
            </Typography.Text>
            <Space wrap>
            <Select
              aria-label="保存的视图"
              allowClear
              value={selectedView || undefined}
              placeholder="保存的视图"
              onChange={(value) => applyView(value || "")}
              options={savedViews.map((view) => ({
                value: view.name,
                label: view.name,
              }))}
            />
            {canEditSelectedSprint && (
              <Button
                aria-label="删除保存的视图"
                danger
                icon={<DeleteOutlined />}
                disabled={!selectedView}
                onClick={async () => {
                  await savePreferences({
                    views: savedViews.filter(
                      (view) => view.name !== selectedView,
                    ),
                  });
                  setSelectedView("");
                }}
              />
            )}
            {canEditSelectedSprint && (
              <Button icon={<SaveOutlined />} onClick={() => setViewOpen(true)}>
                保存视图
              </Button>
            )}
            {(project.role === "Owner" || project.role === "Admin") &&
              canEditSelectedSprint && (
                <Button onClick={() => setWipOpen(true)}>
                  当前 Sprint WIP
                </Button>
              )}
            </Space>
          </div>
        </div>
        {selected.length > 0 && canEditSelectedSprint && (
          <div className="project-batch-bar">
            <Typography.Text strong>
              已选择 {selected.length} 项
            </Typography.Text>
            <Select
              value={batchStatus}
              onChange={setBatchStatus}
              options={[...STATUS_OPTIONS]}
            />
            <Button
              type="primary"
              onClick={() => void batchPatch({ status: batchStatus })}
            >
              批量更新状态
            </Button>
            <Button onClick={() => setSelected([])}>取消选择</Button>
          </div>
        )}
      </Card>

      {filtered.length ? (
        lanes.map((lane) => (
          <section className="project-lane" key={lane.key}>
            {group !== "none" && (
              <div className="project-lane-heading">
                <Space>
                  <TeamOutlined />
                  <Typography.Text strong>{lane.label}</Typography.Text>
                  <Tag>{lane.items.length}</Tag>
                </Space>
              </div>
            )}
            <div className="project-kanban">
              {STATUS_OPTIONS.map((status) => {
                const cards = lane.items.filter(
                  (item) => item.status === status.value,
                );
                const limit = wip[status.value];
                const over = Boolean(limit && cards.length > limit);
                return (
                  <div
                    className={`project-kanban-column${over ? " is-over-wip" : ""}`}
                    key={status.value}
                    onDragOver={(event) => {
                      if (canEditSelectedSprint) event.preventDefault();
                    }}
                    onDrop={(event) => {
                      if (!canEditSelectedSprint) return;
                      const id = event.dataTransfer.getData("text/plain");
                      const task = sprintRoots.find((item) => item.id === id);
                      if (task && task.status !== status.value) {
                        const move = () =>
                          void patchTask(task, { status: status.value });
                        if (limit && cards.length >= limit)
                          Modal.confirm({
                            title: "目标列已达到 WIP 上限",
                            content: `${status.label}当前 ${cards.length}/${limit}，仍要移动吗？`,
                            okText: "仍然移动",
                            onOk: move,
                          });
                        else move();
                      }
                    }}
                  >
                    <div className="project-kanban-column-head">
                      <Space>
                        <Badge
                          status={
                            STATUS_META[status.value].color as
                              "default" | "processing" | "warning" | "success"
                          }
                        />
                        <Typography.Text strong>{status.label}</Typography.Text>
                      </Space>
                      <Typography.Text type={over ? "danger" : "secondary"}>
                        {cards.length}
                        {limit ? `/${limit}` : ""}
                      </Typography.Text>
                    </div>
                    <div className="project-kanban-cards">
                      {cards.map((task) => (
                        <Card
                          key={task.id}
                          size="small"
                          className={`project-task-card${savingTaskIds.has(task.id) ? " is-saving" : ""}`}
                          draggable={
                            canEditSelectedSprint && !savingTaskIds.has(task.id)
                          }
                          aria-busy={savingTaskIds.has(task.id)}
                          onDragStart={(event) =>
                            event.dataTransfer.setData("text/plain", task.id)
                          }
                          onClick={() =>
                            openTask(
                              task,
                              {},
                              selectedSprint.status === "closed",
                            )
                          }
                        >
                          <div className="project-task-card-title">
                            {canEditSelectedSprint && (
                              <Checkbox
                                checked={selected.includes(task.id)}
                                disabled={savingTaskIds.has(task.id)}
                                aria-label={`选择任务 ${task.title}`}
                                onClick={(event) => event.stopPropagation()}
                                onChange={(event) =>
                                  toggleSelected(task.id, event.target.checked)
                                }
                              />
                            )}
                            <Typography.Text
                              strong
                              ellipsis={{ tooltip: task.title }}
                            >
                              {task.title}
                            </Typography.Text>
                            {savingTaskIds.has(task.id) && (
                              <Tag icon={<ClockCircleOutlined />}>保存中</Tag>
                            )}
                          </div>
                          {task.description && (
                            <Typography.Paragraph
                              type="secondary"
                              ellipsis={{ rows: 2 }}
                            >
                              {taskDescriptionSummary(task.description)}
                            </Typography.Paragraph>
                          )}
                          <div className="project-task-card-meta">
                            <Space size={[4, 4]} wrap>
                              {sprintItems.some((item) => item.parent_id === task.id) && <Tag>{sprintItems.filter((item) => item.parent_id === task.id && item.status === "done").length}/{sprintItems.filter((item) => item.parent_id === task.id).length} 子任务</Tag>}
                              {task.priority && (
                                <Tag color={PRIORITY_COLORS[task.priority]}>
                                  {
                                    PRIORITY_OPTIONS.find(
                                      (item) => item.value === task.priority,
                                    )?.label
                                  }
                                </Tag>
                              )}
                              {task.assignee_name && (
                                <Tag
                                  icon={
                                    <Avatar size={16}>
                                      {task.assignee_name.slice(0, 1)}
                                    </Avatar>
                                  }
                                >
                                  {task.assignee_name}
                                </Tag>
                              )}
                              {task.due_date && (
                                <Tag icon={<CalendarOutlined />}>
                                  {task.due_date}
                                </Tag>
                              )}
                            </Space>
                            {canEditSelectedSprint && (
                              <Select
                                size="small"
                                value={task.status}
                                aria-label={`${task.title} 状态`}
                                loading={savingTaskIds.has(task.id)}
                                disabled={savingTaskIds.has(task.id)}
                                onClick={(event) => event.stopPropagation()}
                                onChange={(value) =>
                                  void patchTask(task, { status: value })
                                }
                                options={[...STATUS_OPTIONS]}
                              />
                            )}
                          </div>
                        </Card>
                      ))}
                      {!cards.length && (
                        <div className="project-kanban-empty">暂无任务</div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        ))
      ) : (
        <Card>
          <Empty
            description={
              sprintRoots.length ? "没有符合条件的任务" : "此 Sprint 还没有任务"
            }
          >
            <Space wrap>
              {!sprintRoots.length && canEditSelectedSprint && (
                <Button
                  type="primary"
                  onClick={() =>
                    openTask(null, {
                      sprint_id: selectedSprint.id,
                      milestone_id: selectedSprint.milestone_id,
                    })
                  }
                >
                  新建第一个 Sprint 任务
              </Button>
              )}
              {sprintRoots.length > 0 && hasPlanFilters && (
                <Button onClick={clearPlanFilters}>清除筛选</Button>
              )}
            </Space>
          </Empty>
        </Card>
      )}

      <Modal
        title="设置 WIP 上限"
        open={wipOpen}
        onCancel={() => setWipOpen(false)}
        footer={null}
        destroyOnHidden
      >
        <Form layout="vertical" initialValues={wip} onFinish={saveWip}>
          <Row gutter={12}>
            {STATUS_OPTIONS.map((status) => (
              <Col span={12} key={status.value}>
                <Form.Item name={status.value} label={status.label}>
                  <InputNumber
                    min={1}
                    placeholder="不限"
                    className="full-width"
                  />
                </Form.Item>
              </Col>
            ))}
          </Row>
          <Button type="primary" htmlType="submit">
            保存
          </Button>
        </Form>
      </Modal>
      <Modal
        title="保存当前视图"
        open={viewOpen}
        onCancel={() => setViewOpen(false)}
        onOk={() => viewForm.submit()}
        destroyOnHidden
      >
        <Form
          form={viewForm}
          layout="vertical"
          onFinish={async ({ name }) => {
            const next = [
              ...savedViews.filter((item) => item.name !== name),
              {
                id: globalThis.crypto?.randomUUID?.() || `view-${Date.now()}`,
                name,
                filters: { group, assignee, source, search },
              },
            ];
            await savePreferences({ views: next });
            setViewOpen(false);
            viewForm.resetFields();
          }}
        >
          <Form.Item
            name="name"
            label="视图名称"
            rules={[{ required: true, whitespace: true }]}
          >
            <Input maxLength={40} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

function makeLanes(
  items: WorkItem[],
  group: GroupMode,
  members: Member[],
  milestones: Milestone[],
) {
  if (group === "none") return [{ key: "all", label: "全部任务", items }];
  const groups = new Map<
    string,
    { key: string; label: string; items: WorkItem[] }
  >();
  for (const item of items) {
    const key =
      group === "assignee"
        ? item.assignee || "unassigned"
        : item.milestone_id || "no-milestone";
    const label =
      group === "assignee"
        ? members.find((member) => member.account_id === item.assignee)?.name ||
          item.assignee_name ||
          "未指派"
        : milestones.find((milestone) => milestone.id === item.milestone_id)
            ?.name || "无里程碑";
    const current = groups.get(key) || { key, label, items: [] };
    current.items.push(item);
    groups.set(key, current);
  }
  return [...groups.values()];
}

function orderTasksForTable(items: WorkItem[]): WorkItem[] {
  const children = new Map<string, WorkItem[]>();
  for (const item of items) {
    const bucket = children.get(item.parent_id) || [];
    bucket.push(item);
    children.set(item.parent_id, bucket);
  }
  const ordered: WorkItem[] = [];
  const visited = new Set<string>();
  const append = (item: WorkItem) => {
    if (visited.has(item.id)) return;
    visited.add(item.id);
    ordered.push(item);
    for (const child of children.get(item.id) || []) append(child);
  };
  for (const root of children.get("") || []) append(root);
  // 兼容修复前留下的孤儿或异常关系，确保它们不会从管理界面消失。
  for (const item of items) append(item);
  return ordered;
}

export function ProjectTasks({
  scope = "all",
}: {
  scope?: ProjectTaskListScope;
} = {}) {
  const {
    project,
    items,
    members,
    milestones,
    sprints,
    loading,
    savingTaskIds,
    selected,
    setSelected,
    reload,
    openTask,
    patchTask,
    deleteTask,
    batchPatch,
  } = useProjectWork();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [assignee, setAssignee] = useState("");
  const [priority, setPriority] = useState("");
  const [milestoneId, setMilestoneId] = useState("");
  const [sprintId, setSprintId] = useState("");
  const [batchStatus, setBatchStatus] = useState<WorkItem["status"]>("doing");
  useEffect(() => {
    setSelected([]);
  }, [scope]);
  const scopedItems = useMemo(
    () =>
      scope === "backlog"
        ? items.filter((item) => !item.sprint_id)
        : items,
    [items, scope],
  );
  const orderedItems = useMemo(
    () => orderTasksForTable(scopedItems),
    [scopedItems],
  );
  const filtered = orderedItems.filter(
    (item) =>
      (!search ||
        `${item.title} ${item.description || ""}`
          .toLowerCase()
          .includes(search.toLowerCase())) &&
      (!status || item.status === status) &&
      (!assignee || item.assignee === assignee) &&
      (!priority ||
        (priority === "__none__"
          ? !item.priority
          : item.priority === priority)) &&
      (!milestoneId || item.milestone_id === milestoneId) &&
      (!sprintId ||
        (sprintId === "__unplanned__"
          ? !item.sprint_id
          : item.sprint_id === sprintId)),
  );
  const hasTaskFilters = Boolean(
    search || status || assignee || priority || milestoneId || sprintId,
  );

  function clearTaskFilters() {
    setSearch("");
    setStatus("");
    setAssignee("");
    setPriority("");
    setMilestoneId("");
    setSprintId("");
  }
  const columns: ProColumns<WorkItem>[] = [
    {
      title: "任务",
      dataIndex: "title",
      width: 300,
      fixed: "left",
      render: (_value, item) => (
        <Button
          type="link"
          className={`project-task-link${item.parent_id ? " project-task-child" : ""}`}
          onClick={() => openTask(item)}
        >
          <span>
            <Typography.Text strong>{item.title}</Typography.Text>
            {savingTaskIds.has(item.id) && (
              <Tag icon={<ClockCircleOutlined />}>保存中</Tag>
            )}
            {items.some((child) => child.parent_id === item.id) && <Tag>{items.filter((child) => child.parent_id === item.id && child.status === "done").length}/{items.filter((child) => child.parent_id === item.id).length} 子任务</Tag>}
            {item.description && (
              <Typography.Text type="secondary" ellipsis>
                {taskDescriptionSummary(item.description)}
              </Typography.Text>
            )}
          </span>
        </Button>
      ),
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 130,
      render: (_value, item) => (
        <Select
          size="small"
          value={item.status}
          aria-label={`${item.title} 状态`}
          loading={savingTaskIds.has(item.id)}
          disabled={!canWrite(project) || savingTaskIds.has(item.id)}
          options={[...STATUS_OPTIONS]}
          onChange={(value) => void patchTask(item, { status: value })}
        />
      ),
    },
    {
      title: "优先级",
      dataIndex: "priority",
      width: 120,
      render: (_value, item) => (
        <Select
          size="small"
          value={item.priority}
          aria-label={`${item.title} 优先级`}
          loading={savingTaskIds.has(item.id)}
          disabled={!canWrite(project) || savingTaskIds.has(item.id)}
          options={[...PRIORITY_OPTIONS]}
          onChange={(value) => void patchTask(item, { priority: value })}
        />
      ),
    },
    {
      title: "负责人",
      dataIndex: "assignee_name",
      width: 150,
      render: (_value, item) => (
        <Select
          size="small"
          allowClear
          showSearch
          optionFilterProp="label"
          value={item.assignee || undefined}
          placeholder="未指派"
          aria-label={`${item.title} 负责人`}
          loading={savingTaskIds.has(item.id)}
          disabled={!canWrite(project) || savingTaskIds.has(item.id)}
          options={members.map((member) => ({
            value: member.account_id,
            label: member.name,
          }))}
          onChange={(value) => void patchTask(item, { assignee: value || "" })}
        />
      ),
    },
    {
      title: "里程碑",
      dataIndex: "milestone_id",
      width: 160,
      render: (_value, item) => (
        <Select
          size="small"
          allowClear
          showSearch
          optionFilterProp="label"
          value={item.milestone_id || undefined}
          placeholder="无里程碑"
          aria-label={`${item.title} 里程碑`}
          loading={savingTaskIds.has(item.id)}
          disabled={!canWrite(project) || savingTaskIds.has(item.id)}
          options={milestones.map((milestone) => ({
            value: milestone.id,
            label: milestone.name,
          }))}
          onChange={(value) => void patchTask(item, { milestone_id: value || "" })}
        />
      ),
    },
    {
      title: "Sprint",
      dataIndex: "sprint_id",
      width: 160,
      render: (_value, item) => (
        <Select
          size="small"
          allowClear
          showSearch
          optionFilterProp="label"
          value={item.sprint_id || undefined}
          placeholder="待规划"
          aria-label={`${item.title} Sprint`}
          loading={savingTaskIds.has(item.id)}
          disabled={!canWrite(project) || savingTaskIds.has(item.id)}
          options={sprints.map((sprint) => ({
            value: sprint.id,
            label: sprint.name,
          }))}
          onChange={(value) => {
            const sprint = sprints.find((candidate) => candidate.id === value);
            void patchTask(item, {
              sprint_id: value || "",
              ...(sprint?.milestone_id
                ? { milestone_id: sprint.milestone_id }
                : {}),
            });
          }}
        />
      ),
    },
    {
      title: "关键路径",
      dataIndex: "critical_path",
      width: 100,
      render: (value) => (value ? <Tag color="red">关键</Tag> : "-"),
    },
    {
      title: "截止",
      dataIndex: "due_date",
      width: 150,
      render: (_value, item) => (
        <Input
          size="small"
          type="date"
          value={item.due_date || ""}
          aria-label={`${item.title} 截止日期`}
          disabled={!canWrite(project) || savingTaskIds.has(item.id)}
          status={item.status !== "done" && item.due_date && item.due_date < today() ? "error" : undefined}
          onChange={(event) => void patchTask(item, { due_date: event.target.value })}
        />
      ),
    },
    {
      title: "工时",
      width: 100,
      render: (_value, item) => `${item.spent_h || 0}/${item.estimate_h || 0}h`,
    },
    {
      title: "操作",
      valueType: "option",
      width: 130,
      fixed: "right",
      render: (_value, item) => (
        <Space>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => openTask(item)}
          >
            详情
          </Button>
          {canWrite(project) && (
            <Button
              type="link"
              danger
              size="small"
              onClick={() =>
                Modal.confirm({
                  title: "删除此任务？",
                  content: items.some((child) => child.parent_id === item.id)
                    ? `“${item.title}”的直接子任务会保留，并提升为根任务；其他任务中的前置依赖会自动清理。`
                    : `“${item.title}”将被删除；其他任务中的前置依赖会自动清理。`,
                  okButtonProps: { danger: true },
                  onOk: () => deleteTask(item),
                })
              }
            >
              删除
            </Button>
          )}
        </Space>
      ),
    },
  ];
  return (
    <div className="project-task-center">
      <div className="project-task-center-header">
        <div>
          <Typography.Title level={5}>
            {scope === "backlog" ? "Backlog" : "全部任务"}
          </Typography.Title>
          <Typography.Text type="secondary">
            {scope === "backlog"
              ? "这里只保留尚未进入 Sprint 的任务，用于细化、排序并安排到后续 Sprint。"
              : "跨里程碑、跨 Sprint 查询和批量维护项目任务；项目执行请使用当前 Sprint 看板。"}
          </Typography.Text>
        </div>
        <Tag color={scope === "backlog" ? "gold" : "default"}>
          {scopedItems.length} 项
        </Tag>
      </div>
      <div className="project-task-table">
          <Typography.Paragraph className="table-scroll-hint" type="secondary">
            表格可左右滑动查看计划、日期和工时等全部字段。
          </Typography.Paragraph>
          <ProTable<WorkItem>
        rowKey="id"
        columns={columns}
        dataSource={filtered}
        loading={loading}
        search={false}
        pagination={{
          pageSize: 15,
          showTotal: (total) => `共 ${total} 项`,
        }}
        scroll={{ x: 1600 }}
        locale={{
          emptyText: (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={
                scopedItems.length
                  ? "没有符合条件的任务"
                  : scope === "backlog"
                    ? "Backlog 已清空"
                    : "还没有任务"
              }
            >
              {scopedItems.length && hasTaskFilters ? (
                <Button onClick={clearTaskFilters}>清除筛选</Button>
              ) : canWrite(project) ? (
                <Button type="primary" onClick={() => openTask(null)}>
                  {scope === "backlog" ? "新建 Backlog 任务" : "新建第一个任务"}
                </Button>
              ) : null}
            </Empty>
          ),
        }}
        options={{ reload: () => void reload(), density: true, setting: true }}
        rowSelection={
          canWrite(project)
            ? {
                selectedRowKeys: selected,
                onChange: (keys) => setSelected(keys.map(String)),
              }
            : undefined
        }
        toolbar={{
          title: (
            <Space wrap className="project-task-filters">
              <Input.Search
                aria-label="搜索任务"
                allowClear
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="搜索任务"
              />
              <Select
                aria-label="状态筛选"
                allowClear
                value={status || undefined}
                placeholder="全部状态"
                onChange={(value) => setStatus(value || "")}
                options={[...STATUS_OPTIONS]}
              />
              <Select
                aria-label="负责人筛选"
                allowClear
                value={assignee || undefined}
                placeholder="全部负责人"
                onChange={(value) => setAssignee(value || "")}
                options={members.map((member) => ({
                  value: member.account_id,
                  label: member.name,
                }))}
              />
              <Select
                aria-label="优先级筛选"
                allowClear
                value={priority || undefined}
                placeholder="全部优先级"
                onChange={(value) => setPriority(value || "")}
                options={[
                  { value: "__none__", label: "无优先级" },
                  ...PRIORITY_OPTIONS.filter((item) => item.value),
                ]}
              />
              <Select
                aria-label="里程碑筛选"
                allowClear
                showSearch
                optionFilterProp="label"
                value={milestoneId || undefined}
                placeholder="全部里程碑"
                onChange={(value) => setMilestoneId(value || "")}
                options={milestones.map((milestone) => ({
                  value: milestone.id,
                  label: milestone.name,
                }))}
              />
              {scope === "all" && (
                <Select
                  aria-label="Sprint 筛选"
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  value={sprintId || undefined}
                  placeholder="全部 Sprint"
                  onChange={(value) => setSprintId(value || "")}
                  options={[
                    { value: "__unplanned__", label: "待规划" },
                    ...sprints.map((sprint) => ({
                      value: sprint.id,
                      label: sprint.name,
                    })),
                  ]}
                />
              )}
              <Tag>{filtered.length}/{scopedItems.length} 项</Tag>
              {hasTaskFilters && (
                <Button onClick={clearTaskFilters}>清除筛选</Button>
              )}
            </Space>
          ),
          actions: canWrite(project)
            ? [
                <Button
                  key="new"
                  type="primary"
                  icon={<PlusOutlined />}
                  onClick={() => openTask(null)}
                >
                  {scope === "backlog" ? "新建 Backlog 任务" : "新建任务"}
                </Button>,
              ]
            : [],
        }}
        tableAlertRender={({ selectedRowKeys }) =>
          `已选择 ${selectedRowKeys.length} 项`
        }
        tableAlertOptionRender={() => (
          <Space>
            <Select
              value={batchStatus}
              onChange={setBatchStatus}
              options={[...STATUS_OPTIONS]}
            />
            <Button
              type="link"
              onClick={() => void batchPatch({ status: batchStatus })}
            >
              批量更新
            </Button>
            <Button type="link" onClick={() => setSelected([])}>
              取消选择
            </Button>
          </Space>
        )}
          />
      </div>
    </div>
  );
}

export function ProjectIterations({
  sectionOnly,
}: {
  sectionOnly?: PlanningSettingsSection;
} = {}) {
  const {
    project,
    items,
    roots,
    milestones,
    customFields,
    sprints,
    selectedSprintId,
    setSelectedSprintId,
    reload,
    navigateToTab,
    openTask,
  } = useProjectWork();
  const { message, modal } = App.useApp();
  const [section, setSection] = useState<PlanningSettingsSection>(
    sectionOnly || "milestones",
  );
  const [fieldOpen, setFieldOpen] = useState(false);
  const [sprintOpen, setSprintOpen] = useState(false);
  const [editingField, setEditingField] = useState<ProjectCustomField | null>(
    null,
  );
  const [editingSprint, setEditingSprint] = useState<Sprint | null>(null);
  const [changingSprintId, setChangingSprintId] = useState("");
  const [burn, setBurn] = useState<{
    sprint: Sprint;
    total: number;
    points: BurndownPoint[];
  } | null>(null);
  const [fieldForm] =
    Form.useForm<
      Pick<ProjectCustomField, "name" | "field_type" | "options" | "required">
    >();
  const [sprintForm] = Form.useForm<SprintFormDraft>();
  const orderedSprints = useMemo(() => orderSprints(sprints), [sprints]);
  const activeSprint = orderedSprints.find(
    (sprint) => sprint.status === "active",
  );
  const suggestedSprint = orderedSprints.find(
    (sprint) => sprint.status === "planned",
  );
  const sprintStats = useMemo(
    () =>
      new Map(
        sprints.map((sprint) => {
          const tasks = items.filter((item) => item.sprint_id === sprint.id);
          const completed = tasks.filter((item) => item.status === "done").length;
          return [
            sprint.id,
            {
              tasks: tasks.length,
              completed,
              percent: tasks.length
                ? Math.round((completed / tasks.length) * 100)
                : 0,
              estimate: tasks.reduce(
                (sum, item) => sum + Number(item.estimate_h || 0),
                0,
              ),
              spent: tasks.reduce(
                (sum, item) => sum + Number(item.spent_h || 0),
                0,
              ),
            },
          ] as const;
        }),
      ),
    [items, sprints],
  );

  function openNewSprint(milestoneId = "") {
    setEditingSprint(null);
    sprintForm.resetFields();
    sprintForm.setFieldsValue({
      status: "planned",
      milestone_id: milestoneId,
      sync_task_milestone: false,
    });
    setSprintOpen(true);
  }

  function openNewField() {
    setEditingField(null);
    fieldForm.resetFields();
    fieldForm.setFieldsValue({
      field_type: "text",
      options: [],
      required: false,
    });
    setFieldOpen(true);
  }

  function openSprintEditor(sprint: Sprint) {
    setEditingSprint(sprint);
    sprintForm.setFieldsValue({
      ...sprint,
      sync_task_milestone: false,
    });
    setSprintOpen(true);
  }

  function startSprint(sprint: Sprint) {
    modal.confirm({
      title: `开始 Sprint“${sprint.name}”？`,
      content:
        activeSprint && activeSprint.id !== sprint.id
          ? `当前 Sprint“${activeSprint.name}”会自动结束；两个 Sprint 的任务归属均保持不变。`
          : "开始后，它会成为项目唯一的当前 Sprint，并出现在任务执行看板中。",
      okText: activeSprint ? "切换当前 Sprint" : "开始 Sprint",
      cancelText: "取消",
      onOk: async () => {
        setChangingSprintId(sprint.id);
        try {
          await consoleApi.updateSprint(project.id, sprint.id, {
            status: "active",
          });
          setSelectedSprintId(sprint.id);
          await reload();
          message.success(`已开始 ${sprint.name}`);
        } catch (reason) {
          message.error(errorText(reason, "Sprint 启动失败"));
          throw reason;
        } finally {
          setChangingSprintId("");
        }
      },
    });
  }

  function closeSprint(sprint: Sprint) {
    modal.confirm({
      title: `结束 Sprint“${sprint.name}”？`,
      content:
        "结束后任务和燃尽数据会保留，但该 Sprint 会变为只读历史；未完成任务不会自动移入 Backlog。",
      okText: "结束 Sprint",
      okButtonProps: { danger: true },
      cancelText: "继续执行",
      onOk: async () => {
        setChangingSprintId(sprint.id);
        try {
          await consoleApi.updateSprint(project.id, sprint.id, {
            status: "closed",
          });
          if (selectedSprintId === sprint.id) setSelectedSprintId("");
          await reload();
          message.success(`${sprint.name} 已结束`);
        } catch (reason) {
          message.error(errorText(reason, "Sprint 结束失败"));
          throw reason;
        } finally {
          setChangingSprintId("");
        }
      },
    });
  }

  function deletePlannedSprint(sprint: Sprint) {
    const taskCount = sprintStats.get(sprint.id)?.tasks || 0;
    modal.confirm({
      title: `删除 Sprint“${sprint.name}”？`,
      content: `${taskCount} 个任务会移回 Backlog，但不会被删除。`,
      okText: "删除 Sprint",
      okButtonProps: { danger: true },
      cancelText: "取消",
      onOk: async () => {
        try {
          await consoleApi.deleteSprint(project.id, sprint.id);
          if (selectedSprintId === sprint.id) setSelectedSprintId("");
          await reload();
          message.success("Sprint 已删除，关联任务已移回 Backlog");
        } catch (reason) {
          message.error(errorText(reason, "Sprint 删除失败"));
          throw reason;
        }
      },
    });
  }

  return (
    <div className="project-settings">
      <Tabs
        className={`project-settings-tabs${sectionOnly ? " is-single" : ""}`}
        activeKey={sectionOnly || section}
        onChange={(key) => setSection(key as PlanningSettingsSection)}
        more={{ trigger: "click" }}
        items={[
          {
            key: "milestones",
            label: (
              <Space size={6}>
                里程碑
                <Tag bordered={false}>{milestones.length}</Tag>
              </Space>
            ),
            children: (
              <MilestoneCard
                project={project}
                roots={roots}
                milestones={milestones}
                onCreateSprint={(milestone) => openNewSprint(milestone.id)}
              />
            ),
          },
          {
            key: "sprints",
            label: (
              <Space size={6}>
                Sprint
                <Tag bordered={false}>{sprints.length}</Tag>
              </Space>
            ),
            children: (
              <Card
                title="Sprint / 周期"
                className="project-settings-panel"
                extra={
                  <Space wrap>
                    <Button
                      icon={<DownloadOutlined />}
                      onClick={() =>
                        void consoleApi
                          .exportPmCsv(project.id)
                          .catch((reason) =>
                            message.error(errorText(reason, "导出失败")),
                          )
                      }
                    >
                      导出 CSV
                    </Button>
                    {canWrite(project) && (
                      <Button
                        type="primary"
                        icon={<PlusOutlined />}
                        onClick={() => openNewSprint()}
                      >
                        新建 Sprint
                      </Button>
                    )}
                  </Space>
                }
              >
                {activeSprint ? (
                  <Alert
                    className="project-sprint-current"
                    type="success"
                    showIcon
                    message={
                      <Space size={6} wrap>
                        <Typography.Text strong>当前 Sprint</Typography.Text>
                        <Tag color="processing">{activeSprint.name}</Tag>
                        <Typography.Text type="secondary">
                          {activeSprint.start_date} — {activeSprint.end_date}
                        </Typography.Text>
                      </Space>
                    }
                    description={
                      activeSprint.goal || "尚未设置目标，可编辑 Sprint 补充。"
                    }
                    action={
                      <Space wrap>
                        <Button onClick={() => navigateToTab("plan")}>
                          打开执行看板
                        </Button>
                        {canWrite(project) && (
                          <Button
                            danger
                            icon={<StopOutlined />}
                            loading={changingSprintId === activeSprint.id}
                            onClick={() => closeSprint(activeSprint)}
                          >
                            结束 Sprint
                          </Button>
                        )}
                      </Space>
                    }
                  />
                ) : (
                  <Alert
                    className="project-sprint-current"
                    type="warning"
                    showIcon
                    message="尚无当前 Sprint"
                    description="开始一个计划中的 Sprint 后，任务看板才会建立明确的执行范围。"
                    action={
                      suggestedSprint && canWrite(project) ? (
                        <Button
                          type="primary"
                          icon={<PlayCircleOutlined />}
                          loading={changingSprintId === suggestedSprint.id}
                          onClick={() => startSprint(suggestedSprint)}
                        >
                          开始 {suggestedSprint.name}
                        </Button>
                      ) : undefined
                    }
                  />
                )}
                <Table<Sprint>
                  rowKey="id"
                  dataSource={orderedSprints}
                  pagination={{
                    pageSize: 10,
                    hideOnSinglePage: true,
                  }}
                  scroll={{ x: 930 }}
                  locale={{
                    emptyText: (
                      <Empty
                        image={Empty.PRESENTED_IMAGE_SIMPLE}
                        description="还没有 Sprint"
                      />
                    ),
                  }}
                  rowClassName={(sprint) =>
                    `project-settings-row${
                      sprint.status === "active" ? " is-current" : ""
                    }${canWrite(project) ? " is-clickable" : ""}`
                  }
                  onRow={(sprint) => ({
                    onClick: (event) => {
                      if (
                        !canWrite(project) ||
                        (event.target as HTMLElement).closest("button")
                      )
                        return;
                      openSprintEditor(sprint);
                    },
                  })}
                  columns={[
                    {
                      title: "Sprint",
                      dataIndex: "name",
                      minWidth: 200,
                      render: (value, sprint) => (
                        <div>
                          <Space size={6} wrap>
                            <Typography.Text strong>
                              {String(value)}
                            </Typography.Text>
                            <Tag color={SPRINT_STATUS_META[sprint.status].color}>
                              {SPRINT_STATUS_META[sprint.status].label}
                            </Tag>
                          </Space>
                          <div>
                            <Typography.Text type="secondary" ellipsis>
                              {sprint.goal || "未设置目标"}
                            </Typography.Text>
                          </div>
                        </div>
                      ),
                    },
                    {
                      title: "执行",
                      width: 180,
                      render: (_value, sprint) => {
                        const stats = sprintStats.get(sprint.id);
                        return (
                          <div className="project-settings-progress">
                            <Space size={8}>
                              <Typography.Text>
                                {stats?.completed || 0}/{stats?.tasks || 0} 任务
                              </Typography.Text>
                              <Typography.Text type="secondary">
                                {stats?.spent || 0}/{stats?.estimate || 0}h
                              </Typography.Text>
                            </Space>
                            <Progress
                              size="small"
                              percent={stats?.percent || 0}
                              showInfo={false}
                            />
                          </div>
                        );
                      },
                    },
                    {
                      title: "周期",
                      width: 200,
                      render: (_value, sprint) =>
                        `${sprint.start_date} — ${sprint.end_date}`,
                    },
                    {
                      title: "里程碑",
                      dataIndex: "milestone_id",
                      width: 130,
                      render: (value) =>
                        milestones.find(
                          (milestone) => milestone.id === value,
                        )?.name || (
                          <Typography.Text type="secondary">
                            未关联
                          </Typography.Text>
                        ),
                    },
                    {
                      title: "操作",
                      width: 220,
                      fixed: "right",
                      render: (_value, sprint) => (
                        <Space size={4}>
                          {canWrite(project) && sprint.status === "planned" && (
                            <Button
                              type="link"
                              size="small"
                              icon={<PlayCircleOutlined />}
                              loading={changingSprintId === sprint.id}
                              onClick={() => startSprint(sprint)}
                            >
                              开始
                            </Button>
                          )}
                          {canWrite(project) && sprint.status === "active" && (
                            <Button
                              type="link"
                              danger
                              size="small"
                              icon={<StopOutlined />}
                              loading={changingSprintId === sprint.id}
                              onClick={() => closeSprint(sprint)}
                            >
                              结束
                            </Button>
                          )}
                          <Button
                            type="link"
                            size="small"
                            onClick={() => {
                              setSelectedSprintId(sprint.id);
                              navigateToTab("plan");
                            }}
                          >
                            查看任务
                          </Button>
                          <Dropdown
                            trigger={["click"]}
                            menu={{
                              items: [
                                ...(canWrite(project) &&
                                sprint.status !== "closed"
                                  ? [
                                      {
                                        key: "new-task",
                                        icon: <PlusOutlined />,
                                        label: "新建任务",
                                      },
                                    ]
                                  : []),
                                { key: "burndown", label: "查看燃尽" },
                                ...(canWrite(project)
                                  ? [
                                      {
                                        key: "edit",
                                        icon: <EditOutlined />,
                                        label: "编辑 Sprint",
                                      },
                                    ]
                                  : []),
                                ...(canWrite(project) &&
                                sprint.status === "planned"
                                  ? [
                                      {
                                        key: "delete",
                                        danger: true,
                                        icon: <DeleteOutlined />,
                                        label: "删除 Sprint",
                                      },
                                    ]
                                  : []),
                              ],
                              onClick: async ({ key, domEvent }) => {
                                domEvent.stopPropagation();
                                if (key === "new-task") {
                                  openTask(null, {
                                    sprint_id: sprint.id,
                                    milestone_id: sprint.milestone_id || "",
                                  });
                                } else if (key === "burndown") {
                                  try {
                                    const result =
                                      await consoleApi.sprintBurndown(
                                        project.id,
                                        sprint.id,
                                      );
                                    setBurn({ sprint, ...result });
                                  } catch (reason) {
                                    message.error(
                                      errorText(reason, "燃尽数据加载失败"),
                                    );
                                  }
                                } else if (key === "edit") {
                                  openSprintEditor(sprint);
                                } else if (key === "delete") {
                                  deletePlannedSprint(sprint);
                                }
                              },
                            }}
                          >
                            <Button
                              type="text"
                              size="small"
                              icon={<MoreOutlined />}
                              aria-label={`${sprint.name} 更多操作`}
                            />
                          </Dropdown>
                        </Space>
                      ),
                    },
                  ]}
                />
              </Card>
            ),
          },
          {
            key: "fields",
            label: (
              <Space size={6}>
                自定义字段
                <Tag bordered={false}>{customFields.length}</Tag>
              </Space>
            ),
            children: (
              <Card
                title="自定义字段"
                className="project-settings-panel"
                extra={
                  canWrite(project) && (
                    <Button
                      type="primary"
                      icon={<PlusOutlined />}
                      onClick={openNewField}
                    >
                      新建字段
                    </Button>
                  )
                }
              >
                <List
                  dataSource={customFields}
                  locale={{ emptyText: "暂无自定义字段" }}
                  renderItem={(field) => (
                    <List.Item
                      className={
                        canWrite(project)
                          ? "project-settings-row is-clickable"
                          : "project-settings-row"
                      }
                      onClick={(event) => {
                        if (
                          !canWrite(project) ||
                          (event.target as HTMLElement).closest("button")
                        )
                          return;
                        setEditingField(field);
                        fieldForm.setFieldsValue(field);
                        setFieldOpen(true);
                      }}
                      actions={
                        canWrite(project)
                          ? [
                              <Popconfirm
                                key="delete"
                                title={`删除字段“${field.name}”？`}
                                description="所有任务中的该字段值会一并移除。"
                                onConfirm={async () => {
                                  await consoleApi.deleteCustomField(
                                    project.id,
                                    field.id,
                                  );
                                  await reload();
                                }}
                              >
                                <Button
                                  type="text"
                                  danger
                                  icon={<DeleteOutlined />}
                                  aria-label={`删除字段 ${field.name}`}
                                />
                              </Popconfirm>,
                            ]
                          : []
                      }
                    >
                      <List.Item.Meta
                        title={
                          <Space>
                            <Typography.Text strong>
                              {field.name}
                            </Typography.Text>
                            <Tag>{field.field_type}</Tag>
                            {field.required && (
                              <Tag color="orange">必填</Tag>
                            )}
                          </Space>
                        }
                        description={
                          field.options.length
                            ? `选项：${field.options.join(" / ")}`
                            : "无预设选项"
                        }
                      />
                    </List.Item>
                  )}
                />
              </Card>
            ),
          },
        ].filter((item) => !sectionOnly || item.key === sectionOnly)}
      />
      <Modal
        title={editingField ? "编辑自定义字段" : "新增自定义字段"}
        open={fieldOpen}
        onCancel={() => setFieldOpen(false)}
        onOk={() => fieldForm.submit()}
        destroyOnHidden
      >
        <Form
          form={fieldForm}
          layout="vertical"
          onFinish={async (values) => {
            try {
              const fieldValues = {
                ...values,
                options:
                  values.field_type === "select" ? values.options || [] : [],
              };
              if (editingField)
                await consoleApi.updateCustomField(
                  project.id,
                  editingField.id,
                  fieldValues,
                );
              else
                await consoleApi.createCustomField(project.id, fieldValues);
              setFieldOpen(false);
              setEditingField(null);
              await reload();
            } catch (reason) {
              message.error(
                errorText(
                  reason,
                  editingField ? "字段更新失败" : "字段创建失败",
                ),
              );
            }
          }}
        >
          <Form.Item
            name="name"
            label="字段名称"
            rules={[{ required: true, whitespace: true }]}
          >
            <Input maxLength={80} />
          </Form.Item>
          <Form.Item name="field_type" label="类型">
            <Select
              options={[
                { value: "text", label: "文本" },
                { value: "number", label: "数字" },
                { value: "date", label: "日期" },
                { value: "select", label: "单选" },
                { value: "boolean", label: "是/否" },
              ]}
            />
          </Form.Item>
          <Form.Item
            noStyle
            shouldUpdate={(prev, next) => prev.field_type !== next.field_type}
          >
            {({ getFieldValue }) =>
              getFieldValue("field_type") === "select" && (
                <Form.Item
                  name="options"
                  label="选项"
                  rules={[
                    {
                      validator: (_rule, options) =>
                        Array.isArray(options) && options.length > 0
                          ? Promise.resolve()
                          : Promise.reject(new Error("请至少添加一个选项")),
                    },
                  ]}
                >
                  <CustomFieldOptionEditor />
                </Form.Item>
              )
            }
          </Form.Item>
          <Form.Item name="required" label="必填" valuePropName="checked">
            <Checkbox />
          </Form.Item>
        </Form>
      </Modal>
      <Modal
        title={editingSprint ? "编辑 Sprint" : "新建 Sprint"}
        open={sprintOpen}
        onCancel={() => setSprintOpen(false)}
        onOk={() => sprintForm.submit()}
        destroyOnHidden
      >
        <Form
          form={sprintForm}
          layout="vertical"
          onFinish={async (values) => {
            try {
              const syncTasks = values.sync_task_milestone;
              const sprintValues = {
                name: values.name,
                goal: values.goal,
                milestone_id: values.milestone_id,
                start_date: values.start_date,
                end_date: values.end_date,
              };
              const milestoneChanged =
                Boolean(editingSprint) &&
                editingSprint?.milestone_id !==
                  (sprintValues.milestone_id || "");
              if (editingSprint)
                await consoleApi.updateSprint(
                  project.id,
                  editingSprint.id,
                  sprintValues,
                );
              else
                await consoleApi.createSprint(project.id, {
                  ...sprintValues,
                  status: "planned",
                });
              let failedSyncs = 0;
              if (editingSprint && milestoneChanged && syncTasks) {
                const results = await Promise.allSettled(
                  items
                    .filter((item) => item.sprint_id === editingSprint.id)
                    .map((item) =>
                      consoleApi.updateWorkItem(project.id, item.id, {
                        milestone_id: sprintValues.milestone_id || "",
                      }),
                    ),
                );
                failedSyncs = results.filter(
                  (result) => result.status === "rejected",
                ).length;
              }
              setSprintOpen(false);
              setEditingSprint(null);
              await reload();
              if (failedSyncs)
                message.warning(
                  `Sprint 已保存，${failedSyncs} 个任务的里程碑同步失败`,
                );
              else
                message.success(
                  syncTasks && milestoneChanged
                    ? "Sprint 与任务里程碑已同步"
                    : editingSprint
                      ? "Sprint 已更新"
                      : "Sprint 已创建",
                );
            } catch (reason) {
              message.error(
                errorText(
                  reason,
                  editingSprint ? "Sprint 更新失败" : "Sprint 创建失败",
                ),
              );
            }
          }}
        >
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, whitespace: true }]}
          >
            <Input maxLength={120} />
          </Form.Item>
          <Form.Item name="milestone_id" label="所属里程碑">
            <Select
              allowClear
              placeholder="未关联里程碑"
              options={milestones.map((milestone) => ({
                value: milestone.id,
                label: milestone.name,
              }))}
            />
          </Form.Item>
          <Form.Item name="goal" label="目标">
            <Input.TextArea rows={3} maxLength={1000} />
          </Form.Item>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item
                name="start_date"
                label="开始日期"
                rules={[{ required: true }]}
              >
                <Input type="date" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="end_date"
                label="结束日期"
                dependencies={["start_date", "milestone_id"]}
                rules={[
                  { required: true },
                  ({ getFieldValue }) => ({
                    validator: async (_rule, value) => {
                      const startDate = getFieldValue("start_date");
                      if (!value || !startDate || value >= startDate) return;
                      throw new Error("结束日期不能早于开始日期");
                    },
                  }),
                  ({ getFieldValue }) => ({
                    warningOnly: true,
                    validator: async (_rule, value) => {
                      const milestone = milestones.find(
                        (item) =>
                          item.id === getFieldValue("milestone_id"),
                      );
                      if (
                        !value ||
                        !milestone?.due_date ||
                        value <= milestone.due_date
                      )
                        return;
                      throw new Error(
                        `结束日期晚于里程碑截止日期 ${milestone.due_date}`,
                      );
                    },
                  }),
                ]}
              >
                <Input type="date" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item label="状态">
            <Space size={8} wrap>
              <Tag
                color={
                  editingSprint
                    ? SPRINT_STATUS_META[editingSprint.status].color
                    : SPRINT_STATUS_META.planned.color
                }
              >
                {editingSprint
                  ? SPRINT_STATUS_META[editingSprint.status].label
                  : SPRINT_STATUS_META.planned.label}
              </Tag>
              <Typography.Text type="secondary">
                {editingSprint
                  ? "请在 Sprint 列表使用“开始”或“结束”变更生命周期。"
                  : "新 Sprint 会先保存为计划中，确认任务范围后再开始。"}
              </Typography.Text>
            </Space>
          </Form.Item>
          {editingSprint && (
            <Form.Item
              name="sync_task_milestone"
              valuePropName="checked"
              extra="仅在所属里程碑发生变化时生效；任务不会被删除或移出 Sprint。"
            >
              <Checkbox>同步更新当前 Sprint 中任务的里程碑</Checkbox>
            </Form.Item>
          )}
        </Form>
      </Modal>
      <Drawer
        width={680}
        open={Boolean(burn)}
        title={burn ? `${burn.sprint.name} · 燃尽` : "燃尽"}
        onClose={() => setBurn(null)}
        destroyOnHidden
      >
        {burn && (
          <>
            <Statistic title="初始工作量" value={burn.total} suffix="h" />
            <Table<BurndownPoint>
              rowKey="date"
              pagination={false}
              dataSource={burn.points}
              columns={[
                { title: "日期", dataIndex: "date" },
                {
                  title: "理想剩余",
                  dataIndex: "ideal_remaining",
                  render: (value) => `${value}h`,
                },
                {
                  title: "实际剩余",
                  dataIndex: "actual_remaining",
                  render: (value) => `${value}h`,
                },
              ]}
            />
          </>
        )}
      </Drawer>
    </div>
  );
}

interface WorkloadRow {
  key: string;
  name: string;
  tasks: number;
  doing: number;
  overdue: number;
  estimate: number;
  spent: number;
}

export function ProjectWorkload() {
  const { project, roots, members, loading, navigateToTab, openTask } =
    useProjectWork();
  const rows = useMemo<WorkloadRow[]>(() => {
    const people = [
      ...members.map((member) => ({
        key: member.account_id,
        name: member.name,
      })),
      { key: "unassigned", name: "未指派" },
    ];
    return people
      .map((person) => {
        const tasks = roots.filter((item) =>
          person.key === "unassigned"
            ? !item.assignee
            : item.assignee === person.key,
        );
        return {
          key: person.key,
          name: person.name,
          tasks: tasks.length,
          doing: tasks.filter((item) => item.status === "doing").length,
          overdue: tasks.filter(
            (item) =>
              item.due_date &&
              item.due_date < today() &&
              item.status !== "done",
          ).length,
          estimate: tasks.reduce(
            (sum, item) => sum + Number(item.estimate_h || 0),
            0,
          ),
          spent: tasks.reduce(
            (sum, item) => sum + Number(item.spent_h || 0),
            0,
          ),
        };
      })
      .filter((row) => row.tasks > 0 || row.key !== "unassigned");
  }, [roots, members]);
  return (
    <Card
      title="团队负载"
      extra={
        <Typography.Text type="secondary">
          按 Server 项目成员与真实工时聚合
        </Typography.Text>
      }
    >
      <Table<WorkloadRow>
        rowKey="key"
        loading={loading}
        dataSource={rows}
        pagination={false}
        scroll={{ x: 760 }}
        locale={{
          emptyText: (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="还没有可统计的任务负载"
            >
              <Space wrap>
                <Button onClick={() => navigateToTab("tasks")}>
                  查看任务列表
                </Button>
                {canWrite(project) && (
                  <Button type="primary" onClick={() => openTask(null)}>
                    新建任务
                  </Button>
                )}
              </Space>
            </Empty>
          ),
        }}
        columns={[
          {
            title: "成员",
            dataIndex: "name",
            width: 180,
            render: (name) => (
              <Space>
                <Avatar>{String(name).slice(0, 1)}</Avatar>
                <Typography.Text strong>{String(name)}</Typography.Text>
              </Space>
            ),
          },
          { title: "任务", dataIndex: "tasks", width: 90 },
          { title: "进行中", dataIndex: "doing", width: 90 },
          {
            title: "逾期",
            dataIndex: "overdue",
            width: 90,
            render: (value) => (
              <Typography.Text type={Number(value) ? "danger" : undefined}>
                {Number(value)}
              </Typography.Text>
            ),
          },
          {
            title: "工时",
            width: 150,
            render: (_value, row) => `${row.spent}/${row.estimate}h`,
          },
          {
            title: "投入进度",
            render: (_value, row) => (
              <Progress
                percent={
                  row.estimate
                    ? Math.min(
                        100,
                        Math.round((row.spent / row.estimate) * 100),
                      )
                    : 0
                }
                status={
                  row.estimate && row.spent > row.estimate
                    ? "exception"
                    : "active"
                }
                format={() =>
                  row.estimate
                    ? `${Math.round((row.spent / row.estimate) * 100)}%`
                    : "未估时"
                }
              />
            ),
          },
        ]}
      />
    </Card>
  );
}

interface GanttTask {
  task: WorkItem;
  start: Date;
  end: Date;
}

function dateUtc(value: string): Date {
  return new Date(`${value}T00:00:00Z`);
}

function daysBetween(from: Date, to: Date): number {
  return Math.round((to.getTime() - from.getTime()) / 86400000);
}

export function ProjectGantt() {
  const { project, roots, loading, navigateToTab, openTask } = useProjectWork();
  const dated = useMemo<GanttTask[]>(
    () =>
      roots
        .filter((task) => task.start_date || task.due_date)
        .map((task) => {
          const start = dateUtc(task.start_date || task.due_date);
          const end = dateUtc(task.due_date || task.start_date);
          return {
            task,
            start: start <= end ? start : end,
            end: end >= start ? end : start,
          };
        })
        .sort((a, b) => a.start.getTime() - b.start.getTime()),
    [roots],
  );
  if (loading) return <Card loading />;
  if (!dated.length)
    return (
      <Card>
        <Empty description="暂无带开始或截止日期的任务">
          <Space wrap>
            <Button onClick={() => navigateToTab("tasks")}>
              前往任务列表
            </Button>
            {canWrite(project) && !roots.length && (
              <Button type="primary" onClick={() => openTask(null)}>
                新建任务
              </Button>
            )}
          </Space>
        </Empty>
      </Card>
    );
  const min = new Date(Math.min(...dated.map((item) => item.start.getTime())));
  const max = new Date(Math.max(...dated.map((item) => item.end.getTime())));
  const span = Math.max(1, daysBetween(min, max) + 1);
  const middle = new Date(min.getTime() + Math.floor(span / 2) * 86400000);
  return (
    <Card
      title="甘特排期"
      extra={
        <Typography.Text type="secondary">
          {dateLabel(min)} — {dateLabel(max)}
        </Typography.Text>
      }
    >
      <div className="project-gantt-scroll">
        <div
          className="project-gantt"
          style={{ minWidth: Math.max(760, span * 18) }}
        >
          <div className="project-gantt-head project-gantt-name">任务</div>
          <div className="project-gantt-head project-gantt-axis">
            <span>{dateLabel(min)}</span>
            <span>{dateLabel(middle)}</span>
            <span>{dateLabel(max)}</span>
          </div>
          {dated.map(({ task, start, end }) => {
            const left = (daysBetween(min, start) / span) * 100;
            const width = Math.max(
              1.5,
              ((daysBetween(start, end) + 1) / span) * 100,
            );
            return (
              <div className="project-gantt-row" key={task.id}>
                <Button
                  type="link"
                  className="project-gantt-task"
                  onClick={() => openTask(task)}
                >
                  {task.title}
                </Button>
                <div className="project-gantt-track">
                  <button
                    type="button"
                    className={`project-gantt-bar is-${task.status}`}
                    style={{ left: `${left}%`, width: `${width}%` }}
                    onClick={() => openTask(task)}
                    title={`${task.title} · ${dateLabel(start)}—${dateLabel(end)}`}
                  >
                    <span>{width > 14 ? task.title : ""}</span>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </Card>
  );
}

function dateLabel(value: Date): string {
  return value.toISOString().slice(5, 10);
}

function today(): string {
  const value = new Date();
  const part = (number: number) => String(number).padStart(2, "0");
  return `${value.getFullYear()}-${part(value.getMonth() + 1)}-${part(value.getDate())}`;
}
