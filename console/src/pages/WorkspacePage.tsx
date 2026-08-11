import {
  Alert, App, Button, Card, Empty, Space, Statistic, Tag, Typography,
} from "antd";
import { CompatList as List } from "../components/CompatList";
import {
  CheckCircleOutlined, ClockCircleOutlined, DesktopOutlined,
  PlayCircleOutlined, WarningOutlined,
} from "@ant-design/icons";
import { PageContainer } from "@ant-design/pro-components";
import { useCallback, useEffect, useMemo, useState } from "react";
import { navigate } from "../router";
import type { Account, LocalAgentDevice } from "../types";
import {
  workspaceApi,
  type WorkspaceActionItem,
  type WorkspaceActionItemsResponse,
  type WorkspaceRun,
  type WorkspaceSession,
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
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [actionResult, runResult, sessionResult, deviceResult] = await Promise.all([
        workspaceApi.actionItems(localDate()),
        workspaceApi.runs(),
        workspaceApi.sessions(),
        workspaceApi.devices(),
      ]);
      setActions(actionResult);
      setRuns(runResult.runs || []);
      setSessions(sessionResult.sessions || []);
      setDevices(deviceResult.devices || []);
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
      actions={[<Button type="link" key="open" onClick={() => openRun(run)}>查看执行</Button>]}
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
