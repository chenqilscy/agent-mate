import {
  Alert, App, Button, Descriptions, Drawer, Form, Input, InputNumber, Modal,
  Popconfirm, Select, Space, Switch, Table, Tag, Typography,
} from "antd";
import {
  ApiOutlined, DeleteOutlined, EditOutlined, HistoryOutlined, PlayCircleOutlined,
  PlusOutlined, RedoOutlined,
} from "@ant-design/icons";
import { PageContainer, ProTable } from "@ant-design/pro-components";
import type { ProColumns } from "@ant-design/pro-components";
import { useEffect, useMemo, useState } from "react";
import { consoleApi } from "../api";
import { localAgentReadiness, localAgentVerified } from "../localAgentPresentation";
import type {
  AutomationFireRecord, AutomationRecord, AutomationTriggerKind,
  AutomationWebhookRecord, LocalAgentDevice, Project,
} from "../types";

type AutomationForm = {
  name: string;
  prompt: string;
  project_id?: string;
  trigger_kind: AutomationTriggerKind;
  interval_min: number;
  at_time: string;
  timezone: string;
  model_ref?: string;
  routing_mode: "any_compatible" | "specific";
  target_device_id?: string;
  enabled: boolean;
  timeout_sec: number;
  max_attempts: number;
  retry_backoff_sec: number;
  max_total_tokens: number;
  notify_policy: string[];
  preauthorized_permissions: string[];
};

const defaults: AutomationForm = {
  name: "", prompt: "", trigger_kind: "interval", interval_min: 60,
  at_time: "09:00", timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "server_local",
  enabled: true, timeout_sec: 300, max_attempts: 3,
  routing_mode: "any_compatible", target_device_id: undefined,
  retry_backoff_sec: 30, max_total_tokens: 0,
  notify_policy: ["failure", "recovery"], preauthorized_permissions: [],
};

const triggerLabels: Record<AutomationTriggerKind, string> = {
  interval: "固定间隔", daily: "每日定时", health_daily: "每日项目健康检查", webhook: "Webhook",
};

const statusColors: Record<string, string> = {
  succeeded: "success", running: "processing", queued: "blue", retry_wait: "warning",
  dead_letter: "error", ignored: "default", cancelled: "default", failed: "error",
};

function formatTime(value?: number | null): string {
  return value ? new Date(value * 1000).toLocaleString() : "—";
}

function errorText(reason: unknown, fallback: string): string {
  return reason instanceof Error ? reason.message : fallback;
}

export default function AutomationsPage() {
  const { message } = App.useApp();
  const [items, setItems] = useState<AutomationRecord[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [devices, setDevices] = useState<LocalAgentDevice[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<AutomationRecord | null | undefined>(undefined);
  const [historyOf, setHistoryOf] = useState<AutomationRecord | null>(null);
  const [fires, setFires] = useState<AutomationFireRecord[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [webhookOf, setWebhookOf] = useState<AutomationRecord | null>(null);
  const [webhook, setWebhook] = useState<AutomationWebhookRecord | null>(null);
  const [webhookLoading, setWebhookLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm<AutomationForm>();
  const triggerKind = Form.useWatch("trigger_kind", form);
  const routingMode = Form.useWatch("routing_mode", form);

  async function load() {
    setLoading(true);
    try {
      const [automationResult, projectResult, deviceResult] = await Promise.all([
        consoleApi.automations(), consoleApi.projects(), consoleApi.devices(),
      ]);
      setItems(automationResult.automations);
      setProjects(projectResult.projects);
      setDevices(deviceResult.devices);
    } catch (reason) {
      message.error(errorText(reason, "自动化加载失败"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  function openEditor(item: AutomationRecord | null) {
    setEditing(item);
    form.setFieldsValue(item ? {
      ...item,
      project_id: item.project_id || undefined,
      model_ref: item.model_ref || undefined,
      target_device_id: item.target_device_id || undefined,
      notify_policy: item.notify_policy.split(",").filter(Boolean),
      preauthorized_permissions: item.preauthorized_permissions || [],
    } : defaults);
  }

  async function save(values: AutomationForm) {
    setSaving(true);
    const payload = {
      ...values,
      project_id: values.project_id || null,
      model_ref: values.model_ref?.trim() || null,
      target_device_id: values.routing_mode === "specific" ? values.target_device_id || "" : "",
      name: values.name.trim(), prompt: values.prompt.trim(),
      notify_policy: values.notify_policy.join(","),
      concurrency_policy: "skip" as const,
    };
    try {
      if (editing) await consoleApi.updateAutomation(editing.id, { ...payload, expected_version: editing.version });
      else await consoleApi.createAutomation(payload);
      message.success(editing ? "自动化已更新" : "自动化已创建");
      setEditing(undefined);
      await load();
    } catch (reason) {
      message.error(errorText(reason, "自动化保存失败"));
    } finally {
      setSaving(false);
    }
  }

  async function setEnabled(item: AutomationRecord, enabled: boolean) {
    try {
      await consoleApi.updateAutomation(item.id, { expected_version: item.version, enabled });
      message.success(enabled ? "自动化已启用" : "自动化已停用");
      await load();
    } catch (reason) {
      message.error(errorText(reason, "状态更新失败"));
    }
  }

  async function runNow(item: AutomationRecord) {
    try {
      const result = await consoleApi.runAutomation(item.id);
      message.success(result.skipped ? "已有执行在运行，本次已跳过" : "执行已提交给 Local Agent");
      await load();
    } catch (reason) {
      message.error(errorText(reason, "启动失败"));
    }
  }

  async function loadHistory(item: AutomationRecord) {
    setHistoryOf(item);
    setHistoryLoading(true);
    try {
      setFires((await consoleApi.automationFires(item.id)).fires);
    } catch (reason) {
      message.error(errorText(reason, "执行历史加载失败"));
    } finally {
      setHistoryLoading(false);
    }
  }

  async function mutateFire(fire: AutomationFireRecord, action: "replay" | "ignore") {
    try {
      if (action === "replay") await consoleApi.replayAutomationFire(fire.id);
      else await consoleApi.ignoreAutomationFire(fire.id);
      message.success(action === "replay" ? "失败执行已重新排队" : "失败执行已忽略");
      if (historyOf) await loadHistory(historyOf);
    } catch (reason) {
      message.error(errorText(reason, "操作失败"));
    }
  }

  async function loadWebhook(item: AutomationRecord) {
    setWebhookOf(item);
    setWebhookLoading(true);
    try {
      setWebhook(await consoleApi.automationWebhook(item.id));
    } catch (reason) {
      message.error(errorText(reason, "Webhook 加载失败"));
    } finally {
      setWebhookLoading(false);
    }
  }

  async function createOrRotateWebhook(rotate: boolean) {
    if (!webhookOf) return;
    setWebhookLoading(true);
    try {
      const result = rotate
        ? await consoleApi.rotateAutomationWebhook(webhookOf.id)
        : await consoleApi.createAutomationWebhook(webhookOf.id);
      setWebhook(result);
      message.success(rotate ? "密钥已轮换，请立即保存新密钥" : "Webhook 已创建，请立即保存密钥");
    } catch (reason) {
      message.error(errorText(reason, "Webhook 操作失败"));
    } finally {
      setWebhookLoading(false);
    }
  }

  const projectNames = useMemo(() => new Map(projects.map((item) => [item.id, item.name])), [projects]);
  const columns: ProColumns<AutomationRecord>[] = [
    { title: "名称", dataIndex: "name", width: 220, render: (_value, item) => <Space orientation="vertical" size={0}><Typography.Text strong>{item.name}</Typography.Text><Typography.Text type="secondary">{item.project_id ? projectNames.get(item.project_id) || "项目" : "个人"}</Typography.Text></Space> },
    { title: "触发方式", dataIndex: "trigger_kind", width: 200, render: (_value, item) => <Space orientation="vertical" size={0}><Tag>{triggerLabels[item.trigger_kind]}</Tag><Typography.Text type="secondary">{item.trigger_kind === "interval" ? `每 ${item.interval_min} 分钟` : ["daily", "health_daily"].includes(item.trigger_kind) ? `${item.at_time} · ${item.timezone}` : "签名请求"}</Typography.Text></Space> },
    { title: "执行设备", dataIndex: "routing_mode", width: 180, render: (_value, item) => item.routing_mode === "specific" ? devices.find((device) => device.id === item.target_device_id)?.name || "指定设备（不可用）" : "任一兼容设备" },
    { title: "下次执行", dataIndex: "next_run_at", width: 180, render: (value) => formatTime(Number(value) || null) },
    { title: "最近状态", dataIndex: "last_status", width: 120, render: (value) => value ? <Tag color={statusColors[String(value)] || "default"}>{String(value)}</Tag> : "—" },
    { title: "启用", dataIndex: "enabled", width: 90, fixed: "right", render: (_value, item) => <Switch checked={item.enabled} aria-label={`${item.name}启用状态`} onChange={(checked) => void setEnabled(item, checked)} /> },
    { title: "操作", valueType: "option", width: 290, fixed: "right", render: (_value, item) => <Space wrap>
      <Button type="link" size="small" icon={<PlayCircleOutlined />} onClick={() => void runNow(item)}>执行</Button>
      <Button type="link" size="small" icon={<HistoryOutlined />} onClick={() => void loadHistory(item)}>历史</Button>
      {item.trigger_kind === "webhook" && <Button type="link" size="small" icon={<ApiOutlined />} onClick={() => void loadWebhook(item)}>Webhook</Button>}
      <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEditor(item)}>编辑</Button>
      <Popconfirm title="删除此自动化？" description="历史执行记录会保留用于审计。" onConfirm={async () => { try { await consoleApi.deleteAutomation(item.id, item.version); message.success("自动化已删除"); await load(); } catch (reason) { message.error(errorText(reason, "删除失败")); } }}><Button type="link" danger size="small" icon={<DeleteOutlined />}>删除</Button></Popconfirm>
    </Space> },
  ];

  return (
    <PageContainer title="自动化" subTitle="由 Server 统一调度，Local Agent 领取并执行" extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => openEditor(null)}>新建自动化</Button>} header={{ breadcrumb: { items: [{ title: "工作区" }, { title: "自动化" }] } }}>
      <Alert type="info" showIcon title="控制面与执行面已分离" description="定义、调度、重试和审计保存在 Server；模型调用、本机文件和需要本机权限的工具只在已绑定的 Local Agent 上执行。" style={{ marginBottom: 16 }} />
      <ProTable<AutomationRecord> rowKey="id" columns={columns} dataSource={items} loading={loading} search={false} scroll={{ x: 1280 }} options={{ reload: () => void load(), density: true, setting: true }} />

      <Drawer size={640} open={editing !== undefined} title={editing ? `编辑 ${editing.name}` : "新建自动化"} onClose={() => setEditing(undefined)} destroyOnHidden extra={<Button type="primary" loading={saving} onClick={() => form.submit()}>保存</Button>}>
        <Form<AutomationForm> form={form} layout="vertical" onFinish={(values) => void save(values)} initialValues={defaults}>
          <Form.Item name="name" label="名称" rules={[{ required: true, whitespace: true }]}><Input maxLength={120} /></Form.Item>
          <Form.Item name="prompt" label="执行指令" rules={[{ required: true, whitespace: true }]}><Input.TextArea rows={6} maxLength={200000} showCount /></Form.Item>
          <Form.Item name="project_id" label="关联项目"><Select allowClear placeholder="个人自动化" options={projects.map((item) => ({ value: item.id, label: item.name }))} /></Form.Item>
          <Form.Item name="trigger_kind" label="触发方式" rules={[{ required: true }]}><Select options={Object.entries(triggerLabels).map(([value, label]) => ({ value, label }))} /></Form.Item>
          {triggerKind === "interval" && <Form.Item name="interval_min" label="执行间隔（分钟）" rules={[{ required: true }]}><InputNumber min={1} precision={0} style={{ width: "100%" }} /></Form.Item>}
          {["daily", "health_daily"].includes(triggerKind || "") && <Form.Item name="at_time" label="每日执行时间" rules={[{ required: true }, { pattern: /^([01]\d|2[0-3]):[0-5]\d$/, message: "请输入 HH:MM" }]}><Input placeholder="09:00" maxLength={5} /></Form.Item>}
          {["daily", "health_daily"].includes(triggerKind || "") && <Form.Item name="timezone" label="时区" tooltip="使用 IANA 时区；新建时自动读取当前浏览器时区" rules={[{ required: true, whitespace: true }]}><Input placeholder="Asia/Shanghai" maxLength={100} /></Form.Item>}
          {triggerKind === "health_daily" && <Alert type="warning" showIcon title="项目健康检查必须选择项目" style={{ marginBottom: 16 }} />}
          <Form.Item name="model_ref" label="模型引用" tooltip="留空时由 Local Agent 使用当前默认模型"><Input allowClear maxLength={200} /></Form.Item>
          <Form.Item name="routing_mode" label="设备路由" rules={[{ required: true }]} tooltip="执行归属始终是自动化创建者；这里只决定由哪台已验证设备领取">
            <Select options={[{ value: "any_compatible", label: "任一在线兼容设备" }, { value: "specific", label: "指定 Local Agent" }]} />
          </Form.Item>
          {routingMode === "specific" && <Form.Item name="target_device_id" label="目标 Local Agent" rules={[{ required: true, message: "请选择一台已验证设备" }]}>
            <Select
              placeholder="选择已验证设备"
              options={devices.filter((device) => localAgentVerified(device) && device.status === "active" && localAgentReadiness(device).key !== "revoked").map((device) => ({
                value: device.id,
                label: `${device.name} · ${localAgentReadiness(device).label}`,
                disabled: device.compatible === false,
              }))}
            />
          </Form.Item>}
          {routingMode === "specific" && <Alert type="info" showIcon title="离线设备仍可被指定" description="Run 会保持排队并明确显示离线、容量不足或工作区写锁等原因，设备恢复后继续领取。" style={{ marginBottom: 16 }} />}
          <Space size="middle" wrap style={{ width: "100%" }}>
            <Form.Item name="timeout_sec" label="超时（秒）"><InputNumber min={1} max={3600} precision={0} /></Form.Item>
            <Form.Item name="max_attempts" label="最大尝试次数"><InputNumber min={1} max={10} precision={0} /></Form.Item>
            <Form.Item name="retry_backoff_sec" label="重试退避（秒）"><InputNumber min={1} max={86400} precision={0} /></Form.Item>
            <Form.Item name="max_total_tokens" label="Token 上限（0=不限）"><InputNumber min={0} max={10000000} precision={0} /></Form.Item>
          </Space>
          <Form.Item name="notify_policy" label="通知策略"><Select mode="multiple" options={[{ value: "failure", label: "最终失败" }, { value: "recovery", label: "重试恢复" }, { value: "success", label: "每次成功" }]} /></Form.Item>
          <Form.Item name="preauthorized_permissions" label="预授权权限" tooltip="仅填写已由管理员审批、可无人值守使用的权限标识"><Select mode="tags" tokenSeparators={[","]} /></Form.Item>
          <Form.Item name="enabled" label="创建后启用" valuePropName="checked"><Switch /></Form.Item>
        </Form>
      </Drawer>

      <Modal width={900} open={Boolean(historyOf)} title={`${historyOf?.name || "自动化"} · 执行历史`} footer={null} onCancel={() => setHistoryOf(null)} destroyOnHidden>
        <Table<AutomationFireRecord> rowKey="id" size="small" loading={historyLoading} dataSource={fires} scroll={{ x: 900 }} pagination={{ pageSize: 10 }} columns={[
          { title: "计划时间", dataIndex: "planned_at", width: 180, render: (value) => formatTime(Number(value)) },
          { title: "状态", dataIndex: "status", width: 120, render: (value) => <Tag color={statusColors[String(value)] || "default"}>{String(value)}</Tag> },
          { title: "尝试", width: 90, render: (_value, item) => `${item.attempt}/${item.max_attempts}` },
          { title: "错误", dataIndex: "error_message", ellipsis: true, render: (value, item) => value || item.error_code || "—" },
          { title: "操作", width: 180, fixed: "right", render: (_value, item) => <Space>{["dead_letter", "ignored"].includes(item.status) && <Button size="small" type="link" icon={<RedoOutlined />} onClick={() => void mutateFire(item, "replay")}>重放</Button>}{["dead_letter", "retry_wait"].includes(item.status) && <Button size="small" type="link" onClick={() => void mutateFire(item, "ignore")}>忽略</Button>}</Space> },
        ]} />
      </Modal>

      <Modal width={760} open={Boolean(webhookOf)} title={`${webhookOf?.name || "自动化"} · Webhook`} footer={null} onCancel={() => { setWebhookOf(null); setWebhook(null); }} destroyOnHidden loading={webhookLoading}>
        {!webhook?.configured ? <Alert type="info" showIcon title="尚未创建 Webhook" description="创建后 Server 会生成签名密钥；密钥只显示一次。" action={<Button type="primary" onClick={() => void createOrRotateWebhook(false)}>创建</Button>} /> : <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
          {webhook.secret && <Alert type="warning" showIcon title="立即保存签名密钥" description={<Typography.Text copyable code>{webhook.secret}</Typography.Text>} />}
          <Descriptions bordered size="small" column={1} items={[
            { key: "endpoint", label: "入口", children: <Typography.Text copyable code>{webhook.endpoint}</Typography.Text> },
            { key: "created", label: "创建时间", children: formatTime(webhook.created_at) },
            { key: "rotated", label: "轮换时间", children: formatTime(webhook.rotated_at) },
          ]} />
          <Space><Popconfirm title="轮换密钥？" description="旧密钥会立即失效。" onConfirm={() => void createOrRotateWebhook(true)}><Button icon={<RedoOutlined />}>轮换密钥</Button></Popconfirm><Popconfirm title="删除 Webhook？" onConfirm={async () => { if (!webhookOf) return; try { await consoleApi.deleteAutomationWebhook(webhookOf.id); message.success("Webhook 已删除"); setWebhook({ configured: false, automation_id: webhookOf.id, deliveries: [] }); } catch (reason) { message.error(errorText(reason, "删除失败")); } }}><Button danger icon={<DeleteOutlined />}>删除</Button></Popconfirm></Space>
          <Table rowKey="id" size="small" dataSource={webhook.deliveries} pagination={{ pageSize: 5 }} columns={[{ title: "接收时间", dataIndex: "received_at", render: (value) => formatTime(Number(value)) }, { title: "幂等键", dataIndex: "idempotency_key", ellipsis: true }, { title: "状态", dataIndex: "status", render: (value) => <Tag>{String(value)}</Tag> }, { title: "执行状态", dataIndex: "fire_status", render: (value) => value || "—" }]} />
        </Space>}
      </Modal>
    </PageContainer>
  );
}
