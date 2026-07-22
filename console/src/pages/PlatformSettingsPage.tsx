import {
  Alert, App, Button, Card, Descriptions, Form, Input, InputNumber, Popconfirm,
  Space, Table, Tag, Typography,
} from "antd";
import { PageContainer } from "@ant-design/pro-components";
import { ApiError, consoleApi } from "../api";
import type { PlatformSettingAudit, PlatformSettingItem, PlatformSettingsPayload } from "../types";
import { useEffect, useMemo, useState } from "react";

type Draft = {
  weknora_url: string;
  weknora_api_key: string;
  embedding_model_id: string;
  invite_ttl_seconds: number;
};

const sourceLabel: Record<string, string> = {
  database: "页面设置", environment: "部署环境", default: "系统默认",
};

function byKey(items: PlatformSettingItem[], key: string): PlatformSettingItem | undefined {
  return items.find((item) => item.key === key);
}

function errorText(reason: unknown): string {
  return reason instanceof ApiError || reason instanceof Error ? reason.message : String(reason);
}

async function validateHttpUrl(_rule: unknown, value?: string): Promise<void> {
  if (!value) return;
  try {
    const parsed = new URL(value);
    if ((parsed.protocol === "http:" || parsed.protocol === "https:") && parsed.hostname && !parsed.username && !parsed.password) return;
  } catch {
    // Use the same user-facing message for parse and protocol/credential failures.
  }
  throw new Error("请输入不含账号密码的有效 http(s) URL");
}

export default function PlatformSettingsPage() {
  const { message } = App.useApp();
  const [form] = Form.useForm<Draft>();
  const [data, setData] = useState<PlatformSettingsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const next = await consoleApi.platformSettings();
      setData(next);
      form.setFieldsValue({
        weknora_url: String(byKey(next.items, "knowledge.weknora_url")?.value || ""),
        weknora_api_key: "",
        embedding_model_id: String(byKey(next.items, "knowledge.weknora_embedding_model_id")?.value || ""),
        invite_ttl_seconds: Number(byKey(next.items, "collaboration.invite_ttl_seconds")?.value || 0),
      });
    } catch (reason) {
      message.error(errorText(reason));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const save = async (draft: Draft) => {
    setSaving(true);
    try {
      const values: Record<string, unknown> = {
        "knowledge.weknora_url": draft.weknora_url,
        "knowledge.weknora_embedding_model_id": draft.embedding_model_id,
        "collaboration.invite_ttl_seconds": draft.invite_ttl_seconds,
      };
      if (draft.weknora_api_key.trim()) values["knowledge.weknora_api_key"] = draft.weknora_api_key;
      const next = await consoleApi.savePlatformSettings(values);
      setData(next); form.setFieldValue("weknora_api_key", "");
      message.success("平台设置已保存并立即生效");
    } catch (reason) {
      message.error(errorText(reason));
    } finally {
      setSaving(false);
    }
  };

  const clear = async (keys: string[]) => {
    try {
      const next = await consoleApi.savePlatformSettings({}, keys);
      setData(next); await load();
      message.success("已恢复部署环境或系统默认值");
    } catch (reason) { message.error(errorText(reason)); }
  };

  const test = async () => {
    setTesting(true);
    try {
      const result = await consoleApi.testPlatformSettings("knowledge");
      if (result.ok) message.success(`连接成功 · WeKnora ${result.version || "未知版本"} · ${result.embedding_models || 0} 个嵌入模型`);
      else message.error(result.error || "连接测试失败");
    } catch (reason) { message.error(errorText(reason)); }
    finally { setTesting(false); }
  };

  const knowledgeItems = useMemo(() => data?.items.filter((item) => item.group === "knowledge") || [], [data]);
  const keyConfigured = byKey(knowledgeItems, "knowledge.weknora_api_key")?.configured;

  return (
    <PageContainer title="平台设置" subTitle="统一管理所有项目与成员共享的服务配置" header={{ breadcrumb: { items: [{ title: "系统" }, { title: "平台设置" }] } }}>
      <Alert type="info" showIcon message="设置作用域" description="这里的设置对整个平台生效。用户偏好、项目配置和助理渠道仍在各自入口管理；数据库、端口等启动参数不会出现在此处。" />
      <Form<Draft> form={form} layout="vertical" onFinish={(values) => void save(values)} style={{ marginTop: 16 }}>
        <Card title="知识服务 · 中央 WeKnora" loading={loading} extra={<Space><Button loading={testing} onClick={() => void test()}>测试连接</Button><Popconfirm title="恢复全部 WeKnora 部署值？" onConfirm={() => void clear(knowledgeItems.map((item) => item.key))}><Button>恢复部署值</Button></Popconfirm></Space>}>
          <Form.Item name="weknora_url" label="服务地址" rules={[{ required: true }, { validator: validateHttpUrl }]}><Input placeholder="http://127.0.0.1:37201" /></Form.Item>
          <Form.Item label={<Space>API Key<Tag color={keyConfigured ? "green" : "default"}>{keyConfigured ? "已配置" : "未配置"}</Tag></Space>} name="weknora_api_key" extra="留空表示保持当前密钥；保存后不会回显。"><Input.Password autoComplete="new-password" placeholder="输入新密钥以替换" /></Form.Item>
          <Form.Item name="embedding_model_id" label="默认嵌入模型 ID" extra="留空时由 Server 查询 WeKnora 并选择首个 embedding 模型。"><Input /></Form.Item>
          <Descriptions size="small" column={3} items={knowledgeItems.map((item) => ({ key: item.key, label: item.label, children: <Tag>{sourceLabel[item.source] || item.source}</Tag> }))} />
        </Card>
        <Card title="协作策略" loading={loading} style={{ marginTop: 16 }} extra={<Popconfirm title="恢复邀请策略部署值？" onConfirm={() => void clear(["collaboration.invite_ttl_seconds"])}><Button>恢复部署值</Button></Popconfirm>}>
          <Form.Item name="invite_ttl_seconds" label="项目邀请有效期（秒）" extra="0 表示永不过期；仅影响之后创建的邀请。"><InputNumber min={0} max={31536000} style={{ width: "100%" }} /></Form.Item>
        </Card>
        <Card title="启动级配置边界" style={{ marginTop: 16 }}>
          <Typography.Paragraph type="secondary">以下配置必须通过部署环境管理，不能假装热更新：</Typography.Paragraph>
          <Space wrap>{data?.deployment_only.map((key) => <Tag key={key}>{key}</Tag>)}</Space>
        </Card>
        <Space style={{ marginTop: 16 }}><Button type="primary" htmlType="submit" loading={saving}>保存并生效</Button></Space>
      </Form>
      <Card title="设置审计" style={{ marginTop: 16 }}>
        <Table<PlatformSettingAudit> rowKey="id" size="small" pagination={{ pageSize: 10 }} dataSource={data?.audit || []} columns={[
          { title: "设置", dataIndex: "setting_key" },
          { title: "动作", dataIndex: "action", width: 90, render: (value) => value === "clear" ? "恢复" : "保存" },
          { title: "执行人", dataIndex: "actor_id", ellipsis: true },
          { title: "变更", width: 260, render: (_value, row) => `${row.before_value || "-"} → ${row.after_value || "-"}` },
          { title: "时间", dataIndex: "created_at", width: 180, render: (value) => new Date(Number(value) * 1000).toLocaleString() },
        ]} />
      </Card>
    </PageContainer>
  );
}
