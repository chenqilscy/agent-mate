import {
  Alert, App, Avatar, Button, Card, Col, Descriptions, Drawer, Empty, Form, Input,
  Modal, Popconfirm, Row, Select, Space, Tabs, Tag,
  Timeline, Typography, Upload,
} from "antd";
import { CompatList as List } from "../components/CompatList";
import { IconPicker } from "../../../src/components/ui/IconPicker";
import {
  ArrowLeftOutlined, CloudUploadOutlined, FileTextOutlined,
  PlusOutlined, ProjectOutlined, TeamOutlined,
} from "@ant-design/icons";
import { PageContainer, ProTable } from "@ant-design/pro-components";
import type { ProColumns } from "@ant-design/pro-components";
import { useEffect, useState } from "react";
import { consoleApi } from "../api";
import {
  ProjectGantt, ProjectIterations, ProjectOverview, ProjectPlan, ProjectTasks, ProjectWorkload,
  ProjectWorkProvider,
} from "../components/project/ProjectWorkspace";
import { navigate } from "../router";
import type {
  CatalogData, CatalogItem, CommentRecord, KnowledgeBase, KnowledgeDocument,
  Member, Project, TimelineEvent,
} from "../types";

const ROLE_OPTIONS = ["Admin", "Member", "Viewer"].map((value) => ({ value, label: value }));
function errorText(reason: unknown, fallback: string): string { return reason instanceof Error ? reason.message : fallback; }
function canWrite(project: Project): boolean { return project.role !== "Viewer"; }
function canManage(project: Project): boolean { return project.role === "Owner" || project.role === "Admin"; }

export default function ProjectDetailPage({ projectId }: { projectId: string }) {
  const { message } = App.useApp();
  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("overview");
  async function load() { setLoading(true); try { setProject(await consoleApi.project(projectId)); } catch (reason) { message.error(errorText(reason, "项目加载失败")); } finally { setLoading(false); } }
  useEffect(() => { void load(); }, [projectId]);
  return (
    <PageContainer
      title={project?.name || "项目"}
      subTitle={project?.instruction || "未设置项目指令"}
      loading={loading}
      tags={project ? <Tag color={project.role === "Viewer" ? "default" : "green"}>{project.role}{project.role === "Viewer" ? " · 只读" : ""}</Tag> : undefined}
      extra={<Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/projects")}>返回项目</Button>}
      header={{ breadcrumb: { items: [{ title: "工作区" }, { title: "项目", onClick: () => navigate("/projects") }, { title: project?.name || projectId }] } }}
    >
      {project ? <ProjectWorkProvider project={project}>
        <Card className="project-hero">
          <Space size={16}>
            <Avatar shape="square" size={52} icon={<ProjectOutlined />} />
            <div><Typography.Title level={4}>{project.name}</Typography.Title><Typography.Text type="secondary">{project.instruction || "未设置项目指令"}</Typography.Text></div>
          </Space>
        </Card>
        <Tabs
          className="project-workspace-tabs"
          activeKey={tab}
          onChange={setTab}
          items={[
            { key: "overview", label: "概览", children: <ProjectOverview /> },
            { key: "plan", label: "计划", children: <ProjectPlan /> },
            { key: "tasks", label: "任务", children: <ProjectTasks /> },
            { key: "workload", label: "负载", children: <ProjectWorkload /> },
            { key: "gantt", label: "甘特", children: <ProjectGantt /> },
            { key: "iterations", label: "周期与字段", children: <ProjectIterations /> },
            { key: "knowledge", label: "知识库", children: <KnowledgeTab project={project} /> },
            { key: "collab", label: "协作", children: <CollaborationTab project={project} /> },
            { key: "config", label: "配置", children: <ConfigTab project={project} onSaved={load} /> },
          ]}
        />
      </ProjectWorkProvider> : !loading && <Empty description="项目不存在或无权访问" />}
    </PageContainer>
  );
}

function KnowledgeTab({ project }: { project: Project }) {
  const { message } = App.useApp();
  const [items, setItems] = useState<KnowledgeBase[]>([]);
  const [loading, setLoading] = useState(true);
  const [configured, setConfigured] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [selected, setSelected] = useState<KnowledgeBase | null>(null);
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [form] = Form.useForm<Partial<KnowledgeBase> & { name: string }>();
  async function load() { setLoading(true); try { const result = await consoleApi.knowledgeBases(project.id); setItems(result.items || []); setConfigured(result.configured); } catch (reason) { message.error(errorText(reason, "知识库加载失败")); } finally { setLoading(false); } }
  async function loadDocs(kb: KnowledgeBase) { setSelected(kb); try { setDocuments((await consoleApi.knowledgeDocuments(project.id, kb.id)).items || []); } catch (reason) { message.error(errorText(reason, "文档加载失败")); } }
  useEffect(() => { void load(); }, [project.id]);
  const columns: ProColumns<KnowledgeBase>[] = [
    { title: "知识库", dataIndex: "name", render: (_value, item) => <Space><Avatar shape="square">{item.icon || "📚"}</Avatar><div><Typography.Text strong>{item.name}</Typography.Text><div><Typography.Text type="secondary">{item.description || "暂无简介"}</Typography.Text></div></div></Space> },
    { title: "状态", width: 140, render: (_value, item) => item.provider_status === "ready" ? <Tag color="green">WeKnora 已就绪</Tag> : item.provider_status === "legacy_pending" ? <Tag color="orange">旧库待迁移</Tag> : item.provider_status === "migrating" ? <Tag color="processing">迁移中</Tag> : <Tag color="red">暂不可用</Tag> },
    { title: "文档", dataIndex: "doc_count", width: 80 },
    { title: "操作", valueType: "option", width: 220, render: (_value, item) => <Space><Button type="link" size="small" onClick={() => void loadDocs(item)}>打开</Button>{canManage(project) && item.provider_status === "legacy_pending" && <Button type="link" size="small" onClick={async () => { try { await consoleApi.migrateKnowledgeBase(project.id, item.id); message.success("旧知识库已提交到中央 WeKnora"); await load(); } catch (reason) { message.error(errorText(reason, "迁移失败")); } }}>迁移</Button>}{canManage(project) && <Popconfirm title={`删除知识库“${item.name}”及全部文档？`} onConfirm={async () => { try { await consoleApi.deleteKnowledgeBase(project.id, item.id); message.success("知识库已删除"); await load(); } catch (reason) { message.error(errorText(reason, "删除失败")); } }}><Button type="link" danger size="small">删除</Button></Popconfirm>}</Space> },
  ];
  return <>
    {!configured && <Alert type="warning" showIcon message="中央 WeKnora 尚未配置" description="请让平台管理员在 AgentMate Server 部署环境配置 WeKnora 服务凭据；密钥不会下发到 Console 或 AgentMate。" />}
    <ProTable<KnowledgeBase> rowKey="id" columns={columns} dataSource={items} loading={loading} search={false} options={{ reload: () => void load(), density: true }} toolBarRender={() => canManage(project) ? [<Button key="new" type="primary" disabled={!configured} icon={<PlusOutlined />} onClick={() => { form.setFieldsValue({ icon: "📚" }); setCreateOpen(true); }}>新建知识库</Button>] : []} />
    <Modal title="新建中央知识库" open={createOpen} onCancel={() => setCreateOpen(false)} onOk={() => form.submit()} destroyOnHidden><Form form={form} layout="vertical" onFinish={async (values) => { try { await consoleApi.createKnowledgeBase(project.id, values); message.success("知识库已在 WeKnora 创建"); setCreateOpen(false); form.resetFields(); await load(); } catch (reason) { message.error(errorText(reason, "创建失败")); } }}><Row gutter={12}><Col span={6}><Form.Item name="icon" label="图标"><IconPicker ariaLabel="选择知识库图标" /></Form.Item></Col><Col span={18}><Form.Item name="name" label="名称" rules={[{ required: true, whitespace: true }]}><Input /></Form.Item></Col></Row><Form.Item name="description" label="用途简介"><Input.TextArea rows={3} /></Form.Item><Alert type="info" showIcon message="解析、切片、嵌入与检索均由中央 WeKnora 完成，项目成员无需再配置 API Key。" /></Form></Modal>
    <Drawer width={680} open={Boolean(selected)} title={selected ? `${selected.icon || "📚"} ${selected.name}` : "知识库"} onClose={() => setSelected(null)} destroyOnHidden>
      {selected && <><Descriptions column={1} bordered size="small" items={[{ key: "desc", label: "用途", children: selected.description || "-" }, { key: "provider", label: "知识服务", children: selected.provider_status === "ready" ? "中央 WeKnora（已就绪）" : selected.provider_error || "旧库待迁移" }, { key: "boundary", label: "凭据边界", children: "WeKnora API Key 仅保存在 AgentMate Server" }]} /><Card className="drawer-card" title="文档" extra={canWrite(project) && selected.provider_status === "ready" && <Upload showUploadList={false} beforeUpload={(file) => { void (async () => { try { await consoleApi.uploadKnowledgeDocument(project.id, selected.id, file); message.success("文档已上传，WeKnora 正在解析"); await loadDocs(selected); await load(); } catch (reason) { message.error(errorText(reason, "上传失败")); } })(); return false; }}><Button icon={<CloudUploadOutlined />}>上传文档</Button></Upload>}><List dataSource={documents} locale={{ emptyText: "还没有文档" }} renderItem={(doc) => <List.Item actions={canWrite(project) ? [<Popconfirm key="delete" title="删除此文档？" onConfirm={async () => { await consoleApi.deleteKnowledgeDocument(project.id, selected.id, doc.id); await loadDocs(selected); await load(); }}><Button danger type="link" size="small">删除</Button></Popconfirm>] : []}><List.Item.Meta avatar={<FileTextOutlined />} title={doc.filename} description={`${doc.size ? `${(doc.size / 1024).toFixed(1)} KB · ` : ""}${doc.vector_status === 1 ? "解析完成" : doc.vector_status === 2 ? `失败：${doc.fail_msg || "未知"}` : doc.parse_status === "legacy_pending" ? "旧文档待迁移" : "解析中"}`} /></List.Item>} /></Card></>}
    </Drawer>
  </>;
}

function CollaborationTab({ project }: { project: Project }) {
  const { message } = App.useApp();
  const [members, setMembers] = useState<Member[]>([]);
  const [presence, setPresence] = useState<Member[]>([]);
  const [comments, setComments] = useState<CommentRecord[]>([]);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [inviteCode, setInviteCode] = useState("");
  const [inviteRole, setInviteRole] = useState("Member");
  const [memberForm] = Form.useForm<{ name: string; role: string }>();
  const [commentForm] = Form.useForm<{ body: string }>();
  async function load() { try { const [memberResult, presenceResult, commentResult, timelineResult] = await Promise.all([consoleApi.projectMembers(project.id), consoleApi.presence(project.id), consoleApi.comments(project.id), consoleApi.timeline(project.id)]); setMembers(memberResult.members || []); setPresence(presenceResult.presence || []); setComments(commentResult.comments || []); setTimeline(timelineResult.events || []); } catch (reason) { message.error(errorText(reason, "协作数据加载失败")); } }
  useEffect(() => { void load(); }, [project.id]);
  return <Row gutter={[16, 16]}><Col xs={24} xl={11}><Card title="成员" extra={<Tag icon={<TeamOutlined />}>{members.length}</Tag>}><List dataSource={members} locale={{ emptyText: "还没有成员" }} renderItem={(member) => <List.Item actions={canManage(project) && member.role !== "Owner" ? [<Select key="role" size="small" value={member.role} options={ROLE_OPTIONS} onChange={async (role) => { await consoleApi.updateProjectMember(project.id, member.account_id, role); await load(); }} />, <Popconfirm key="remove" title="移除此成员？" onConfirm={async () => { await consoleApi.removeProjectMember(project.id, member.account_id); await load(); }}><Button type="link" danger size="small">移除</Button></Popconfirm>] : []}><List.Item.Meta avatar={<Avatar>{member.name.slice(0, 1)}</Avatar>} title={member.name} description={member.email} /><Tag>{member.role}</Tag></List.Item>} />{canManage(project) && <Form form={memberForm} layout="inline" className="inline-form" initialValues={{ role: "Member" }} onFinish={async ({ name, role }) => { try { await consoleApi.addProjectMember(project.id, name, role); message.success("成员已加入"); memberForm.resetFields(); await load(); } catch (reason) { message.error(errorText(reason, "加入失败")); } }}><Form.Item name="name" rules={[{ required: true }]}><Input placeholder="账号名" /></Form.Item><Form.Item name="role"><Select options={ROLE_OPTIONS} /></Form.Item><Button type="primary" htmlType="submit">加入</Button></Form>}</Card><Card title="邀请码" className="section-card">{canManage(project) ? <Space direction="vertical" className="full-width"><Space><Select value={inviteRole} options={ROLE_OPTIONS} id="invite-role" onChange={setInviteRole} /><Button onClick={async () => { try { setInviteCode((await consoleApi.inviteProjectMember(project.id, inviteRole)).code); } catch (reason) { message.error(errorText(reason, "生成失败")); } }}>生成邀请码</Button></Space>{inviteCode && <Typography.Text code copyable>{inviteCode}</Typography.Text>}</Space> : <Typography.Text type="secondary">需要 Admin/Owner 权限</Typography.Text>}</Card><Card title="在线状态" className="section-card"><Space wrap>{presence.length ? presence.map((item) => <Tag color="green" key={item.account_id}>{item.name}</Tag>) : <Typography.Text type="secondary">暂无在线成员</Typography.Text>}</Space></Card></Col><Col xs={24} xl={13}><Card title="讨论"><List dataSource={comments} locale={{ emptyText: "暂无评论" }} renderItem={(comment) => <List.Item><List.Item.Meta avatar={<Avatar>{(comment.author_name || comment.account_name || "?").slice(0, 1)}</Avatar>} title={comment.author_name || comment.account_name || "成员"} description={<><Typography.Paragraph>{comment.body}</Typography.Paragraph><Typography.Text type="secondary">{comment.created_at ? new Date(comment.created_at * 1000).toLocaleString() : ""}</Typography.Text></>} /></List.Item>} /><Form form={commentForm} layout="vertical" onFinish={async ({ body }) => { try { await consoleApi.createComment(project.id, body); commentForm.resetFields(); await load(); } catch (reason) { message.error(errorText(reason, "发送失败")); } }}><Form.Item name="body" rules={[{ required: true, whitespace: true }]}><Input.TextArea rows={3} placeholder="写评论…可 @用户名 提及成员" /></Form.Item><Button type="primary" htmlType="submit">发送</Button></Form></Card><Card title="团队时间线" className="section-card">{timeline.length ? <Timeline items={timeline.map((event) => ({ children: <><Typography.Text strong>{event.actor_name || event.actor || "成员"}</Typography.Text> {event.title || event.summary || event.detail || event.kind}<div><Typography.Text type="secondary">{event.created_at ? new Date(event.created_at * 1000).toLocaleString() : ""}</Typography.Text></div></> }))} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无时间线事件" />}</Card></Col></Row>;
}

function ConfigTab({ project, onSaved }: { project: Project; onSaved: () => Promise<void> }) {
  const { message } = App.useApp();
  const [form] = Form.useForm<{ instruction: string; connectors: string[]; experts: string[]; skills: string[] }>();
  const [options, setOptions] = useState({ connectors: [] as { value: string; label: string }[], experts: [] as { value: string; label: string }[], skills: [] as { value: string; label: string }[] });
  useEffect(() => {
    form.setFieldsValue({ instruction: project.instruction || "", connectors: project.connectors || [], experts: project.experts || [], skills: project.skills || [] });
    Promise.all([consoleApi.catalog<CatalogData>("NP_CONNS"), consoleApi.catalog<CatalogData>("EXPERT_DEFS"), consoleApi.catalog<CatalogData>("APP_SKILLS")]).then(([connectors, experts, skills]) => {
      const map = (items: CatalogItem<CatalogData>[], stable = false) => items.map((item) => { const data = typeof item.data === "object" && item.data ? item.data : { value: item.data }; const label = String(data.name || data.title || data.slug || data.value || item.id); const value = stable ? String(data.slug || data.key || label) : label; return { value, label }; });
      setOptions({ connectors: map(connectors.items), experts: map(experts.items), skills: map(skills.items, true) });
    }).catch((reason) => message.error(errorText(reason, "目录选项加载失败")));
  }, [project.id]);
  return <Card title="项目能力配置"><Form form={form} layout="vertical" disabled={!canWrite(project)} onFinish={async (values) => { try { await consoleApi.updateProject(project.id, values); message.success("项目配置已保存"); await onSaved(); } catch (reason) { message.error(errorText(reason, "保存失败")); } }}><Form.Item name="instruction" label="项目指令"><Input.TextArea rows={6} /></Form.Item><Form.Item name="connectors" label="连接器"><Select mode="multiple" options={options.connectors} placeholder="选择连接器" /></Form.Item><Form.Item name="experts" label="专家"><Select mode="multiple" options={options.experts} placeholder="选择专家" /></Form.Item><Form.Item name="skills" label="技能"><Select mode="multiple" options={options.skills} placeholder="选择技能" /></Form.Item>{canWrite(project) && <Button type="primary" htmlType="submit">保存配置</Button>}</Form></Card>;
}
