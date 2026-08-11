import { App, Button, Drawer, Form, Input, Modal, Select, Space, Tag, Typography } from "antd";
import { CompatList as List } from "../components/CompatList";
import { PlusOutlined, TeamOutlined, UserAddOutlined } from "@ant-design/icons";
import { PageContainer, ProTable } from "@ant-design/pro-components";
import type { ProColumns } from "@ant-design/pro-components";
import { useEffect, useState } from "react";
import { consoleApi } from "../api";
import { formatEpoch } from "../format";
import type { Member, Organization } from "../types";

export default function OrganizationsPage() {
  const { message } = App.useApp();
  const [items, setItems] = useState<Organization[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [selected, setSelected] = useState<Organization | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [form] = Form.useForm<{ name: string }>();
  const [memberForm] = Form.useForm<{ name: string; role: string }>();

  async function load() { setLoading(true); try { setItems((await consoleApi.organizations()).orgs || []); } catch (reason) { message.error(reason instanceof Error ? reason.message : "组织加载失败"); } finally { setLoading(false); } }
  async function loadMembers(id: string) { try { setMembers((await consoleApi.organizationMembers(id)).members || []); } catch (reason) { message.error(reason instanceof Error ? reason.message : "成员加载失败"); } }
  useEffect(() => { void load(); }, []);

  const columns: ProColumns<Organization>[] = [
    { title: "组织", dataIndex: "name", render: (_value, item) => <Space><TeamOutlined /><Typography.Text strong>{item.name}</Typography.Text></Space> },
    { title: "我的角色", dataIndex: "role", width: 120, render: (value) => <Tag color={value === "Owner" ? "green" : "blue"}>{String(value)}</Tag> },
    { title: "创建时间", dataIndex: "created_at", width: 180, render: (value) => formatEpoch(Number(value)) },
    { title: "操作", valueType: "option", width: 110, render: (_value, item) => <Button type="link" onClick={() => { setSelected(item); void loadMembers(item.id); }}>成员管理</Button> },
  ];

  return (
    <PageContainer title="组织与成员" subTitle="管理团队边界与组织级角色" extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>新建组织</Button>} header={{ breadcrumb: { items: [{ title: "工作区" }, { title: "组织与成员" }] } }}>
      <ProTable<Organization> rowKey="id" columns={columns} dataSource={items} loading={loading} search={false} options={{ reload: () => void load(), density: true }} />
      <Modal title="新建组织" open={createOpen} okText="创建" cancelText="取消" onCancel={() => setCreateOpen(false)} onOk={() => form.submit()} destroyOnHidden>
        <Form form={form} layout="vertical" onFinish={async ({ name }) => { try { await consoleApi.createOrganization(name); message.success("组织已创建"); setCreateOpen(false); form.resetFields(); await load(); } catch (reason) { message.error(reason instanceof Error ? reason.message : "创建失败"); } }}>
          <Form.Item name="name" label="组织名称" rules={[{ required: true, whitespace: true }]}><Input autoFocus maxLength={120} /></Form.Item>
        </Form>
      </Modal>
      <Drawer size={560} open={Boolean(selected)} title={selected ? `${selected.name} · 成员` : "成员"} onClose={() => setSelected(null)} destroyOnHidden>
        <List dataSource={members} locale={{ emptyText: "还没有成员" }} renderItem={(member) => <List.Item><List.Item.Meta title={member.name} description={member.email} /><Tag>{member.role}</Tag></List.Item>} />
        {selected && ["Owner", "Admin"].includes(selected.role) && (
          <Form form={memberForm} layout="vertical" className="drawer-form" initialValues={{ role: "Member" }} onFinish={async ({ name, role }) => { try { await consoleApi.addOrganizationMember(selected.id, name, role); message.success("成员已加入"); memberForm.resetFields(); await loadMembers(selected.id); } catch (reason) { message.error(reason instanceof Error ? reason.message : "加入失败"); } }}>
            <Typography.Title level={5}><UserAddOutlined /> 添加成员</Typography.Title>
            <Form.Item name="name" label="账号名" rules={[{ required: true, whitespace: true }]}><Input /></Form.Item>
            <Form.Item name="role" label="角色"><Select options={["Admin", "Member", "Viewer"].map((value) => ({ value, label: value }))} /></Form.Item>
            <Button type="primary" htmlType="submit">加入组织</Button>
          </Form>
        )}
      </Drawer>
    </PageContainer>
  );
}
