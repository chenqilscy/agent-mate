import { App, Button, Card, Drawer, Form, Input, Popconfirm, Space, Switch, Table, Tag, Typography } from "antd";
import { DeleteOutlined, EditOutlined, KeyOutlined, LockOutlined, PlusOutlined, StopOutlined, UserOutlined } from "@ant-design/icons";
import { PageContainer, ProTable } from "@ant-design/pro-components";
import type { ProColumns } from "@ant-design/pro-components";
import { useEffect, useState } from "react";
import { consoleApi } from "../api";
import { formatEpoch } from "../format";
import type { Account } from "../types";

type AccountForm = { name: string; email: string; plan: string; password?: string; is_platform_admin: boolean };

export default function UsersPage({ current }: { current: Account }) {
  const { message } = App.useApp();
  const [items, setItems] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<Account | null | undefined>(undefined);
  const [passwordFor, setPasswordFor] = useState<Account | null>(null);
  const [audit, setAudit] = useState<Array<{ id: string; account_id: string; actor_id: string; action: string; created_at: number }>>([]);
  const [form] = Form.useForm<AccountForm>();
  const [passwordForm] = Form.useForm<{ password: string }>();

  async function load() { setLoading(true); try { const [accounts, authAudit] = await Promise.all([consoleApi.accounts(), consoleApi.authAudit()]); setItems(accounts.accounts || []); setAudit(authAudit.audit || []); } catch (reason) { message.error(reason instanceof Error ? reason.message : "用户加载失败"); } finally { setLoading(false); } }
  useEffect(() => { void load(); }, []);

  const columns: ProColumns<Account>[] = [
    { title: "用户", dataIndex: "name", render: (_value, item) => <Space><UserOutlined /><div><Typography.Text strong>{item.name}</Typography.Text><div><Typography.Text type="secondary">{item.email || "未设置邮箱"}</Typography.Text></div></div></Space> },
    { title: "套餐", dataIndex: "plan", width: 120, render: (value) => <Tag>{String(value || "体验版")}</Tag> },
    { title: "状态", width: 190, render: (_value, item) => <Space wrap><Tag color={item.suspended_at ? "red" : "green"}>{item.suspended_at ? "已暂停" : "正常"}</Tag>{item.is_platform_admin ? <Tag color="blue">平台管理员</Tag> : <Tag>普通用户</Tag>}<Tag color={item.password_login_enabled ? "cyan" : "default"}>{item.password_login_enabled ? "密码登录" : "SSO 登录"}</Tag></Space> },
    { title: "登录方式", width: 180, render: (_value, item) => <Space wrap>{(item.identities || []).map((identity) => <Popconfirm key={identity.provider} title={`解绑 ${identity.provider}？`} description="解绑会撤销该用户的全部现有会话；最后一种登录方式不能解绑。" onConfirm={async () => { try { await consoleApi.unlinkAccountIdentity(item.id, identity.provider); message.success("联合身份已解绑"); await load(); } catch (reason) { message.error(reason instanceof Error ? reason.message : "解绑失败"); } }}><Tag closable onClose={(event) => event.preventDefault()}>{identity.provider}</Tag></Popconfirm>)}{!(item.identities || []).length && <Typography.Text type="secondary">无联合身份</Typography.Text>}</Space> },
    { title: "会话", dataIndex: "active_sessions", width: 90, render: (value) => `${Number(value || 0)} 个` },
    { title: "创建时间", dataIndex: "created_at", width: 170, render: (value) => formatEpoch(Number(value)) },
    { title: "操作", valueType: "option", width: 330, render: (_value, item) => <Space size={2} wrap>
      <Button type="link" size="small" icon={<EditOutlined />} onClick={() => { setEditing(item); form.setFieldsValue({ name: item.name, email: item.email || "", plan: item.plan || "体验版", is_platform_admin: item.is_platform_admin }); }}>编辑</Button>
      <Button type="link" size="small" icon={<KeyOutlined />} onClick={() => setPasswordFor(item)}>密码</Button>
      <Popconfirm title="撤销此账号的全部登录会话？" onConfirm={async () => { try { const result = await consoleApi.revokeAccountSessions(item.id); message.success(`已撤销 ${result.revoked} 个会话`); await load(); } catch (reason) { message.error(reason instanceof Error ? reason.message : "撤销失败"); } }}><Button type="link" size="small" icon={<LockOutlined />}>会话</Button></Popconfirm>
      <Popconfirm title={item.password_login_enabled ? "禁用密码登录？" : "启用密码登录？"} description={item.password_login_enabled ? "至少保留一个联合身份；操作会撤销现有会话。" : "启用后仍应重置为已知强密码。"} onConfirm={async () => { try { await consoleApi.setPasswordLogin(item.id, !item.password_login_enabled); message.success("登录方式已更新"); await load(); } catch (reason) { message.error(reason instanceof Error ? reason.message : "更新失败"); } }}><Button type="link" size="small">{item.password_login_enabled ? "禁用密码" : "启用密码"}</Button></Popconfirm>
      <Popconfirm title={item.suspended_at ? "恢复此账号？" : "暂停此账号？"} description={item.suspended_at ? "恢复后需要重新登录，已撤销的 Service Token 不会恢复。" : "将立即撤销全部会话和 Service Token。"} disabled={item.id === current.id} onConfirm={async () => { try { await consoleApi.setAccountSuspended(item.id, !item.suspended_at); message.success(item.suspended_at ? "账号已恢复" : "账号已暂停"); await load(); } catch (reason) { message.error(reason instanceof Error ? reason.message : "操作失败"); } }}><Button danger={!item.suspended_at} type="link" size="small" disabled={item.id === current.id} icon={<StopOutlined />}>{item.suspended_at ? "恢复" : "暂停"}</Button></Popconfirm>
      <Popconfirm title="删除此账号？" description="仍拥有项目的账号无法删除。" disabled={item.id === current.id} onConfirm={async () => { try { await consoleApi.deleteAccount(item.id); message.success("账号已删除"); await load(); } catch (reason) { message.error(reason instanceof Error ? reason.message : "删除失败"); } }}><Button danger type="link" size="small" disabled={item.id === current.id} icon={<DeleteOutlined />}>删除</Button></Popconfirm>
    </Space> },
  ];

  return (
    <PageContainer title="用户" subTitle="平台账号、套餐与管理员权限" extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); form.resetFields(); form.setFieldsValue({ plan: "体验版", is_platform_admin: false }); }}>新建用户</Button>} header={{ breadcrumb: { items: [{ title: "系统" }, { title: "用户" }] } }}>
      <ProTable<Account> rowKey="id" columns={columns} dataSource={items} loading={loading} search={false} scroll={{ x: 1500 }} options={{ reload: () => void load(), density: true }} />
      <Drawer size={520} open={editing !== undefined} title={editing ? `编辑 ${editing.name}` : "新建用户"} onClose={() => setEditing(undefined)} destroyOnHidden extra={<Button type="primary" onClick={() => form.submit()}>保存</Button>}>
        <Form form={form} layout="vertical" onFinish={async (values) => { try { if (editing) await consoleApi.updateAccount(editing.id, values); else await consoleApi.createAccount({ ...values, password: values.password || "" }); message.success(editing ? "用户已更新" : "用户已创建"); setEditing(undefined); await load(); } catch (reason) { message.error(reason instanceof Error ? reason.message : "保存失败"); } }}>
          <Form.Item name="name" label="用户名" rules={[{ required: true, whitespace: true }]}><Input maxLength={60} /></Form.Item>
          <Form.Item name="email" label="邮箱"><Input type="email" maxLength={120} /></Form.Item>
          <Form.Item name="plan" label="套餐"><Input maxLength={40} /></Form.Item>
          {!editing && <Form.Item name="password" label="初始密码" extra="至少 12 位；本地历史测试账号不受影响。" rules={[{ required: true, min: 12 }]}><Input.Password /></Form.Item>}
          <Form.Item name="is_platform_admin" label="平台管理员" valuePropName="checked"><Switch /></Form.Item>
        </Form>
      </Drawer>
      <Drawer size={420} open={Boolean(passwordFor)} title={passwordFor ? `重置 ${passwordFor.name} 的密码` : "重置密码"} onClose={() => setPasswordFor(null)} destroyOnHidden extra={<Button type="primary" onClick={() => passwordForm.submit()}>重置</Button>}>
        <Form form={passwordForm} layout="vertical" onFinish={async ({ password }) => { if (!passwordFor) return; try { await consoleApi.resetPassword(passwordFor.id, password); message.success("密码已设置、密码登录已启用，现有会话已撤销"); setPasswordFor(null); passwordForm.resetFields(); await load(); } catch (reason) { message.error(reason instanceof Error ? reason.message : "重置失败"); } }}><Form.Item name="password" label="新密码" extra="至少 12 位；设置后会启用密码登录并撤销现有会话。" rules={[{ required: true, min: 12 }]}><Input.Password autoFocus /></Form.Item></Form>
      </Drawer>
      <Card title="认证操作审计" style={{ marginTop: 16 }}>
        <Table rowKey="id" size="small" pagination={{ pageSize: 10 }} dataSource={audit} columns={[{ title: "动作", dataIndex: "action" }, { title: "目标账号", dataIndex: "account_id", ellipsis: true }, { title: "执行人", dataIndex: "actor_id", ellipsis: true }, { title: "时间", dataIndex: "created_at", width: 180, render: (value) => formatEpoch(Number(value)) }]} />
      </Card>
    </PageContainer>
  );
}
