import { App, Button, Form, Input, Modal, Space, Tag, Typography } from "antd";
import { PlusOutlined, ProjectOutlined } from "@ant-design/icons";
import { PageContainer, ProTable } from "@ant-design/pro-components";
import type { ProColumns } from "@ant-design/pro-components";
import { useEffect, useState } from "react";
import { consoleApi } from "../api";
import { navigate } from "../router";
import { formatEpoch } from "../format";
import type { Project } from "../types";

export default function ProjectsPage() {
  const { message } = App.useApp();
  const [items, setItems] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm<{ name: string; instruction: string }>();

  async function load() {
    setLoading(true);
    try { setItems((await consoleApi.projects()).projects || []); }
    catch (reason) { message.error(reason instanceof Error ? reason.message : "项目加载失败"); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, []);

  const columns: ProColumns<Project>[] = [
    { title: "项目", dataIndex: "name", render: (_value, item) => <Space><ProjectOutlined /><Typography.Text strong>{item.name}</Typography.Text></Space> },
    { title: "说明", dataIndex: "instruction", ellipsis: true, render: (value) => value || <Typography.Text type="secondary">未设置项目指令</Typography.Text> },
    { title: "角色", dataIndex: "role", width: 100, render: (value) => <Tag color={value === "Owner" ? "green" : value === "Viewer" ? "default" : "blue"}>{String(value)}</Tag> },
    { title: "更新时间", dataIndex: "updated_at", width: 170, render: (value) => formatEpoch(Number(value)) },
    { title: "操作", valueType: "option", width: 90, render: (_value, item) => <Button type="link" onClick={() => navigate(`/projects/${item.id}`)}>打开</Button> },
  ];

  return (
    <PageContainer title="项目" subTitle="你拥有或参与的项目" extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>新建项目</Button>} header={{ breadcrumb: { items: [{ title: "工作区" }, { title: "项目" }] } }}>
      <ProTable<Project> rowKey="id" columns={columns} dataSource={items} loading={loading} search={false} pagination={{ pageSize: 12 }} options={{ reload: () => void load(), density: true }} />
      <Modal title="新建项目" open={open} confirmLoading={saving} okText="创建" cancelText="取消" onCancel={() => setOpen(false)} onOk={() => form.submit()} destroyOnHidden>
        <Form form={form} layout="vertical" onFinish={async (values) => {
          setSaving(true);
          try { const project = await consoleApi.createProject(values); message.success("项目已创建"); setOpen(false); form.resetFields(); navigate(`/projects/${project.id}`); }
          catch (reason) { message.error(reason instanceof Error ? reason.message : "创建失败"); }
          finally { setSaving(false); }
        }}>
          <Form.Item name="name" label="项目名称" rules={[{ required: true, whitespace: true, message: "请输入项目名称" }]}><Input autoFocus maxLength={120} /></Form.Item>
          <Form.Item name="instruction" label="项目指令"><Input.TextArea rows={5} placeholder="可选：说明项目目标和执行约束" /></Form.Item>
        </Form>
      </Modal>
    </PageContainer>
  );
}
