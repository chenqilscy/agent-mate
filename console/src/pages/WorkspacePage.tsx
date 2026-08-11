import {
  Alert, App, Button, Card, Empty, Input, Select, Space, Statistic, Tag, Typography,
} from "antd";
import { CompatList as List } from "../components/CompatList";
import {
  CheckCircleOutlined, ClockCircleOutlined, DesktopOutlined,
  PlayCircleOutlined, WarningOutlined,
} from "@ant-design/icons";
import { PageContainer } from "@ant-design/pro-components";
import { useCallback, useEffect, useMemo, useState } from "react";
import { navigate } from "../router";
import { desktopCompanionRunUrl } from "../desktopHandoff";
import type { Account, LocalAgentDevice, Project } from "../types";
import {
  workspaceApi,
  type WorkspaceActionItem,
  type WorkspaceActionItemsResponse,
  type WorkspaceRun,
  type WorkspaceSession,
  type WorkspaceTurnMode,
  type WorkspaceTurnResponse,
} from "../workspaceApi";

const ACTIVE_RUNS = new Set(["queued", "leased", "planning", "running", "waiting_user", "waiting_approval", "paused", "recoverable"]);
const ATTENTION_RUNS = new Set(["waiting_user", "waiting_approval"]);
const FAILED_RUNS = new Set(["failed", "cancelled"]);

const ACTION_LABEL: Record<string, string> = {
  overdue: "已逾期",
  due_today: "今日到期",
  blocked: "被阻塞",
  in_progress: "进行中",
  awaiting_acceptance: "待验收",
  starts_today: "今日开始",
  ready: "可开始",
  urgent: "紧急",
};

const RUN_LABEL: Record<string, string> = {
  queued: "等待执行节点",
  leased: "已领取",
  planning: "规划中",
  running: "执行中",
  waiting_user: "等待回答或授权",
  waiting_approval: "等待本机授权",
  paused: "已暂停",
  recoverable: "等待恢复",
  completed: "已完成",
  succeeded: "已完成",
  failed: "执行失败",
  cancelled: "已取消",
};

function localDate(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}
function relativeTime(value: number): string {
  if (!value) return "时间未知";
  const seconds = Math.max(0, Math.round(Date.now() / 1000 - value));
  if (seconds < 60) return "刚刚";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时前`;
  return `${Math.floor(seconds / 86400)} 天前`;
}

function runColor(status: string): string {
  if (ATTENTION_RUNS.has(status) || status === "paused") return "warning";
  if (FAILED_RUNS.has(status)) return "error";
  if (["completed", "succeeded"].includes(status)) return "success";
  return "processing";
}

function deviceColor(device: LocalAgentDevice): string {
  if (device.readiness === "ready") return "success";
  if (device.readiness === "busy") return "processing";
  if (device.readiness === "incompatible" || device.readiness === "unverified") return "warning";
  return "default";
}

function deviceLabel(device: LocalAgentDevice): string {
  return ({
    ready: "可执行", busy: "忙碌", offline: "离线", incompatible: "协议不兼容",
    unverified: "未验证", revoked: "已撤销",
  } as Record<string, string>)[device.readiness || ""] || (device.online ? "在线" : "离线");
}

export default function WorkspacePage({ account }: { account: Account }) {
  const { message } = App.useApp();
  const [actions, setActions] = useState<WorkspaceActionItemsResponse | null>(null);
  const [runs, setRuns] = useState<WorkspaceRun[]>([]);
  const [sessions, setSessions] = useState<WorkspaceSession[]>([]);
  const [devices, setDevices] = useState<LocalAgentDevice[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [prompt, setPrompt] = useState("");
  const [mode, setMode] = useState<WorkspaceTurnMode>("exec");
  const [projectId, setProjectId] = useState("");
  const [targetDeviceId, setTargetDeviceId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [createdTurn, setCreatedTurn] = useState<WorkspaceTurnResponse | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [actionResult, runResult, sessionResult, deviceResult, projectResult] = await Promise.all([
        workspaceApi.actionItems(localDate()),
        workspaceApi.runs(),
        workspaceApi.sessions(),
        workspaceApi.devices(),
        workspaceApi.projects(),
      ]);
      setActions(actionResult);
      setRuns(runResult.runs || []);
      setSessions(sessionResult.sessions || []);
      setDevices(deviceResult.devices || []);
      setProjects(projectResult.projects || []);
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : "个人工作台加载失败");
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => { void load(); }, [load]);

  const sessionById = useMemo(() => new Map(sessions.map((session) => [session.id, session])), [sessions]);
  const actionById = useMemo(() => new Map([
    ...(actions?.items || []), ...(actions?.unassigned || []),
  ].map((item) => [item.id, item])), [actions]);
  const sortedRuns = useMemo(() => [...runs].sort((left, right) => right.updated_at - left.updated_at), [runs]);
  const activeRuns = sortedRuns.filter((run) => ACTIVE_RUNS.has(run.status));
  const attentionRuns = sortedRuns.filter((run) => ATTENTION_RUNS.has(run.status));
  const recentFailed = sortedRuns.filter((run) => FAILED_RUNS.has(run.status) && run.updated_at >= Date.now() / 1000 - 7 * 86400);
  const writableProjects = projects.filter((project) => project.role !== "Viewer" && !project.archived_at);
  const compatibleDevices = devices.filter((device) =>
    device.status === "active" && device.verified && device.compatible
    && ["ready", "busy"].includes(device.readiness || ""),
  );

  const runTitle = (run: WorkspaceRun): string => {
    const action = run.work_item_id ? actionById.get(run.work_item_id) : undefined;
    const session = sessionById.get(run.session_id);
    return action?.title || session?.title || `Run ${run.id.slice(0, 8)}`;
  };
  const runProject = (run: WorkspaceRun): string | null => {
    const action = run.work_item_id ? actionById.get(run.work_item_id) : undefined;
    return run.project_id || action?.project.id || sessionById.get(run.session_id)?.project_id || null;
  };
  const openRun = (run: WorkspaceRun) => {
    const projectId = runProject(run);
    if (projectId) navigate(`/projects/${encodeURIComponent(projectId)}`);
    else message.info("此 Run 没有关联项目，请在 Desktop Companion 中查看会话详情");
  };
  const startRun = async () => {
    const text = prompt.trim();
    if (!text) return;
    setSubmitting(true);
    try {
      const turn = await workspaceApi.createTurn({
        text,
        title: text.slice(0, 500),
        project_id: projectId || null,
        kind: projectId ? "projexec" : "chat",
        mode,
        workspace: projectId ? `project:${projectId}` : "default",
        target_device_id: targetDeviceId,
        required_capabilities: [
          "run_events_v1",
          "llm.chat",
          ...(mode === "ask" ? [] : ["agent.tools"]),
        ],
        request_snapshot: {
          launched_from: "server_workspace",
          loadout: {
            experts: [], skills: [], skill_bundles: [], connectors: [], knowledge_ids: [],
          },
          refs: [],
          local_input_key: null,
        },
      }, crypto.randomUUID());
      setCreatedTurn(turn);
      setPrompt("");
      message.success(turn.duplicate ? "已定位到同一执行请求" : "Run 已提交给执行节点");
      await load();
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : "Run 创建失败");
    } finally {
      setSubmitting(false);
    }
  };

  const renderAction = (item: WorkspaceActionItem) => (
    <List.Item
      key={item.id}
      actions={[<Button type="link" key="open" onClick={() => navigate(`/projects/${encodeURIComponent(item.project.id)}`)}>查看任务</Button>]}
    >
      <List.Item.Meta
        title={<Space size={[6, 6]} wrap><span>{item.title}</span><Tag color="blue">{ACTION_LABEL[item.action_reason] || item.action_reason}</Tag></Space>}
        description={`${item.project.name} · ${item.project.role}${item.due_date ? ` · 截止 ${item.due_date}` : ""}`}
      />
    </List.Item>
  );

  const renderRun = (run: WorkspaceRun) => (
    <List.Item
      key={run.id}
      actions={[
        <Button type="link" key="open" onClick={() => openRun(run)}>查看执行</Button>,
        <Button
          type="link"
          key="desktop"
          href={desktopCompanionRunUrl({ sessionId: run.session_id, projectId: runProject(run) })}
        >
          在执行节点打开
        </Button>,
      ]}
    >
      <List.Item.Meta
        title={<Space size={[6, 6]} wrap><span>{runTitle(run)}</span><Tag color={runColor(run.status)}>{RUN_LABEL[run.status] || run.status}</Tag></Space>}
        description={run.queue_context?.message || run.error_message || `${relativeTime(run.updated_at)} · Run ${run.id.slice(0, 8)}`}
      />
    </List.Item>
  );

  return (
    <PageContainer
      title="我的工作台"
      subTitle="Server Workspace · 决定下一步、查看执行并验收交付"
      header={{ breadcrumb: { items: [{ title: "工作区" }, { title: "我的工作台" }] } }}
      extra={<Space><Button onClick={() => void load()} loading={loading}>刷新</Button>{account.is_platform_admin && <Button onClick={() => navigate("/admin")}>管理总览</Button>}</Space>}
    >
      <Card
        className="workspace-run-composer"
        title="发起执行"
        extra={<Tag color="blue">Server 原子创建 · Local Agent 执行</Tag>}
      >
        <Input.TextArea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder="描述要完成的工作。Server 保存业务上下文，本机文件、命令、MCP 与凭据只在所选执行节点处理。"
          autoSize={{ minRows: 3, maxRows: 8 }}
          maxLength={200000}
        />
        <div className="workspace-run-controls">
          <Select
            aria-label="执行模式"
            value={mode}
            onChange={setMode}
            options={[
              { value: "exec", label: "执行" },
              { value: "plan", label: "规划" },
              { value: "ask", label: "问答" },
            ]}
          />
          <Select
            aria-label="关联项目"
            value={projectId}
            onChange={setProjectId}
            options={[
              { value: "", label: "不关联项目" },
              ...writableProjects.map((project) => ({ value: project.id, label: project.name })),
            ]}
          />
          <Select
            aria-label="执行节点"
            value={targetDeviceId}
            onChange={setTargetDeviceId}
            options={[
              { value: "", label: "自动选择兼容节点" },
              ...compatibleDevices.map((device) => ({
                value: device.id,
                label: `${device.name || "Local Agent"} · ${deviceLabel(device)}`,
              })),
            ]}
          />
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            loading={submitting}
            disabled={!prompt.trim()}
            onClick={() => void startRun()}
          >
            提交 Run
          </Button>
        </div>
        <Typography.Paragraph type="secondary" className="workspace-run-note">
          未指定节点时由 Server 按协议、能力与容量分配；涉及本机输入的任务，请先在 Desktop Companion 中准备对应工作区。
        </Typography.Paragraph>
      </Card>

      {createdTurn && (
        <Alert
          className="workspace-run-created"
          type="success"
          showIcon
          title={`Run ${createdTurn.run.id.slice(0, 8)} 已进入队列`}
          description="业务记录已经由 Server 原子提交。你可以留在 Workspace 观察权威状态，或打开 Desktop Companion 查看本机执行过程。"
          action={(
            <Button
              type="primary"
              href={desktopCompanionRunUrl({
                sessionId: createdTurn.session.id,
                projectId: createdTurn.session.project_id,
              })}
            >
              在执行节点打开
            </Button>
          )}
        />
      )}

      <div className="workspace-stat-grid">
        <Card loading={loading}><Statistic title="我的行动项" value={actions?.summary.assigned || 0} prefix={<CheckCircleOutlined />} /></Card>
        <Card loading={loading}><Statistic title="等待我处理" value={attentionRuns.length} prefix={<ClockCircleOutlined />} /></Card>
        <Card loading={loading}><Statistic title="活动 Run" value={activeRuns.length} prefix={<PlayCircleOutlined />} /></Card>
        <Card loading={loading}><Statistic title="近 7 天失败" value={recentFailed.length} prefix={<WarningOutlined />} /></Card>
      </div>

      {attentionRuns.length > 0 && (
        <Alert
          className="workspace-trust-alert"
          type="warning"
          showIcon
          title={`${attentionRuns.length} 个 Run 正在等待回答或本机授权`}
          description="Server Workspace 展示权威状态；涉及本机文件、进程或高风险工具的确认，仍须在执行节点的 Desktop Companion 中完成。"
        />
      )}

      <div className="workspace-main-grid">
        <Space orientation="vertical" size={16} className="full-width">
          <Card title="我的行动项" extra={<Button type="link" onClick={() => navigate("/projects")}>查看全部项目</Button>}>
            {actions?.items.length ? <List dataSource={actions.items.slice(0, 8)} renderItem={renderAction} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={loading ? "正在读取 Server 行动项…" : "当前没有需要处理的已分配任务"} />}
          </Card>
          <Card title="最近执行">
            {sortedRuns.length ? <List dataSource={sortedRuns.slice(0, 8)} renderItem={renderRun} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={loading ? "正在读取 Server Run…" : "还没有执行记录"} />}
          </Card>
        </Space>

        <Space orientation="vertical" size={16} className="full-width">
          <Card title="需要我处理" extra={<Tag color={attentionRuns.length ? "warning" : "success"}>{attentionRuns.length}</Tag>}>
            {attentionRuns.length ? <List dataSource={attentionRuns.slice(0, 6)} renderItem={renderRun} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前没有等待回答或授权的 Run" />}
          </Card>
          <Card title={<Space><DesktopOutlined />执行节点</Space>} extra={<Button type="link" onClick={() => navigate("/local-agents")}>设备管理</Button>}>
            {devices.length ? (
              <List dataSource={devices.slice(0, 5)} renderItem={(device) => (
                <List.Item key={device.id}>
                  <List.Item.Meta title={device.name || "Local Agent"} description={`${device.platform || "未知平台"} · ${relativeTime(device.last_seen_at)}`} />
                  <Tag color={deviceColor(device)}>{deviceLabel(device)}</Tag>
                </List.Item>
              )} />
            ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚未注册执行节点" />}
            <Typography.Paragraph type="secondary" className="workspace-device-note">
              Agent Runtime、工具、MCP、本机文件、进程与凭据在执行节点运行；Server 不直接连接你的设备。
            </Typography.Paragraph>
          </Card>
        </Space>
      </div>
    </PageContainer>
  );
}
