import {
  App, Avatar, Button, Card, Col, Descriptions, Drawer, Empty, Form, Input, InputNumber,
  Modal, Popconfirm, Progress, Row, Select, Space, Statistic, Switch, Tabs, Tag,
  Timeline, Typography, Upload,
} from "antd";
import { CompatList as List } from "../components/CompatList";
import {
  ArrowLeftOutlined, CloudUploadOutlined, DeleteOutlined, EditOutlined, FileTextOutlined,
  PlusOutlined, ProjectOutlined, TeamOutlined,
} from "@ant-design/icons";
import { PageContainer, ProTable } from "@ant-design/pro-components";
import type { ProColumns } from "@ant-design/pro-components";
import { useEffect, useMemo, useState } from "react";
import { consoleApi } from "../api";
import { navigate } from "../router";
import type {
  Activity, CatalogData, CatalogItem, CommentRecord, KnowledgeBase, KnowledgeDocument,
  Member, Milestone, Project, TimelineEvent, WorkItem,
} from "../types";

const ROLE_OPTIONS = ["Admin", "Member", "Viewer"].map((value) => ({ value, label: value }));
const STATUS_OPTIONS = [
  { value: "todo", label: "待办" }, { value: "doing", label: "进行中" },
  { value: "paused", label: "暂停" }, { value: "done", label: "完成" },
];
const PRIORITY_OPTIONS = [
  { value: "", label: "无" }, { value: "low", label: "低" }, { value: "medium", label: "中" },
  { value: "high", label: "高" }, { value: "urgent", label: "紧急" },
];
const PRIORITY_COLORS: Record<string, string> = { low: "default", medium: "blue", high: "orange", urgent: "red" };

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
      {project ? <><Card className="project-hero"><Space size={16}><Avatar shape="square" size={52} icon={<ProjectOutlined />} /><div><Typography.Title level={4}>{project.name}</Typography.Title><Typography.Text type="secondary">{project.instruction || "未设置项目指令"}</Typography.Text></div></Space></Card><Tabs activeKey={tab} onChange={setTab} items={[{ key: "overview", label: "概览", children: <ProjectOverview project={project} /> }, { key: "tasks", label: "任务", children: <TasksTab project={project} /> }, { key: "knowledge", label: "知识库", children: <KnowledgeTab project={project} /> }, { key: "collab", label: "协作", children: <CollaborationTab project={project} /> }, { key: "config", label: "配置", children: <ConfigTab project={project} onSaved={load} /> }]} /></> : !loading && <Empty description="项目不存在或无权访问" />}
    </PageContainer>
  );
}

function ProjectOverview({ project }: { project: Project }) {
  const { message } = App.useApp();
  const [items, setItems] = useState<WorkItem[]>([]);
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(true);
  const [milestoneOpen, setMilestoneOpen] = useState(false);
  const [form] = Form.useForm<{ name: string; due_date: string }>();
  async function load() { setLoading(true); try { const [work, miles, acts] = await Promise.all([consoleApi.workItems(project.id), consoleApi.milestones(project.id), consoleApi.activity(project.id)]); setItems(work.items.filter((item) => !item.parent_id)); setMilestones(miles.milestones || []); setActivity(acts.activity || []); } catch (reason) { message.error(errorText(reason, "项目概览加载失败")); } finally { setLoading(false); } }
  useEffect(() => { void load(); }, [project.id]);
  const done = items.filter((item) => item.status === "done").length;
  const doing = items.filter((item) => item.status === "doing").length;
  const overdue = items.filter((item) => item.due_date && item.due_date < new Date().toISOString().slice(0, 10) && item.status !== "done").length;
  const percent = items.length ? Math.round(done / items.length * 100) : 0;
  return <div className="tab-stack">
    <Row gutter={[16, 16]}>{[["任务总数", items.length], ["进行中", doing], ["已完成", done], ["已逾期", overdue]].map(([title, value]) => <Col xs={12} lg={6} key={String(title)}><Card loading={loading}><Statistic title={title} value={value} /></Card></Col>)}</Row>
    <Card title="整体进度"><Progress percent={percent} status={percent === 100 ? "success" : "active"} /></Card>
    <Row gutter={[16, 16]}><Col xs={24} lg={12}><Card title="里程碑" extra={canWrite(project) && <Button type="link" icon={<PlusOutlined />} onClick={() => setMilestoneOpen(true)}>新增</Button>}>{milestones.length ? <List dataSource={milestones} renderItem={(milestone) => { const related = items.filter((item) => item.milestone_id === milestone.id); const completed = related.filter((item) => item.status === "done").length; return <List.Item><List.Item.Meta title={<Space>{milestone.name}{milestone.status === "closed" && <Tag color="green">已关闭</Tag>}</Space>} description={<Progress size="small" percent={related.length ? Math.round(completed / related.length * 100) : 0} />} /></List.Item>; }} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有里程碑" />}</Card></Col><Col xs={24} lg={12}><Card title="近期活动">{activity.length ? <Timeline items={activity.slice(0, 12).map((item) => ({ children: <><Typography.Text strong>{item.actor || "系统"}</Typography.Text> {item.detail || item.kind}<div><Typography.Text type="secondary">{item.created_at ? new Date(item.created_at * 1000).toLocaleString() : ""}</Typography.Text></div></> }))} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无任务活动" />}</Card></Col></Row>
    <Modal title="新增里程碑" open={milestoneOpen} onCancel={() => setMilestoneOpen(false)} onOk={() => form.submit()} destroyOnHidden><Form form={form} layout="vertical" onFinish={async (values) => { try { await consoleApi.createMilestone(project.id, values); message.success("里程碑已创建"); setMilestoneOpen(false); form.resetFields(); await load(); } catch (reason) { message.error(errorText(reason, "创建失败")); } }}><Form.Item name="name" label="名称" rules={[{ required: true, whitespace: true }]}><Input /></Form.Item><Form.Item name="due_date" label="截止日期"><Input type="date" /></Form.Item></Form></Modal>
  </div>;
}

function TasksTab({ project }: { project: Project }) {
  const { message } = App.useApp();
  const [items, setItems] = useState<WorkItem[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<WorkItem | null | undefined>(undefined);
  const [form] = Form.useForm<Partial<WorkItem> & { title: string }>();
  async function load() { setLoading(true); try { const [work, memberResult, milestoneResult] = await Promise.all([consoleApi.workItems(project.id), consoleApi.projectMembers(project.id), consoleApi.milestones(project.id)]); setItems(work.items || []); setMembers(memberResult.members || []); setMilestones(milestoneResult.milestones || []); } catch (reason) { message.error(errorText(reason, "任务加载失败")); } finally { setLoading(false); } }
  useEffect(() => { void load(); }, [project.id]);
  function open(item: WorkItem | null) { setEditing(item); form.setFieldsValue(item || { title: "", status: "todo", priority: "", assignee: "", estimate_h: 0, spent_h: 0, labels: [] }); }
  async function quickPatch(item: WorkItem, patch: Partial<WorkItem>) { try { await consoleApi.updateWorkItem(project.id, item.id, patch); await load(); } catch (reason) { message.error(errorText(reason, "任务更新失败")); } }
  const topLevel = items.filter((item) => !item.parent_id);
  const columns: ProColumns<WorkItem>[] = [
    { title: "任务", dataIndex: "title", width: 300, render: (_value, item) => <div><Typography.Text strong>{item.title}</Typography.Text>{item.description && <div><Typography.Text type="secondary" ellipsis>{item.description}</Typography.Text></div>}</div> },
    { title: "状态", dataIndex: "status", width: 130, render: (_value, item) => <Select size="small" value={item.status} disabled={!canWrite(project)} options={STATUS_OPTIONS} onChange={(status) => void quickPatch(item, { status })} /> },
    { title: "优先级", dataIndex: "priority", width: 100, render: (value) => value ? <Tag color={PRIORITY_COLORS[String(value)]}>{PRIORITY_OPTIONS.find((option) => option.value === value)?.label}</Tag> : "-" },
    { title: "负责人", dataIndex: "assignee_name", width: 130, render: (value) => value || "未指派" },
    { title: "截止", dataIndex: "due_date", width: 120, valueType: "date" },
    { title: "工时", width: 100, render: (_value, item) => `${item.spent_h || 0}/${item.estimate_h || 0}h` },
    { title: "操作", valueType: "option", width: 140, render: (_value, item) => <Space><Button type="link" size="small" icon={<EditOutlined />} onClick={() => open(item)}>详情</Button>{canWrite(project) && <Popconfirm title="删除此任务？" onConfirm={() => void (async () => { try { await consoleApi.deleteWorkItem(project.id, item.id); message.success("任务已删除"); await load(); } catch (reason) { message.error(errorText(reason, "删除失败")); } })()}><Button type="link" danger size="small" icon={<DeleteOutlined />}>删除</Button></Popconfirm>}</Space> },
  ];
  return <>
    <ProTable<WorkItem> rowKey="id" columns={columns} dataSource={topLevel} loading={loading} search={{ labelWidth: "auto" }} pagination={{ pageSize: 15 }} scroll={{ x: 1000 }} options={{ reload: () => void load(), density: true, setting: true }} toolBarRender={() => canWrite(project) ? [<Button key="new" type="primary" icon={<PlusOutlined />} onClick={() => open(null)}>新建任务</Button>] : []} />
    <Drawer width={620} open={editing !== undefined} title={editing ? `任务 · ${editing.title}` : "新建任务"} onClose={() => setEditing(undefined)} destroyOnHidden extra={canWrite(project) && <Button type="primary" onClick={() => form.submit()}>保存</Button>}>
      <Form form={form} layout="vertical" disabled={!canWrite(project)} onFinish={async (values) => { try { const body = { ...values, labels: Array.isArray(values.labels) ? values.labels : [] }; if (editing) await consoleApi.updateWorkItem(project.id, editing.id, body); else await consoleApi.createWorkItem(project.id, body); message.success("任务已保存"); setEditing(undefined); await load(); } catch (reason) { message.error(errorText(reason, "保存失败")); } }}>
        <Form.Item name="title" label="标题" rules={[{ required: true, whitespace: true }]}><Input maxLength={300} /></Form.Item>
        <Form.Item name="description" label="描述"><Input.TextArea rows={5} /></Form.Item>
        <Row gutter={12}><Col span={12}><Form.Item name="status" label="状态"><Select options={STATUS_OPTIONS} /></Form.Item></Col><Col span={12}><Form.Item name="priority" label="优先级"><Select options={PRIORITY_OPTIONS} /></Form.Item></Col></Row>
        <Row gutter={12}><Col span={12}><Form.Item name="assignee" label="负责人"><Select allowClear options={members.map((member) => ({ value: member.account_id, label: member.name }))} /></Form.Item></Col><Col span={12}><Form.Item name="milestone_id" label="里程碑"><Select allowClear options={milestones.map((milestone) => ({ value: milestone.id, label: milestone.name }))} /></Form.Item></Col></Row>
        <Row gutter={12}><Col span={12}><Form.Item name="start_date" label="开始日期"><Input type="date" /></Form.Item></Col><Col span={12}><Form.Item name="due_date" label="截止日期"><Input type="date" /></Form.Item></Col></Row>
        <Row gutter={12}><Col span={12}><Form.Item name="estimate_h" label="预估工时"><InputNumber min={0} className="full-width" addonAfter="h" /></Form.Item></Col><Col span={12}><Form.Item name="spent_h" label="投入工时"><InputNumber min={0} className="full-width" addonAfter="h" /></Form.Item></Col></Row>
        <Form.Item name="labels" label="标签"><Select mode="tags" tokenSeparators={[","]} /></Form.Item>
      </Form>
    </Drawer>
  </>;
}

function KnowledgeTab({ project }: { project: Project }) {
  const { message } = App.useApp();
  const [items, setItems] = useState<KnowledgeBase[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [selected, setSelected] = useState<KnowledgeBase | null>(null);
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [form] = Form.useForm<Partial<KnowledgeBase> & { name: string }>();
  async function load() { setLoading(true); try { setItems((await consoleApi.knowledgeBases(project.id)).items || []); } catch (reason) { message.error(errorText(reason, "知识库加载失败")); } finally { setLoading(false); } }
  async function loadDocs(kb: KnowledgeBase) { setSelected(kb); try { setDocuments((await consoleApi.knowledgeDocuments(project.id, kb.id)).items || []); } catch (reason) { message.error(errorText(reason, "文档加载失败")); } }
  useEffect(() => { void load(); }, [project.id]);
  const columns: ProColumns<KnowledgeBase>[] = [
    { title: "知识库", dataIndex: "name", render: (_value, item) => <Space><Avatar shape="square">{item.icon || "📚"}</Avatar><div><Typography.Text strong>{item.name}</Typography.Text><div><Typography.Text type="secondary">{item.description || "暂无简介"}</Typography.Text></div></div></Space> },
    { title: "向量模型", width: 160, render: (_value, item) => <Tag>Embedding-{item.embedding_id} · {item.embedding_dim}维</Tag> },
    { title: "切片", width: 100, render: (_value, item) => `类型 ${item.knowledge_type}` },
    { title: "文档", dataIndex: "doc_count", width: 80 },
    { title: "操作", valueType: "option", width: 150, render: (_value, item) => <Space><Button type="link" size="small" onClick={() => void loadDocs(item)}>打开</Button>{canWrite(project) && <Popconfirm title={`删除知识库“${item.name}”及全部文档？`} onConfirm={async () => { try { await consoleApi.deleteKnowledgeBase(project.id, item.id); message.success("知识库已删除"); await load(); } catch (reason) { message.error(errorText(reason, "删除失败")); } }}><Button type="link" danger size="small">删除</Button></Popconfirm>}</Space> },
  ];
  return <>
    <ProTable<KnowledgeBase> rowKey="id" columns={columns} dataSource={items} loading={loading} search={false} options={{ reload: () => void load(), density: true }} toolBarRender={() => canWrite(project) ? [<Button key="new" type="primary" icon={<PlusOutlined />} onClick={() => { form.setFieldsValue({ icon: "📚", embedding_id: 11, knowledge_type: 5, sentence_size: 300, contextual: 0 }); setCreateOpen(true); }}>新建知识库</Button>] : []} />
    <Modal title="新建知识库" open={createOpen} onCancel={() => setCreateOpen(false)} onOk={() => form.submit()} destroyOnHidden><Form form={form} layout="vertical" onFinish={async (values) => { try { await consoleApi.createKnowledgeBase(project.id, values); message.success("知识库已创建"); setCreateOpen(false); form.resetFields(); await load(); } catch (reason) { message.error(errorText(reason, "创建失败")); } }}><Row gutter={12}><Col span={6}><Form.Item name="icon" label="图标"><Input /></Form.Item></Col><Col span={18}><Form.Item name="name" label="名称" rules={[{ required: true, whitespace: true }]}><Input /></Form.Item></Col></Row><Form.Item name="description" label="用途简介"><Input.TextArea rows={3} /></Form.Item><Row gutter={12}><Col span={12}><Form.Item name="embedding_id" label="向量模型"><Select options={[{ value: 11, label: "Embedding-3" }, { value: 12, label: "Embedding-3-pro" }, { value: 3, label: "Embedding-2" }]} /></Form.Item></Col><Col span={12}><Form.Item name="knowledge_type" label="切片方式"><Select options={[1, 2, 3, 5, 6, 7].map((value) => ({ value, label: `类型 ${value}` }))} /></Form.Item></Col></Row><Form.Item name="sentence_size" label="切片字数"><InputNumber min={20} max={2000} className="full-width" /></Form.Item><Form.Item name="contextual" label="上下文增强" valuePropName="checked" getValueFromEvent={(checked) => checked ? 1 : 0} getValueProps={(value) => ({ checked: Boolean(value) })}><Switch /></Form.Item></Form></Modal>
    <Drawer width={680} open={Boolean(selected)} title={selected ? `${selected.icon || "📚"} ${selected.name}` : "知识库"} onClose={() => setSelected(null)} destroyOnHidden>
      {selected && <><Descriptions column={1} bordered size="small" items={[{ key: "desc", label: "用途", children: selected.description || "-" }, { key: "embedding", label: "向量模型", children: `Embedding-${selected.embedding_id} · ${selected.embedding_dim}维` }, { key: "status", label: "处理边界", children: "文档存于 Server；向量化由本地执行面完成" }]} /><Card className="drawer-card" title="文档" extra={canWrite(project) && <Upload showUploadList={false} beforeUpload={(file) => { void (async () => { try { await consoleApi.uploadKnowledgeDocument(project.id, selected.id, file); message.success("文档已上传"); await loadDocs(selected); await load(); } catch (reason) { message.error(errorText(reason, "上传失败")); } })(); return false; }}><Button icon={<CloudUploadOutlined />}>上传文档</Button></Upload>}><List dataSource={documents} locale={{ emptyText: "还没有文档" }} renderItem={(doc) => <List.Item actions={canWrite(project) ? [<Popconfirm key="delete" title="删除此文档？" onConfirm={async () => { await consoleApi.deleteKnowledgeDocument(project.id, selected.id, doc.id); await loadDocs(selected); await load(); }}><Button danger type="link" size="small">删除</Button></Popconfirm>] : []}><List.Item.Meta avatar={<FileTextOutlined />} title={doc.filename} description={`${(doc.size / 1024).toFixed(1)} KB · ${doc.vector_status === 1 ? "已向量化" : doc.vector_status === 2 ? `失败：${doc.fail_msg || "未知"}` : "未向量化"}`} /></List.Item>} /></Card></>}
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
