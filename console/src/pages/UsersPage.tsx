import { App, Button, Drawer, Form, Input, Popconfirm, Space, Switch, Tag, Typography } from "antd";
import { DeleteOutlined, EditOutlined, KeyOutlined, PlusOutlined, UserOutlined } from "@ant-design/icons";
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
  const [form] = Form.useForm<AccountForm>();
  const [passwordForm] = Form.useForm<{ password: string }>();

  async function load() { setLoading(true); try { setItems((await consoleApi.accounts()).accounts || []); } catch (reason) { message.error(reason instanceof Error ? reason.message : "用户加载失败"); } finally { setLoading(false); } }
  useEffect(() => { void load(); }, []);

  const columns: ProColumns<Account>[] = [
    { title: "用户", dataIndex: "name", render: (_value, item) => <Space><UserOutlined /><div><Typography.Text strong>{item.name}</Typography.Text><div><Typography.Text type="secondary">{item.email || "未设置邮箱"}</Typography.Text></div></div></Space> },
    { title: "套餐", dataIndex: "plan", width: 120, render: (value) => <Tag>{String(value || "体验版")}</Tag> },
    { title: "权限", dataIndex: "is_platform_admin", width: 130, render: (_value, item) => item.is_platform_admin ? <Tag color="blue">平台管理员</Tag> : <Tag>普通用户</Tag> },
    { title: "创建时间", dataIndex: "created_at", width: 170, render: (value) => formatEpoch(Number(value)) },
    { title: "操作", valueType: "option", width: 190, render: (_value, item) => <Space size={2}>
      <Button type="link" size="small" icon={<EditOutlined />} onClick={() => { setEditing(item); form.setFieldsValue({ name: item.name, email: item.email || "", plan: item.plan || "体验版", is_platform_admin: item.is_platform_admin }); }}>编辑</Button>
      <Button type="link" size="small" icon={<KeyOutlined />} onClick={() => setPasswordFor(item)}>密码</Button>
      <Popconfirm title="删除此账号？" description="仍拥有项目的账号无法删除。" disabled={item.id === current.id} onConfirm={async () => { try { await consoleApi.deleteAccount(item.id); message.success("账号已删除"); await load(); } catch (reason) { message.error(reason instanceof Error ? reason.message : "删除失败"); } }}><Button danger type="link" size="small" disabled={item.id === current.id} icon={<DeleteOutlined />}>删除</Button></Popconfirm>
    </Space> },
  ];

  return (
    <PageContainer title="用户" subTitle="平台账号、套餐与管理员权限" extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); form.resetFields(); form.setFieldsValue({ plan: "体验版", is_platform_admin: false }); }}>新建用户</Button>} header={{ breadcrumb: { items: [{ title: "系统" }, { title: "用户" }] } }}>
      <ProTable<Account> rowKey="id" columns={columns} dataSource={items} loading={loading} search={false} options={{ reload: () => void load(), density: true }} />
      <Drawer width={520} open={editing !== undefined} title={editing ? `编辑 ${editing.name}` : "新建用户"} onClose={() => setEditing(undefined)} destroyOnHidden extra={<Button type="primary" onClick={() => form.submit()}>保存</Button>}>
        <Form form={form} layout="vertical" onFinish={async (values) => { try { if (editing) await consoleApi.updateAccount(editing.id, values); else await consoleApi.createAccount({ ...values, password: values.password || "" }); message.success(editing ? "用户已更新" : "用户已创建"); setEditing(undefined); await load(); } catch (reason) { message.error(reason instanceof Error ? reason.message : "保存失败"); } }}>
          <Form.Item name="name" label="用户名" rules={[{ required: true, whitespace: true }]}><Input maxLength={60} /></Form.Item>
          <Form.Item name="email" label="邮箱"><Input type="email" maxLength={120} /></Form.Item>
          <Form.Item name="plan" label="套餐"><Input maxLength={40} /></Form.Item>
          {!editing && <Form.Item name="password" label="初始密码" rules={[{ required: true, min: 4 }]}><Input.Password /></Form.Item>}
          <Form.Item name="is_platform_admin" label="平台管理员" valuePropName="checked"><Switch /></Form.Item>
        </Form>
      </Drawer>
      <Drawer width={420} open={Boolean(passwordFor)} title={passwordFor ? `重置 ${passwordFor.name} 的密码` : "重置密码"} onClose={() => setPasswordFor(null)} destroyOnHidden extra={<Button type="primary" onClick={() => passwordForm.submit()}>重置</Button>}>
        <Form form={passwordForm} layout="vertical" onFinish={async ({ password }) => { if (!passwordFor) return; try { await consoleApi.resetPassword(passwordFor.id, password); message.success("密码已重置"); setPasswordFor(null); passwordForm.resetFields(); } catch (reason) { message.error(reason instanceof Error ? reason.message : "重置失败"); } }}><Form.Item name="password" label="新密码" rules={[{ required: true, min: 4 }]}><Input.Password autoFocus /></Form.Item></Form>
      </Drawer>
    </PageContainer>
  );
}
