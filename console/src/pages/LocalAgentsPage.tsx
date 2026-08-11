import {
  Alert, App, Button, Descriptions, Popconfirm, Progress, Space, Table, Tag,
  Typography,
} from "antd";
import { DeleteOutlined, ReloadOutlined } from "@ant-design/icons";
import { PageContainer } from "@ant-design/pro-components";
import { useEffect, useState } from "react";
import { consoleApi } from "../api";
import { localAgentCapacity, localAgentReadiness, localAgentVerified } from "../localAgentPresentation";
import type { LocalAgentDevice } from "../types";

function formatTime(value: number): string {
  return value ? new Date(value * 1000).toLocaleString() : "—";
}

export default function LocalAgentsPage() {
  const { message } = App.useApp();
  const [devices, setDevices] = useState<LocalAgentDevice[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      setDevices((await consoleApi.devices()).devices);
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : "Local Agent 加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  async function revoke(device: LocalAgentDevice) {
    try {
      await consoleApi.revokeDevice(device.id);
      message.success(`${device.name} 已撤销`);
      await load();
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : "撤销失败");
    }
  }

  return (
    <PageContainer
      title="Local Agent"
      subTitle="查看当前账户已绑定执行节点的真实心跳、能力与容量"
      extra={<Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>}
      header={{ breadcrumb: { items: [{ title: "工作区" }, { title: "Local Agent" }] } }}
    >
      <Alert
        type="info"
        showIcon
        title="支持同一账户绑定多个独立 Local Agent"
        description="每个副本应使用独立的数据目录和工作副本；不支持多个进程共享同一个 SQLite 数据库或同一可写工作区。任务可指定某台设备，也可由任一在线兼容设备领取。"
        style={{ marginBottom: 16 }}
      />
      <Table<LocalAgentDevice>
        rowKey="id"
        loading={loading}
        dataSource={devices}
        pagination={false}
        expandable={{
          expandedRowRender: (device) => (
            <Descriptions bordered size="small" column={{ xs: 1, sm: 2 }} items={[
              { key: "id", label: "设备 ID", children: <Typography.Text copyable code>{device.id}</Typography.Text> },
              { key: "verified", label: "身份验证", children: localAgentVerified(device) ? "已验证" : "未完成挑战验证" },
              { key: "heartbeat", label: "最近心跳", children: formatTime(device.last_seen_at) },
              { key: "tools", label: "可用工具", children: Object.keys(device.capabilities?.supported_tools || {}).join("、") || "—" },
              { key: "capabilities", label: "协议能力", children: (device.capabilities?.capabilities || []).join("、") || "—" },
              { key: "error", label: "最近失败", span: 2, children: device.latest_error ? `${device.latest_error.code || "执行失败"} · ${device.latest_error.message || "无详情"} · ${formatTime(device.latest_error.occurred_at)}` : "—" },
            ]} />
          ),
        }}
        scroll={{ x: 940 }}
        columns={[
          { title: "设备", dataIndex: "name", width: 200, render: (_value, device) => <Space orientation="vertical" size={0}><Typography.Text strong>{device.name}</Typography.Text><Typography.Text type="secondary">{device.platform || "未知平台"} {device.arch} · App {device.app_version || "—"}</Typography.Text></Space> },
          { title: "状态", dataIndex: "readiness", width: 150, render: (_value, device) => { const readiness = localAgentReadiness(device); return <Tag color={readiness.color}>{readiness.label}</Tag>; } },
          { title: "最近心跳", dataIndex: "last_seen_at", width: 180, render: (value) => formatTime(Number(value)) },
          { title: "并行容量", width: 180, render: (_value, device) => { const capacity = localAgentCapacity(device); return <Progress size="small" percent={Math.min(100, Math.round(capacity.active / capacity.parallel * 100))} format={() => `${capacity.active}/${capacity.parallel}`} />; } },
          { title: "驻留容量", width: 180, render: (_value, device) => { const capacity = localAgentCapacity(device); return `${capacity.resident}/${capacity.resident_limit}`; } },
          { title: "操作", width: 110, fixed: "right", render: (_value, device) => localAgentReadiness(device).key === "revoked" ? "—" : <Popconfirm title={`撤销 ${device.name}？`} description="设备令牌会立即失效，活跃租约将进入恢复。" onConfirm={() => void revoke(device)}><Button danger type="link" icon={<DeleteOutlined />}>撤销</Button></Popconfirm> },
        ]}
      />
    </PageContainer>
  );
}
