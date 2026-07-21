import {
  App, Avatar, Badge, Button, Card, Checkbox, Col, Drawer, Empty, Form, Input,
  InputNumber, Modal, Progress, Row, Select, Space, Statistic, Table, Tag, Timeline,
  Typography,
} from "antd";
import {
  CalendarOutlined, CheckCircleOutlined, ClockCircleOutlined, EditOutlined,
  DeleteOutlined, FlagOutlined, PlusOutlined, SaveOutlined, TeamOutlined,
} from "@ant-design/icons";
import { ProTable } from "@ant-design/pro-components";
import type { ProColumns } from "@ant-design/pro-components";
import {
  createContext, type ReactNode, useContext, useEffect, useMemo, useState,
} from "react";
import { consoleApi } from "../../api";
import type { Activity, Member, Milestone, Project, WorkItem } from "../../types";
import { CompatList as List } from "../CompatList";

const STATUS_OPTIONS = [
  { value: "todo", label: "待办" },
  { value: "doing", label: "进行中" },
  { value: "paused", label: "暂停" },
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
  low: "default", medium: "blue", high: "orange", urgent: "red",
};
const STATUS_META: Record<WorkItem["status"], { label: string; color: string }> = {
  todo: { label: "待办", color: "default" },
  doing: { label: "进行中", color: "processing" },
  paused: { label: "暂停", color: "warning" },
  done: { label: "完成", color: "success" },
};

type TaskDraft = Partial<WorkItem> & { title: string };
interface TaskTemplate { id: string; name: string; fields: Partial<WorkItem> }

function storageJson<T>(key: string, fallback: T): T {
  try { return JSON.parse(localStorage.getItem(key) || "") as T; } catch { return fallback; }
}

interface ProjectWorkContextValue {
  project: Project;
  items: WorkItem[];
  roots: WorkItem[];
  members: Member[];
  milestones: Milestone[];
  activity: Activity[];
  loading: boolean;
  selected: string[];
  setSelected: (ids: string[]) => void;
  reload: () => Promise<void>;
  openTask: (task: WorkItem | null) => void;
  patchTask: (task: WorkItem, patch: Partial<WorkItem>) => Promise<void>;
  deleteTask: (task: WorkItem) => Promise<void>;
  batchPatch: (patch: Partial<WorkItem>) => Promise<void>;
  templates: TaskTemplate[];
  openTemplate: (templateId: string) => void;
  deleteTemplate: (templateId: string) => void;
}

const ProjectWorkContext = createContext<ProjectWorkContextValue | null>(null);

function errorText(reason: unknown, fallback: string): string {
  return reason instanceof Error ? reason.message : fallback;
}

function canWrite(project: Project): boolean {
  return project.role !== "Viewer";
}

function useProjectWork(): ProjectWorkContextValue {
  const value = useContext(ProjectWorkContext);
  if (!value) throw new Error("Project workspace must be used inside ProjectWorkProvider");
  return value;
}

export function ProjectWorkProvider({ project, children }: { project: Project; children: ReactNode }) {
  const { message } = App.useApp();
  const [items, setItems] = useState<WorkItem[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string[]>([]);
  const [editing, setEditing] = useState<WorkItem | null | undefined>(undefined);
  const [templateOpen, setTemplateOpen] = useState(false);
  const [templateRevision, setTemplateRevision] = useState(0);
  const [form] = Form.useForm<TaskDraft>();
  const [templateForm] = Form.useForm<{ name: string }>();
  const templateKey = `agentmate.console.pm.templates.${project.id}`;
  const templates = useMemo(() => storageJson<TaskTemplate[]>(templateKey, []), [templateKey, templateRevision]);

  async function reload() {
    setLoading(true);
    try {
      const [work, memberResult, milestoneResult, activityResult] = await Promise.all([
        consoleApi.workItems(project.id),
        consoleApi.projectMembers(project.id),
        consoleApi.milestones(project.id),
        consoleApi.activity(project.id),
      ]);
      setItems(work.items || []);
      setMembers(memberResult.members || []);
      setMilestones(milestoneResult.milestones || []);
      setActivity(activityResult.activity || []);
      setSelected((current) => current.filter((id) => work.items.some((item) => item.id === id)));
    } catch (reason) {
      message.error(errorText(reason, "项目工作台加载失败"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void reload(); }, [project.id]);

  function openTask(task: WorkItem | null) {
    setEditing(task);
    form.resetFields();
    form.setFieldsValue(task || {
      title: "", description: "", status: "todo", priority: "", source: "console",
      assignee: "", milestone_id: "", start_date: "", due_date: "", estimate_h: 0,
      spent_h: 0, labels: [], parent_id: "",
    });
  }

  function openTemplate(templateId: string) {
    const template = templates.find((item) => item.id === templateId);
    if (!template) return;
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      title: "", description: "", status: "todo", priority: "", source: "console",
      assignee: "", milestone_id: "", start_date: "", due_date: "", estimate_h: 0,
      spent_h: 0, labels: [], parent_id: "", ...template.fields,
    });
  }

  function saveTemplate({ name }: { name: string }) {
    const fields: Partial<WorkItem> & { title?: string } = { ...form.getFieldsValue() };
    delete fields.title;
    const template: TaskTemplate = {
      id: globalThis.crypto?.randomUUID?.() || `template-${Date.now()}`,
      name: name.trim().slice(0, 40),
      fields,
    };
    localStorage.setItem(templateKey, JSON.stringify([...templates, template]));
    setTemplateRevision((value) => value + 1);
    setTemplateOpen(false);
    templateForm.resetFields();
    message.success("任务模板已保存");
  }

  function deleteTemplate(templateId: string) {
    localStorage.setItem(templateKey, JSON.stringify(templates.filter((item) => item.id !== templateId)));
    setTemplateRevision((value) => value + 1);
    message.success("任务模板已删除");
  }

  async function patchTask(task: WorkItem, patch: Partial<WorkItem>) {
    try {
      await consoleApi.updateWorkItem(project.id, task.id, patch);
      await reload();
    } catch (reason) {
      message.error(errorText(reason, "任务更新失败"));
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
    try {
      await Promise.all(selected.map((id) => consoleApi.updateWorkItem(project.id, id, patch)));
      message.success(`已更新 ${selected.length} 个任务`);
      setSelected([]);
      await reload();
    } catch (reason) {
      message.error(errorText(reason, "批量更新失败"));
    }
  }

  async function saveTask(values: TaskDraft) {
    try {
      const body: TaskDraft = {
        ...values,
        labels: Array.isArray(values.labels) ? values.labels : [],
        assignee: values.assignee || "",
        milestone_id: values.milestone_id || "",
      };
      if (editing) await consoleApi.updateWorkItem(project.id, editing.id, body);
      else await consoleApi.createWorkItem(project.id, body);
      message.success(editing ? "任务已保存" : "任务已创建");
      setEditing(undefined);
      await reload();
    } catch (reason) {
      message.error(errorText(reason, "任务保存失败"));
    }
  }

  const roots = useMemo(() => items.filter((item) => !item.parent_id), [items]);
  const value = useMemo<ProjectWorkContextValue>(() => ({
    project, items, roots, members, milestones, activity, loading, selected, setSelected,
    reload, openTask, patchTask, deleteTask, batchPatch, templates, openTemplate, deleteTemplate,
  }), [project, items, roots, members, milestones, activity, loading, selected, templates]);

  return <ProjectWorkContext.Provider value={value}>
    {children}
    <Drawer
      width={640}
      open={editing !== undefined}
      title={editing ? `任务 · ${editing.title}` : "新建任务"}
      onClose={() => setEditing(undefined)}
      destroyOnHidden
      extra={canWrite(project) && <Space>
        {editing && <Button icon={<SaveOutlined />} onClick={() => setTemplateOpen(true)}>存为模板</Button>}
        <Button type="primary" onClick={() => form.submit()}>保存</Button>
      </Space>}
    >
      <Form form={form} layout="vertical" disabled={!canWrite(project)} onFinish={saveTask}>
        <Form.Item name="title" label="标题" rules={[{ required: true, whitespace: true }]}>
          <Input maxLength={300} />
        </Form.Item>
        <Form.Item name="description" label="描述"><Input.TextArea rows={5} /></Form.Item>
        <Row gutter={12}>
          <Col xs={24} sm={12}><Form.Item name="status" label="状态"><Select options={[...STATUS_OPTIONS]} /></Form.Item></Col>
          <Col xs={24} sm={12}><Form.Item name="priority" label="优先级"><Select options={[...PRIORITY_OPTIONS]} /></Form.Item></Col>
        </Row>
        <Row gutter={12}>
          <Col xs={24} sm={12}><Form.Item name="assignee" label="负责人"><Select allowClear options={members.map((member) => ({ value: member.account_id, label: member.name }))} /></Form.Item></Col>
          <Col xs={24} sm={12}><Form.Item name="milestone_id" label="里程碑"><Select allowClear options={milestones.map((milestone) => ({ value: milestone.id, label: milestone.name }))} /></Form.Item></Col>
        </Row>
        <Row gutter={12}>
          <Col xs={24} sm={12}><Form.Item name="start_date" label="开始日期"><Input type="date" /></Form.Item></Col>
          <Col xs={24} sm={12}><Form.Item name="due_date" label="截止日期"><Input type="date" /></Form.Item></Col>
        </Row>
        <Row gutter={12}>
          <Col xs={24} sm={12}><Form.Item name="estimate_h" label="预估工时"><InputNumber min={0} className="full-width" addonAfter="h" /></Form.Item></Col>
          <Col xs={24} sm={12}><Form.Item name="spent_h" label="投入工时"><InputNumber min={0} className="full-width" addonAfter="h" /></Form.Item></Col>
        </Row>
        <Form.Item name="source" label="来源"><Input maxLength={80} /></Form.Item>
        <Form.Item name="labels" label="标签"><Select mode="tags" tokenSeparators={[","]} /></Form.Item>
      </Form>
    </Drawer>
    <Modal title="存为任务模板" open={templateOpen} onCancel={() => setTemplateOpen(false)} onOk={() => templateForm.submit()} destroyOnHidden>
      <Form form={templateForm} layout="vertical" onFinish={saveTemplate}>
        <Form.Item name="name" label="模板名称" rules={[{ required: true, whitespace: true }]}><Input maxLength={40} /></Form.Item>
      </Form>
    </Modal>
  </ProjectWorkContext.Provider>;
}

export function ProjectOverview() {
  const { project, roots, milestones, activity, loading } = useProjectWork();
  const done = roots.filter((item) => item.status === "done").length;
  const doing = roots.filter((item) => item.status === "doing").length;
  const overdue = roots.filter((item) => item.due_date && item.due_date < today() && item.status !== "done").length;
  const percent = roots.length ? Math.round(done / roots.length * 100) : 0;
  return <div className="tab-stack">
    <Row gutter={[16, 16]}>
      <Col xs={12} xl={6}><Card loading={loading}><Statistic title="任务总数" value={roots.length} prefix={<FlagOutlined />} /></Card></Col>
      <Col xs={12} xl={6}><Card loading={loading}><Statistic title="进行中" value={doing} prefix={<ClockCircleOutlined />} /></Card></Col>
      <Col xs={12} xl={6}><Card loading={loading}><Statistic title="已完成" value={done} prefix={<CheckCircleOutlined />} /></Card></Col>
      <Col xs={12} xl={6}><Card loading={loading}><Statistic title="已逾期" value={overdue} prefix={<CalendarOutlined />} /></Card></Col>
    </Row>
    <Card title="整体进度" extra={<Typography.Text type="secondary">{done}/{roots.length}</Typography.Text>}>
      <Progress percent={percent} status={percent === 100 ? "success" : "active"} />
    </Card>
    <Row gutter={[16, 16]}>
      <Col xs={24} xl={12}><MilestoneCard project={project} roots={roots} milestones={milestones} /></Col>
      <Col xs={24} xl={12}>
        <Card title="近期活动" className="project-overview-card">
          {activity.length ? <Timeline items={activity.slice(0, 12).map((item) => ({
            children: <><Typography.Text strong>{item.actor || "系统"}</Typography.Text> {item.detail || item.kind}<div><Typography.Text type="secondary">{item.created_at ? new Date(item.created_at * 1000).toLocaleString() : ""}</Typography.Text></div></>,
          }))} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无任务活动" />}
        </Card>
      </Col>
    </Row>
  </div>;
}

function MilestoneCard({ project, roots, milestones }: { project: Project; roots: WorkItem[]; milestones: Milestone[] }) {
  const { message } = App.useApp();
  const { reload } = useProjectWork();
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm<{ name: string; due_date: string }>();
  return <Card title="里程碑" className="project-overview-card" extra={canWrite(project) && <Button type="link" icon={<PlusOutlined />} onClick={() => setOpen(true)}>新增</Button>}>
    {milestones.length ? <List dataSource={milestones} renderItem={(milestone) => {
      const related = roots.filter((item) => item.milestone_id === milestone.id);
      const completed = related.filter((item) => item.status === "done").length;
      return <List.Item><List.Item.Meta title={<Space>{milestone.name}{milestone.status === "closed" && <Tag color="green">已关闭</Tag>}</Space>} description={<><Progress size="small" percent={related.length ? Math.round(completed / related.length * 100) : 0} /><Typography.Text type="secondary">{milestone.due_date ? `截止 ${milestone.due_date}` : "未设截止日期"}</Typography.Text></>} /></List.Item>;
    }} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有里程碑" />}
    <Modal title="新增里程碑" open={open} onCancel={() => setOpen(false)} onOk={() => form.submit()} destroyOnHidden>
      <Form form={form} layout="vertical" onFinish={async (values) => {
        try {
          await consoleApi.createMilestone(project.id, values);
          message.success("里程碑已创建");
          setOpen(false);
          form.resetFields();
          await reload();
        } catch (reason) { message.error(errorText(reason, "创建失败")); }
      }}>
        <Form.Item name="name" label="名称" rules={[{ required: true, whitespace: true }]}><Input /></Form.Item>
        <Form.Item name="due_date" label="截止日期"><Input type="date" /></Form.Item>
      </Form>
    </Modal>
  </Card>;
}

type GroupMode = "none" | "assignee" | "milestone";
interface SavedPlanView { name: string; group: GroupMode; assignee: string; source: string; search: string }

export function ProjectPlan() {
  const {
    project, roots, members, milestones, loading, selected, setSelected, openTask,
    patchTask, batchPatch, templates, openTemplate, deleteTemplate,
  } = useProjectWork();
  const [group, setGroup] = useState<GroupMode>("none");
  const [assignee, setAssignee] = useState("");
  const [source, setSource] = useState("");
  const [search, setSearch] = useState("");
  const [batchStatus, setBatchStatus] = useState<WorkItem["status"]>("doing");
  const [wipOpen, setWipOpen] = useState(false);
  const [viewOpen, setViewOpen] = useState(false);
  const [templateId, setTemplateId] = useState("");
  const [revision, setRevision] = useState(0);
  const [viewForm] = Form.useForm<{ name: string }>();
  const wipKey = `agentmate.console.pm.wip.${project.id}`;
  const viewKey = `agentmate.console.pm.views.${project.id}`;
  const wip = useMemo(() => storageJson<Partial<Record<WorkItem["status"], number>>>(wipKey, {}), [wipKey, revision]);
  const savedViews = useMemo(() => storageJson<SavedPlanView[]>(viewKey, []), [viewKey, revision]);
  const sources = useMemo(() => [...new Set(roots.map((item) => item.source).filter(Boolean))], [roots]);
  const filtered = useMemo(() => roots.filter((item) => {
    if (assignee && item.assignee !== assignee) return false;
    if (source && item.source !== source) return false;
    if (search && !`${item.title} ${item.description || ""} ${(item.labels || []).join(" ")}`.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  }), [roots, assignee, source, search]);
  const lanes = useMemo(() => makeLanes(filtered, group, members, milestones), [filtered, group, members, milestones]);

  function toggleSelected(id: string, checked: boolean) {
    setSelected(checked ? [...new Set([...selected, id])] : selected.filter((value) => value !== id));
  }

  function saveWip(values: Record<string, number | null>) {
    const next: Partial<Record<WorkItem["status"], number>> = {};
    for (const option of STATUS_OPTIONS) {
      const value = values[option.value];
      if (typeof value === "number" && value > 0) next[option.value] = value;
    }
    localStorage.setItem(wipKey, JSON.stringify(next));
    setRevision((value) => value + 1);
    setWipOpen(false);
  }

  function applyView(name: string) {
    const view = savedViews.find((item) => item.name === name);
    if (!view) return;
    setGroup(view.group); setAssignee(view.assignee); setSource(view.source); setSearch(view.search);
  }

  if (loading) return <Card loading />;
  return <div className="project-plan">
    <Card className="project-plan-toolbar" styles={{ body: { padding: 12 } }}>
      <div className="project-plan-toolbar-row">
        <Space wrap>
          {canWrite(project) && <Button type="primary" icon={<PlusOutlined />} onClick={() => openTask(null)}>新建任务</Button>}
          {canWrite(project) && <Select aria-label="任务模板" value={templateId || undefined} placeholder="选择任务模板" onChange={setTemplateId} options={templates.map((template) => ({ value: template.id, label: template.name }))} />}
          {canWrite(project) && <Button disabled={!templateId} onClick={() => openTemplate(templateId)}>使用模板</Button>}
          {canWrite(project) && <Button aria-label="删除任务模板" danger icon={<DeleteOutlined />} disabled={!templateId} onClick={() => { deleteTemplate(templateId); setTemplateId(""); }} />}
          <Select aria-label="泳道分组" value={group} onChange={setGroup} options={[{ value: "none", label: "不分组" }, { value: "assignee", label: "按负责人泳道" }, { value: "milestone", label: "按里程碑泳道" }]} />
          <Select aria-label="负责人筛选" allowClear value={assignee || undefined} placeholder="全部负责人" onChange={(value) => setAssignee(value || "")} options={members.map((member) => ({ value: member.account_id, label: member.name }))} />
          <Select aria-label="来源筛选" allowClear value={source || undefined} placeholder="全部来源" onChange={(value) => setSource(value || "")} options={sources.map((value) => ({ value, label: value }))} />
          <Input.Search aria-label="搜索任务" allowClear value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索任务" />
        </Space>
        <Space wrap>
          <Select aria-label="保存的视图" allowClear placeholder="保存的视图" onChange={applyView} options={savedViews.map((view) => ({ value: view.name, label: view.name }))} />
          <Button icon={<SaveOutlined />} onClick={() => setViewOpen(true)}>保存视图</Button>
          <Button onClick={() => setWipOpen(true)}>WIP 上限</Button>
        </Space>
      </div>
      {selected.length > 0 && canWrite(project) && <div className="project-batch-bar">
        <Typography.Text strong>已选择 {selected.length} 项</Typography.Text>
        <Select value={batchStatus} onChange={setBatchStatus} options={[...STATUS_OPTIONS]} />
        <Button type="primary" onClick={() => void batchPatch({ status: batchStatus })}>批量更新状态</Button>
        <Button onClick={() => setSelected([])}>取消选择</Button>
      </div>}
    </Card>

    {filtered.length ? lanes.map((lane) => <section className="project-lane" key={lane.key}>
      {group !== "none" && <div className="project-lane-heading"><Space><TeamOutlined /><Typography.Text strong>{lane.label}</Typography.Text><Tag>{lane.items.length}</Tag></Space></div>}
      <div className="project-kanban">
        {STATUS_OPTIONS.map((status) => {
          const cards = lane.items.filter((item) => item.status === status.value);
          const limit = wip[status.value];
          const over = Boolean(limit && cards.length > limit);
          return <div
            className={`project-kanban-column${over ? " is-over-wip" : ""}`}
            key={status.value}
            onDragOver={(event) => { if (canWrite(project)) event.preventDefault(); }}
            onDrop={(event) => {
              if (!canWrite(project)) return;
              const id = event.dataTransfer.getData("text/plain");
              const task = roots.find((item) => item.id === id);
              if (task && task.status !== status.value) void patchTask(task, { status: status.value });
            }}
          >
            <div className="project-kanban-column-head">
              <Space><Badge status={STATUS_META[status.value].color as "default" | "processing" | "warning" | "success"} /><Typography.Text strong>{status.label}</Typography.Text></Space>
              <Typography.Text type={over ? "danger" : "secondary"}>{cards.length}{limit ? `/${limit}` : ""}</Typography.Text>
            </div>
            <div className="project-kanban-cards">
              {cards.map((task) => <Card
                key={task.id}
                size="small"
                className="project-task-card"
                draggable={canWrite(project)}
                onDragStart={(event) => event.dataTransfer.setData("text/plain", task.id)}
                onClick={() => openTask(task)}
              >
                <div className="project-task-card-title">
                  {canWrite(project) && <Checkbox checked={selected.includes(task.id)} onClick={(event) => event.stopPropagation()} onChange={(event) => toggleSelected(task.id, event.target.checked)} />}
                  <Typography.Text strong ellipsis={{ tooltip: task.title }}>{task.title}</Typography.Text>
                </div>
                {task.description && <Typography.Paragraph type="secondary" ellipsis={{ rows: 2 }}>{task.description}</Typography.Paragraph>}
                <div className="project-task-card-meta">
                  <Space size={[4, 4]} wrap>
                    {task.priority && <Tag color={PRIORITY_COLORS[task.priority]}>{PRIORITY_OPTIONS.find((item) => item.value === task.priority)?.label}</Tag>}
                    {task.assignee_name && <Tag icon={<Avatar size={16}>{task.assignee_name.slice(0, 1)}</Avatar>}>{task.assignee_name}</Tag>}
                    {task.due_date && <Tag icon={<CalendarOutlined />}>{task.due_date}</Tag>}
                  </Space>
                  {canWrite(project) && <Select size="small" value={task.status} onClick={(event) => event.stopPropagation()} onChange={(value) => void patchTask(task, { status: value })} options={[...STATUS_OPTIONS]} />}
                </div>
              </Card>)}
              {!cards.length && <div className="project-kanban-empty">暂无任务</div>}
            </div>
          </div>;
        })}
      </div>
    </section>) : <Card><Empty description="没有符合条件的任务" /></Card>}

    <Modal title="设置 WIP 上限" open={wipOpen} onCancel={() => setWipOpen(false)} footer={null} destroyOnHidden>
      <Form layout="vertical" initialValues={wip} onFinish={saveWip}>
        <Row gutter={12}>{STATUS_OPTIONS.map((status) => <Col span={12} key={status.value}><Form.Item name={status.value} label={status.label}><InputNumber min={1} placeholder="不限" className="full-width" /></Form.Item></Col>)}</Row>
        <Button type="primary" htmlType="submit">保存</Button>
      </Form>
    </Modal>
    <Modal title="保存当前视图" open={viewOpen} onCancel={() => setViewOpen(false)} onOk={() => viewForm.submit()} destroyOnHidden>
      <Form form={viewForm} layout="vertical" onFinish={({ name }) => {
        const next = [...savedViews.filter((item) => item.name !== name), { name, group, assignee, source, search }];
        localStorage.setItem(viewKey, JSON.stringify(next));
        setRevision((value) => value + 1);
        setViewOpen(false);
        viewForm.resetFields();
      }}><Form.Item name="name" label="视图名称" rules={[{ required: true, whitespace: true }]}><Input maxLength={40} /></Form.Item></Form>
    </Modal>
  </div>;
}

function makeLanes(items: WorkItem[], group: GroupMode, members: Member[], milestones: Milestone[]) {
  if (group === "none") return [{ key: "all", label: "全部任务", items }];
  const groups = new Map<string, { key: string; label: string; items: WorkItem[] }>();
  for (const item of items) {
    const key = group === "assignee" ? item.assignee || "unassigned" : item.milestone_id || "no-milestone";
    const label = group === "assignee"
      ? members.find((member) => member.account_id === item.assignee)?.name || item.assignee_name || "未指派"
      : milestones.find((milestone) => milestone.id === item.milestone_id)?.name || "无里程碑";
    const current = groups.get(key) || { key, label, items: [] };
    current.items.push(item);
    groups.set(key, current);
  }
  return [...groups.values()];
}

export function ProjectTasks() {
  const { project, roots, members, milestones, loading, selected, setSelected, reload, openTask, patchTask, deleteTask, batchPatch } = useProjectWork();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [assignee, setAssignee] = useState("");
  const [batchStatus, setBatchStatus] = useState<WorkItem["status"]>("doing");
  const filtered = roots.filter((item) => (!search || `${item.title} ${item.description || ""}`.toLowerCase().includes(search.toLowerCase())) && (!status || item.status === status) && (!assignee || item.assignee === assignee));
  const milestoneName = (id: string) => milestones.find((milestone) => milestone.id === id)?.name || "-";
  const columns: ProColumns<WorkItem>[] = [
    { title: "任务", dataIndex: "title", width: 300, render: (_value, item) => <Button type="link" className="project-task-link" onClick={() => openTask(item)}><span><Typography.Text strong>{item.title}</Typography.Text>{item.description && <Typography.Text type="secondary" ellipsis>{item.description}</Typography.Text>}</span></Button> },
    { title: "状态", dataIndex: "status", width: 130, render: (_value, item) => <Select size="small" value={item.status} disabled={!canWrite(project)} options={[...STATUS_OPTIONS]} onChange={(value) => void patchTask(item, { status: value })} /> },
    { title: "优先级", dataIndex: "priority", width: 100, render: (value) => value ? <Tag color={PRIORITY_COLORS[String(value)]}>{PRIORITY_OPTIONS.find((option) => option.value === value)?.label}</Tag> : "-" },
    { title: "负责人", dataIndex: "assignee_name", width: 130, render: (value) => value || "未指派" },
    { title: "里程碑", dataIndex: "milestone_id", width: 150, render: (value) => milestoneName(String(value || "")) },
    { title: "截止", dataIndex: "due_date", width: 120, render: (value, item) => <Typography.Text type={item.status !== "done" && value && String(value) < today() ? "danger" : undefined}>{String(value || "-")}</Typography.Text> },
    { title: "工时", width: 100, render: (_value, item) => `${item.spent_h || 0}/${item.estimate_h || 0}h` },
    { title: "操作", valueType: "option", width: 130, render: (_value, item) => <Space><Button type="link" size="small" icon={<EditOutlined />} onClick={() => openTask(item)}>详情</Button>{canWrite(project) && <Button type="link" danger size="small" onClick={() => Modal.confirm({ title: "删除此任务？", content: item.title, okButtonProps: { danger: true }, onOk: () => deleteTask(item) })}>删除</Button>}</Space> },
  ];
  return <div className="project-task-table">
    <ProTable<WorkItem>
      rowKey="id"
      columns={columns}
      dataSource={filtered}
      loading={loading}
      search={false}
      pagination={{ pageSize: 15 }}
      scroll={{ x: 1120 }}
      options={{ reload: () => void reload(), density: true, setting: true }}
      rowSelection={canWrite(project) ? { selectedRowKeys: selected, onChange: (keys) => setSelected(keys.map(String)) } : undefined}
      toolbar={{
        title: <Space wrap><Input.Search allowClear value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索任务" /><Select allowClear value={status || undefined} placeholder="全部状态" onChange={(value) => setStatus(value || "")} options={[...STATUS_OPTIONS]} /><Select allowClear value={assignee || undefined} placeholder="全部负责人" onChange={(value) => setAssignee(value || "")} options={members.map((member) => ({ value: member.account_id, label: member.name }))} /></Space>,
        actions: canWrite(project) ? [<Button key="new" type="primary" icon={<PlusOutlined />} onClick={() => openTask(null)}>新建任务</Button>] : [],
      }}
      tableAlertRender={({ selectedRowKeys }) => `已选择 ${selectedRowKeys.length} 项`}
      tableAlertOptionRender={() => <Space><Select value={batchStatus} onChange={setBatchStatus} options={[...STATUS_OPTIONS]} /><Button type="link" onClick={() => void batchPatch({ status: batchStatus })}>批量更新</Button><Button type="link" onClick={() => setSelected([])}>取消选择</Button></Space>}
    />
  </div>;
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
  const { roots, members, loading } = useProjectWork();
  const rows = useMemo<WorkloadRow[]>(() => {
    const people = [...members.map((member) => ({ key: member.account_id, name: member.name })), { key: "unassigned", name: "未指派" }];
    return people.map((person) => {
      const tasks = roots.filter((item) => (person.key === "unassigned" ? !item.assignee : item.assignee === person.key));
      return {
        key: person.key, name: person.name, tasks: tasks.length,
        doing: tasks.filter((item) => item.status === "doing").length,
        overdue: tasks.filter((item) => item.due_date && item.due_date < today() && item.status !== "done").length,
        estimate: tasks.reduce((sum, item) => sum + Number(item.estimate_h || 0), 0),
        spent: tasks.reduce((sum, item) => sum + Number(item.spent_h || 0), 0),
      };
    }).filter((row) => row.tasks > 0 || row.key !== "unassigned");
  }, [roots, members]);
  return <Card title="团队负载" extra={<Typography.Text type="secondary">按 Server 项目成员与真实工时聚合</Typography.Text>}>
    <Table<WorkloadRow> rowKey="key" loading={loading} dataSource={rows} pagination={false} scroll={{ x: 760 }} columns={[
      { title: "成员", dataIndex: "name", width: 180, render: (name) => <Space><Avatar>{String(name).slice(0, 1)}</Avatar><Typography.Text strong>{String(name)}</Typography.Text></Space> },
      { title: "任务", dataIndex: "tasks", width: 90 },
      { title: "进行中", dataIndex: "doing", width: 90 },
      { title: "逾期", dataIndex: "overdue", width: 90, render: (value) => <Typography.Text type={Number(value) ? "danger" : undefined}>{Number(value)}</Typography.Text> },
      { title: "工时", width: 150, render: (_value, row) => `${row.spent}/${row.estimate}h` },
      { title: "投入进度", render: (_value, row) => <Progress percent={row.estimate ? Math.min(100, Math.round(row.spent / row.estimate * 100)) : 0} status={row.estimate && row.spent > row.estimate ? "exception" : "active"} format={() => row.estimate ? `${Math.round(row.spent / row.estimate * 100)}%` : "未估时"} /> },
    ]} />
  </Card>;
}

interface GanttTask { task: WorkItem; start: Date; end: Date }

function dateUtc(value: string): Date {
  return new Date(`${value}T00:00:00Z`);
}

function daysBetween(from: Date, to: Date): number {
  return Math.round((to.getTime() - from.getTime()) / 86400000);
}

export function ProjectGantt() {
  const { roots, loading, openTask } = useProjectWork();
  const dated = useMemo<GanttTask[]>(() => roots.filter((task) => task.start_date || task.due_date).map((task) => {
    const start = dateUtc(task.start_date || task.due_date);
    const end = dateUtc(task.due_date || task.start_date);
    return { task, start: start <= end ? start : end, end: end >= start ? end : start };
  }).sort((a, b) => a.start.getTime() - b.start.getTime()), [roots]);
  if (loading) return <Card loading />;
  if (!dated.length) return <Card><Empty description="暂无带开始或截止日期的任务" /></Card>;
  const min = new Date(Math.min(...dated.map((item) => item.start.getTime())));
  const max = new Date(Math.max(...dated.map((item) => item.end.getTime())));
  const span = Math.max(1, daysBetween(min, max) + 1);
  const middle = new Date(min.getTime() + Math.floor(span / 2) * 86400000);
  return <Card title="甘特排期" extra={<Typography.Text type="secondary">{dateLabel(min)} — {dateLabel(max)}</Typography.Text>}>
    <div className="project-gantt-scroll"><div className="project-gantt" style={{ minWidth: Math.max(760, span * 18) }}>
      <div className="project-gantt-head project-gantt-name">任务</div>
      <div className="project-gantt-head project-gantt-axis"><span>{dateLabel(min)}</span><span>{dateLabel(middle)}</span><span>{dateLabel(max)}</span></div>
      {dated.map(({ task, start, end }) => {
        const left = daysBetween(min, start) / span * 100;
        const width = Math.max(1.5, (daysBetween(start, end) + 1) / span * 100);
        return <div className="project-gantt-row" key={task.id}>
          <Button type="link" className="project-gantt-task" onClick={() => openTask(task)}>{task.title}</Button>
          <div className="project-gantt-track">
            <button type="button" className={`project-gantt-bar is-${task.status}`} style={{ left: `${left}%`, width: `${width}%` }} onClick={() => openTask(task)} title={`${task.title} · ${dateLabel(start)}—${dateLabel(end)}`}><span>{width > 14 ? task.title : ""}</span></button>
          </div>
        </div>;
      })}
    </div></div>
  </Card>;
}

function dateLabel(value: Date): string {
  return value.toISOString().slice(5, 10);
}

function today(): string {
  const value = new Date();
  const part = (number: number) => String(number).padStart(2, "0");
  return `${value.getFullYear()}-${part(value.getMonth() + 1)}-${part(value.getDate())}`;
}
