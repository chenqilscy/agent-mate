import {
  Alert, App, Button, Card, Descriptions, Form, Input, InputNumber, Popconfirm,
  Space, Switch, Table, Tag, Typography,
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

type SsoProviderConfig = {
  id: string;
  label: string;
  enabled: boolean;
  client_id: string;
  client_secret?: string;
  secret_configured: boolean;
  updated_at: number;
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
  const { message, modal } = App.useApp();
  const [form] = Form.useForm<Draft>();
  const [data, setData] = useState<PlatformSettingsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [ssoProviders, setSsoProviders] = useState<SsoProviderConfig[]>([]);
  const [ssoSaving, setSsoSaving] = useState("");
  const [ssoAudit, setSsoAudit] = useState<Array<{ id: string; provider: string; actor_id: string; action: string; created_at: number }>>([]);
  const [ssoReadiness, setSsoReadiness] = useState<Awaited<ReturnType<typeof consoleApi.ssoReadiness>> | null>(null);

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
  useEffect(() => {
    void Promise.all([consoleApi.adminSsoProviders(), consoleApi.ssoProviderAudit(), consoleApi.ssoReadiness()])
      .then(([providers, audit, readiness]) => { setSsoProviders(providers.providers); setSsoAudit(audit.audit); setSsoReadiness(readiness); })
      .catch((reason) => message.error(errorText(reason)));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const patchSso = (id: string, patch: Partial<SsoProviderConfig>) => {
    setSsoProviders((items) => items.map((item) => item.id === id ? { ...item, ...patch } : item));
  };

  const saveSso = async (provider: SsoProviderConfig) => {
    setSsoSaving(provider.id);
    try {
      const body: { enabled: boolean; client_id: string; client_secret?: string } = {
        enabled: provider.enabled,
        client_id: provider.client_id,
      };
      if (provider.client_secret?.trim()) body.client_secret = provider.client_secret.trim();
      const result = await consoleApi.saveSsoProvider(provider.id, body);
      patchSso(provider.id, { ...result.provider, client_secret: "" });
      setSsoAudit((await consoleApi.ssoProviderAudit()).audit);
      setSsoReadiness(await consoleApi.ssoReadiness());
      message.success(`${provider.label} 登录配置已保存`);
    } catch (reason) {
      message.error(errorText(reason));
    } finally {
      setSsoSaving("");
    }
  };

  const createSsoInvite = async () => {
    try {
      const result = await consoleApi.createSsoSignupInvite();
      modal.info({
        title: "一次性 SSO 注册邀请码",
        content: <Typography.Text copyable code>{result.code}</Typography.Text>,
        okText: "已安全保存",
      });
    } catch (reason) {
      message.error(errorText(reason));
    }
  };

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
      <Alert type="info" showIcon title="设置作用域" description="这里的设置对整个平台生效。用户偏好、项目配置和助理渠道仍在各自入口管理；数据库、端口等启动参数不会出现在此处。" />
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
        <Card
          title="联合登录 · Google / 微信 / Telegram"
          style={{ marginTop: 16 }}
          extra={<Button onClick={() => void createSsoInvite()}>生成首次注册邀请码</Button>}
        >
          <Alert
            type="warning"
            showIcon
            title="先登记公开 HTTPS 回调，再启用入口"
            description="Client Secret 只写不回显并在 Server 数据库中加密；生产环境必须配置独立主密钥。未启用或凭据不完整的入口不会显示在 App/Console 登录页。"
            style={{ marginBottom: 16 }}
          />
          {ssoReadiness ? <Alert type={ssoReadiness.ready ? "success" : "warning"} showIcon title={ssoReadiness.ready ? "SSO 部署自检通过" : "SSO 仍有部署前置条件"} description={<Space direction="vertical"><Typography.Text>公开地址：{ssoReadiness.public_base_url} · 密钥保护：{ssoReadiness.secret_protection}</Typography.Text>{[...ssoReadiness.blockers, ...ssoReadiness.warnings].map((item) => <Typography.Text key={item} type="secondary">{item}</Typography.Text>)}</Space>} style={{ marginBottom: 16 }} /> : null}
          <Space direction="vertical" size={12} style={{ width: "100%" }}>
            {ssoProviders.map((provider) => (
              <Card key={provider.id} size="small">
                <Space direction="vertical" style={{ width: "100%" }}>
                  <Space>
                    <Switch checked={provider.enabled} onChange={(enabled) => patchSso(provider.id, { enabled })} />
                    <Typography.Text strong>{provider.label}</Typography.Text>
                    <Tag color={provider.secret_configured ? "green" : "default"}>
                      {provider.secret_configured ? "密钥已配置" : "密钥未配置"}
                    </Tag>
                  </Space>
                  <Input
                    value={provider.client_id}
                    onChange={(event) => patchSso(provider.id, { client_id: event.target.value })}
                    placeholder="Client ID / AppID / Bot ID"
                  />
                  <Input.Password
                    value={provider.client_secret || ""}
                    onChange={(event) => patchSso(provider.id, { client_secret: event.target.value })}
                    autoComplete="new-password"
                    placeholder="输入新 Client Secret 以替换"
                  />
                  <Button loading={ssoSaving === provider.id} onClick={() => void saveSso(provider)}>
                    保存 {provider.label}
                  </Button>
                  {ssoReadiness?.providers.find((item) => item.id === provider.id) ? <Typography.Text type="secondary">回调：{ssoReadiness.providers.find((item) => item.id === provider.id)?.callback_url}</Typography.Text> : null}
                </Space>
              </Card>
            ))}
          </Space>
          <Table rowKey="id" size="small" style={{ marginTop: 16 }} pagination={{ pageSize: 6 }} dataSource={ssoAudit} columns={[{ title: "Provider", dataIndex: "provider" }, { title: "动作", dataIndex: "action" }, { title: "执行人", dataIndex: "actor_id", ellipsis: true }, { title: "时间", dataIndex: "created_at", width: 180, render: (value) => new Date(Number(value) * 1000).toLocaleString() }]} />
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
