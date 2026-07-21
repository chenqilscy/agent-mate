import {
  App,
  Alert,
  AutoComplete,
  Avatar,
  Button,
  Card,
  Col,
  Descriptions,
  Drawer,
  Dropdown,
  Empty,
  Form,
  Input,
  InputNumber,
  List,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Switch,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import { IconPicker } from "../../src/components/ui/IconPicker";
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  DeleteOutlined,
  EditOutlined,
  FileTextOutlined,
  MoreOutlined,
  PlusOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import { PageContainer, ProTable } from "@ant-design/pro-components";
import type { ActionType, ProColumns } from "@ant-design/pro-components";
import { useEffect, useMemo, useRef, useState } from "react";
import { consoleApi } from "./api";
import SkillCategories from "./SkillCategories";
import SkillEditor from "./SkillEditor";
import type { CatalogItem, SkillCategoryData, SkillData, SkillRelease, SkillReleaseState, SkillTool, ToolCatalogAudit } from "./types";

type StatusFilter = "all" | "enabled" | "disabled";
type SkillTab = "gallery" | "manage" | "categories" | "tools" | "releases" | "recommendations";

export default function SkillsPage() {
  const { message } = App.useApp();
  const actionRef = useRef<ActionType>(null);
  const [items, setItems] = useState<CatalogItem<SkillData>[]>([]);
  const [skillCategories, setSkillCategories] = useState<CatalogItem<SkillCategoryData>[]>([]);
  const [tools, setTools] = useState<SkillTool[]>([]);
  const [releases, setReleases] = useState<SkillRelease[]>([]);
  const [loading, setLoading] = useState(true);
  const [mutatingId, setMutatingId] = useState("");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string | undefined>();
  const [status, setStatus] = useState<StatusFilter>("all");
  const requestedTab = new URLSearchParams(window.location.search).get("tab");
  const [tab, setTab] = useState<SkillTab>(requestedTab === "manage" || requestedTab === "categories" || requestedTab === "tools" || requestedTab === "releases" || requestedTab === "recommendations" ? requestedTab : "gallery");
  const [editor, setEditor] = useState<{ item: CatalogItem<SkillData> | null; tab: "info" | "files" } | null>(null);

  async function load() {
    setLoading(true);
    try {
      const [skills, categories, toolCatalog, releaseList] = await Promise.all([
        consoleApi.skills(), consoleApi.catalog<SkillCategoryData>("SKILL_CATEGORIES", true),
        consoleApi.tools(true), consoleApi.skillReleases(),
      ]);
      setItems(skills.items.sort((left, right) => left.sort - right.sort));
      setSkillCategories((categories.items || []).sort((left, right) => left.sort - right.sort));
      setTools(toolCatalog.tools || []);
      setReleases(releaseList.releases || []);
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : "技能目录加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  const visibleItems = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return items.filter((item) => {
      const skill = item.data;
      const haystack = `${skill.name} ${skill.slug} ${skill.description}`.toLowerCase();
      return (!normalized || haystack.includes(normalized))
        && (!category || skill.category_slug === category)
        && (status === "all" || item.enabled === (status === "enabled"));
    });
  }, [category, items, query, status]);

  async function moveSkill(item: CatalogItem<SkillData>, delta: number) {
    const index = items.findIndex((candidate) => candidate.id === item.id);
    const target = index + delta;
    if (index < 0 || target < 0 || target >= items.length) return;
    const ordered = [...items];
    const [picked] = ordered.splice(index, 1);
    ordered.splice(target, 0, picked);
    setMutatingId(item.id);
    try {
      await Promise.all(ordered.map((candidate, position) => consoleApi.updateSkill(candidate.id, { sort: position * 10 })));
      message.success("目录顺序已更新");
      await load();
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : "排序失败");
    } finally {
      setMutatingId("");
    }
  }

  const columns: ProColumns<CatalogItem<SkillData>>[] = [
    {
      title: "技能",
      dataIndex: ["data", "name"],
      fixed: "left",
      width: 330,
      render: (_value, item) => (
        <div className="skill-identity">
          <Avatar shape="square" size={38} className="skill-icon">{item.data.icon || <SafetyCertificateOutlined />}</Avatar>
          <div className="skill-copy">
            <Space size={6} wrap>
              <Typography.Text strong>{item.data.name || "未命名技能"}</Typography.Text>
              <Typography.Text code copyable>{item.data.slug}</Typography.Text>
            </Space>
            <Typography.Text type="secondary" ellipsis={{ tooltip: item.data.description }}>{item.data.description}</Typography.Text>
          </div>
        </div>
      ),
    },
    { title: "分类", dataIndex: ["data", "category"], width: 110, render: (value) => value ? <Tag>{String(value)}</Tag> : <Typography.Text type="secondary">未分类</Typography.Text> },
    { title: "版本", dataIndex: "version", width: 70, align: "center", render: (value) => `v${value || 1}` },
    { title: "文件", width: 70, align: "center", render: (_value, item) => `${(item.data.files?.length || 0) + 1}` },
    { title: "排序", dataIndex: "sort", width: 70, align: "center" },
    {
      title: "状态",
      dataIndex: "enabled",
      width: 90,
      render: (_value, item) => (
        <Tag color={item.enabled ? "green" : "default"}>{item.enabled ? "已发布" : "已撤回"}</Tag>
      ),
    },
    {
      title: "操作",
      valueType: "option",
      fixed: "right",
      width: 180,
      render: (_value, item) => {
        const index = items.findIndex((candidate) => candidate.id === item.id);
        return (
          <Space size={4}>
            <Button type="link" size="small" icon={<FileTextOutlined />} onClick={() => setEditor({ item, tab: "files" })}>文件</Button>
            <Button type="link" size="small" icon={<EditOutlined />} onClick={() => setEditor({ item, tab: "info" })}>编辑</Button>
            <Dropdown
              trigger={["click"]}
              menu={{
                items: [
                  { key: "up", icon: <ArrowUpOutlined />, label: "上移", disabled: index <= 0, onClick: () => void moveSkill(item, -1) },
                  { key: "down", icon: <ArrowDownOutlined />, label: "下移", disabled: index >= items.length - 1, onClick: () => void moveSkill(item, 1) },
                  { type: "divider" },
                  { key: "releases", icon: <SafetyCertificateOutlined />, label: "发布记录", onClick: () => setTab("releases") },
                ],
              }}
            >
              <Tooltip title="更多操作"><Button type="text" size="small" icon={<MoreOutlined />} aria-label={`更多操作：${item.data.name}`} /></Tooltip>
            </Dropdown>
          </Space>
        );
      },
    },
  ];

  return (
    <PageContainer
      title="技能"
      subTitle="维护 AgentMate 技能定义、版本与随技能安装的文本文件"
      extra={tab === "manage" ? <Button type="primary" icon={<PlusOutlined />} onClick={() => setEditor({ item: null, tab: "info" })}>新增技能</Button> : undefined}
      header={{ breadcrumb: { items: [{ title: "目录" }, { title: "技能" }] } }}
    >
      <Tabs
        activeKey={tab}
        className="catalog-tabs"
        items={[
          { key: "gallery", label: "目录预览" },
          { key: "manage", label: "目录管理" },
          { key: "categories", label: "分类管理" },
          { key: "tools", label: "内置工具" },
          { key: "releases", label: "发布治理" },
          { key: "recommendations", label: "推荐位管理" },
        ]}
        onChange={(key) => { const next = key as SkillTab; setTab(next); const url = new URL(window.location.href); url.searchParams.set("tab", next); history.replaceState(null, "", url); }}
      />
      {tab === "gallery" ? (
        <Card loading={loading} title="客户端生效预览" extra={<Input.Search allowClear placeholder="搜索技能" value={query} onChange={(event) => setQuery(event.target.value)} />}>
          {visibleItems.filter((item) => item.enabled).length ? <Row gutter={[16, 16]}>{visibleItems.filter((item) => item.enabled).map((item) => <Col xs={24} md={12} xl={8} key={item.id}><Card size="small" className="catalog-card"><Space align="start"><Avatar shape="square" size={44}>{item.data.icon || <SafetyCertificateOutlined />}</Avatar><div><Typography.Title level={5}>{item.data.name}</Typography.Title><Typography.Paragraph type="secondary" ellipsis={{ rows: 2 }}>{item.data.description}</Typography.Paragraph><Space wrap><Tag>{item.data.slug}</Tag>{item.data.category && <Tag color="blue">{item.data.category}</Tag>}</Space></div></Space></Card></Col>)}</Row> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无生效技能" />}
        </Card>
      ) : tab === "recommendations" ? <SkillRecommendations skills={items} categories={skillCategories} /> : tab === "categories" ? (
        <SkillCategories categories={skillCategories} skills={items} loading={loading} reload={load} />
      ) : tab === "tools" ? (
        <ToolCatalogManager tools={tools} loading={loading} reload={load} />
      ) : tab === "releases" ? (
        <SkillReleaseConsole releases={releases} tools={tools} loading={loading} reload={load} />
      ) : <ProTable<CatalogItem<SkillData>>
        actionRef={actionRef}
        rowKey="id"
        columns={columns}
        dataSource={visibleItems}
        loading={loading}
        search={false}
        pagination={false}
        cardBordered
        scroll={{ x: 920 }}
        options={{ density: true, fullScreen: true, reload: () => void load(), setting: true }}
        locale={{ emptyText: query || category || status !== "all" ? "没有匹配的技能" : "还没有技能定义" }}
        toolBarRender={() => [
          <Input.Search key="search" allowClear className="skill-search" placeholder="搜索名称、slug 或简介" value={query} onChange={(event) => setQuery(event.target.value)} />,
          <Select key="category" allowClear className="skill-filter" placeholder="全部分类" value={category} options={skillCategories.map((item) => ({ value: item.data.slug, label: `${item.data.icon || "🧩"} ${item.data.name}` }))} onChange={setCategory} />,
          <Select<StatusFilter> key="status" className="skill-filter" value={status} options={[{ value: "all", label: "全部状态" }, { value: "enabled", label: "已启用" }, { value: "disabled", label: "已停用" }]} onChange={setStatus} />,
        ]}
      />}
      <SkillEditor
        open={Boolean(editor)}
        item={editor?.item || null}
        tools={tools.filter((tool) => tool.enabled !== false && tool.bindable === true)}
        categories={skillCategories}
        initialTab={editor?.tab || "info"}
        onClose={() => setEditor(null)}
        onSaved={() => void load()}
      />
    </PageContainer>
  );
}

const RELEASE_STATE: Record<SkillReleaseState, { label: string; color: string }> = {
  draft: { label: "草稿", color: "default" },
  testing: { label: "测试中", color: "blue" },
  approved: { label: "已审核", color: "cyan" },
  rolling_out: { label: "灰度中", color: "gold" },
  published: { label: "已发布", color: "green" },
  withdrawn: { label: "已撤回", color: "red" },
  superseded: { label: "已替代", color: "default" },
};

function SkillReleaseConsole({
  releases, tools, loading, reload,
}: { releases: SkillRelease[]; tools: SkillTool[]; loading: boolean; reload: () => Promise<void> }) {
  const { message } = App.useApp();
  const [busy, setBusy] = useState("");
  const [detail, setDetail] = useState<SkillRelease | null>(null);
  const [testTarget, setTestTarget] = useState<SkillRelease | null>(null);
  const [publishTarget, setPublishTarget] = useState<SkillRelease | null>(null);
  const [testForm] = Form.useForm<{ passed: boolean; client_run_id: string; app_version: string; trace_id: string; error: string }>();
  const [publishForm] = Form.useForm<{ rollout_percent: number; rollout_channel: string }>();

  async function mutate(id: string, action: () => Promise<unknown>, success: string) {
    setBusy(id);
    try {
      await action();
      message.success(success);
      await reload();
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : "发布操作失败");
    } finally {
      setBusy("");
    }
  }

  function openTest(release: SkillRelease) {
    setTestTarget(release);
    testForm.setFieldsValue({ passed: true, client_run_id: "", app_version: "1.0.0", trace_id: "", error: "" });
  }

  function openPublish(release: SkillRelease) {
    setPublishTarget(release);
    publishForm.setFieldsValue({ rollout_percent: 100, rollout_channel: "stable" });
  }

  const columns: ProColumns<SkillRelease>[] = [
    { title: "技能", width: 210, fixed: "left", render: (_value, release) => <div><Typography.Text strong>{release.data.name}</Typography.Text><div><Typography.Text code>{release.slug}</Typography.Text></div></div> },
    { title: "版本", dataIndex: "version", width: 75, render: (value) => `v${value}` },
    { title: "状态", dataIndex: "state", width: 95, render: (_value, release) => <Tag color={RELEASE_STATE[release.state].color}>{RELEASE_STATE[release.state].label}</Tag> },
    { title: "客户端测试", dataIndex: "test_status", width: 110, render: (_value, release) => <Tag color={release.test_status === "passed" ? "green" : release.test_status === "failed" ? "red" : "default"}>{release.test_status === "passed" ? "通过" : release.test_status === "failed" ? "失败" : "待测试"}</Tag> },
    { title: "灰度", width: 110, render: (_value, release) => release.state === "rolling_out" || release.state === "published" ? `${release.rollout_channel} · ${release.rollout_percent}%` : "—" },
    { title: "运行", width: 120, render: (_value, release) => `${release.metrics.runs - release.metrics.run_failures}/${release.metrics.runs} 成功` },
    { title: "创建者 / 审核者", width: 190, render: (_value, release) => <Typography.Text type="secondary">{release.author_id} / {release.reviewer_id || "待审核"}</Typography.Text> },
    { title: "创建时间", dataIndex: "created_at", width: 170, render: (value) => new Date(Number(value) * 1000).toLocaleString() },
    {
      title: "操作", valueType: "option", width: 300, fixed: "right",
      render: (_value, release) => <Space size={2} wrap>
        <Button type="link" size="small" onClick={() => setDetail(release)}>详情</Button>
        {(release.state === "draft" || release.state === "testing") && <Button type="link" size="small" onClick={() => openTest(release)}>提交测试</Button>}
        {release.state === "testing" && release.test_status === "passed" && <Button type="link" size="small" loading={busy === release.id} onClick={() => void mutate(release.id, () => consoleApi.approveSkillRelease(release.id), "版本已审核")}>审核</Button>}
        {release.state === "approved" && <Button type="link" size="small" onClick={() => openPublish(release)}>发布</Button>}
        {release.state === "rolling_out" && <Button type="link" size="small" loading={busy === release.id} onClick={() => void mutate(release.id, () => consoleApi.pauseSkillRelease(release.id), "灰度已暂停")}>暂停</Button>}
        {(release.state === "rolling_out" || release.state === "published") && <Popconfirm title="撤回后客户端将收到 tombstone，确认继续？" onConfirm={() => void mutate(release.id, () => consoleApi.withdrawSkillRelease(release.id), "版本已撤回")}><Button danger type="link" size="small">撤回</Button></Popconfirm>}
        {(release.state === "withdrawn" || release.state === "superseded") && <Popconfirm title={`以 v${release.version} 内容创建并发布新的回滚版本？`} onConfirm={() => void mutate(release.id, () => consoleApi.rollbackSkillRelease(release.id), "回滚版本已发布")}><Button type="link" size="small">回滚</Button></Popconfirm>}
      </Space>,
    },
  ];

  return <>
    <Alert type="info" showIcon message="Skill 定义以不可变版本发布：草稿需先由真实 App 客户端回传 Test Run，再由非作者管理员审核；灰度按账号稳定分桶。" />
    <ProTable<SkillRelease>
      rowKey="id" columns={columns} dataSource={releases} loading={loading} search={false}
      pagination={{ pageSize: 20 }} scroll={{ x: 1320 }} options={{ reload: () => void reload(), density: true, setting: true }}
    />
    <Drawer width={720} open={Boolean(detail)} title={detail ? `${detail.data.name} · v${detail.version}` : "发布详情"} onClose={() => setDetail(null)}>
      {detail && <Space direction="vertical" size="large" className="full-width">
        <Descriptions bordered size="small" column={2} items={[
          { key: "state", label: "状态", children: RELEASE_STATE[detail.state].label },
          { key: "hash", label: "内容哈希", children: <Typography.Text code copyable>{detail.content_hash.slice(0, 16)}</Typography.Text> },
          { key: "author", label: "作者", children: detail.author_id },
          { key: "reviewer", label: "审核者", children: detail.reviewer_id || "—" },
          { key: "install", label: "安装", children: `${detail.metrics.installs} / 失败 ${detail.metrics.install_failures}` },
          { key: "run", label: "运行", children: `${detail.metrics.runs} / 失败 ${detail.metrics.run_failures}` },
        ]} />
        <Card size="small" title="定义 / 工具 / 权限 Diff"><Space wrap>
          {detail.diff.changed_fields.map((field) => <Tag key={field}>{field}</Tag>)}
          {detail.diff.tools_added.map((tool) => <Tag color="green" key={`+${tool}`}>+ {tool}</Tag>)}
          {detail.diff.tools_removed.map((tool) => <Tag color="red" key={`-${tool}`}>- {tool}</Tag>)}
          {detail.diff.permissions_after.map((permission) => <Tag color="blue" key={permission}>{permission}</Tag>)}
        </Space></Card>
        <Card size="small" title="审计记录"><List size="small" dataSource={detail.audit} renderItem={(entry) => <List.Item><Space><Tag>{entry.action}</Tag><Typography.Text>{entry.actor_id}</Typography.Text><Typography.Text type="secondary">{new Date(entry.created_at * 1000).toLocaleString()}</Typography.Text></Space></List.Item>} /></Card>
      </Space>}
    </Drawer>
    <Modal open={Boolean(testTarget)} title={testTarget ? `提交客户端 Test Run · ${testTarget.slug} v${testTarget.version}` : "提交客户端 Test Run"} okText="提交结果" onCancel={() => setTestTarget(null)} onOk={() => testForm.submit()} confirmLoading={Boolean(testTarget && busy === testTarget.id)}>
      <Form form={testForm} layout="vertical" onFinish={(values) => {
        if (!testTarget) return;
        const supported_tools = Object.fromEntries(tools.map((tool) => [tool.name, tool.contract_version || "1"]));
        void mutate(testTarget.id, () => consoleApi.submitSkillReleaseTest(testTarget.id, { ...values, supported_tools }), values.passed ? "客户端测试结果已登记" : "失败结果已登记").then(() => setTestTarget(null));
      }}>
        <Form.Item name="client_run_id" label="客户端 Run ID" rules={[{ required: true, whitespace: true }]}><Input placeholder="真实 App 执行产生的 run id" /></Form.Item>
        <Row gutter={12}><Col span={12}><Form.Item name="app_version" label="App 版本" rules={[{ required: true }]}><Input /></Form.Item></Col><Col span={12}><Form.Item name="trace_id" label="Trace ID"><Input /></Form.Item></Col></Row>
        <Form.Item name="passed" label="执行结果" rules={[{ required: true }]}><Select options={[{ value: true, label: "通过" }, { value: false, label: "失败" }]} /></Form.Item>
        <Form.Item name="error" label="错误摘要"><Input.TextArea rows={3} maxLength={1000} /></Form.Item>
      </Form>
    </Modal>
    <Modal open={Boolean(publishTarget)} title={publishTarget ? `发布 ${publishTarget.slug} v${publishTarget.version}` : "发布版本"} okText="开始发布" onCancel={() => setPublishTarget(null)} onOk={() => publishForm.submit()} confirmLoading={Boolean(publishTarget && busy === publishTarget.id)}>
      <Form form={publishForm} layout="vertical" onFinish={(values) => {
        if (!publishTarget) return;
        void mutate(publishTarget.id, () => consoleApi.publishSkillRelease(publishTarget.id, values), values.rollout_percent === 100 ? "版本已发布" : "灰度发布已启动").then(() => setPublishTarget(null));
      }}>
        <Form.Item name="rollout_channel" label="发布通道" rules={[{ required: true }]}><Select options={[{ value: "stable", label: "Stable" }, { value: "beta", label: "Beta" }]} /></Form.Item>
        <Form.Item name="rollout_percent" label="账号灰度比例（%）" rules={[{ required: true }]}><InputNumber min={1} max={100} precision={0} className="full-width" /></Form.Item>
      </Form>
    </Modal>
  </>;
}

const TOOL_RISK: Record<NonNullable<SkillTool["risk_level"]>, { label: string; color: string }> = {
  low: { label: "低", color: "green" },
  medium: { label: "中", color: "blue" },
  high: { label: "高", color: "orange" },
  critical: { label: "关键", color: "red" },
};

const TOOL_EXPOSURE: Record<NonNullable<SkillTool["exposure"]>, string> = {
  skill: "Skill 可声明",
  contextual: "按上下文注入",
  automatic: "运行时自动注入",
  internal: "系统内部",
};

type ToolFormValues = Pick<SkillTool, "label" | "description" | "category" | "risk_level" | "enabled" | "bindable" | "min_app_version" | "sort">;

function ToolCatalogManager({
  tools, loading, reload,
}: { tools: SkillTool[]; loading: boolean; reload: () => Promise<void> }) {
  const { message } = App.useApp();
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<SkillTool | null>(null);
  const [audit, setAudit] = useState<ToolCatalogAudit[]>([]);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm<ToolFormValues>();
  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return tools;
    return tools.filter((tool) => `${tool.name} ${tool.label || ""} ${tool.description || ""} ${tool.category || ""}`.toLowerCase().includes(needle));
  }, [query, tools]);

  async function open(tool: SkillTool) {
    setEditing(tool);
    form.setFieldsValue({
      label: tool.label || tool.name,
      description: tool.description || "",
      category: tool.category || "",
      risk_level: tool.risk_level || "low",
      enabled: tool.enabled !== false,
      bindable: tool.bindable === true,
      min_app_version: tool.min_app_version || "1.0.0",
      sort: tool.sort || 0,
    });
    try {
      setAudit((await consoleApi.toolAudit(tool.name)).audit || []);
    } catch {
      setAudit([]);
    }
  }

  const columns: ProColumns<SkillTool>[] = [
    { title: "工具", dataIndex: "name", width: 250, fixed: "left", render: (_value, tool) => <div><Typography.Text strong>{tool.label || tool.name}</Typography.Text><div><Typography.Text code copyable>{tool.name}</Typography.Text></div></div> },
    { title: "分类", dataIndex: "category", width: 110, render: (value) => <Tag>{String(value || "未分类")}</Tag> },
    { title: "注入方式", dataIndex: "exposure", width: 140, render: (value) => TOOL_EXPOSURE[value as NonNullable<SkillTool["exposure"]>] || String(value || "—") },
    { title: "风险", dataIndex: "risk_level", width: 80, render: (value) => { const risk = TOOL_RISK[value as NonNullable<SkillTool["risk_level"]>] || TOOL_RISK.low; return <Tag color={risk.color}>{risk.label}</Tag>; } },
    { title: "权限", dataIndex: "permissions", width: 270, render: (_value, tool) => <Space size={[4, 4]} wrap>{(tool.permissions || []).length ? tool.permissions!.map((permission) => <Tag key={permission}>{permission}</Tag>) : <Typography.Text type="secondary">无</Typography.Text>}</Space> },
    { title: "契约 / 最低 App", width: 150, render: (_value, tool) => <Typography.Text type="secondary">v{tool.contract_version || "1"} / {tool.min_app_version || "1.0.0"}</Typography.Text> },
    { title: "Skill 绑定", dataIndex: "bindable", width: 95, render: (value) => value ? <Tag color="blue">可绑定</Tag> : <Tag>自动/内部</Tag> },
    { title: "状态", dataIndex: "enabled", width: 80, render: (value) => value ? <Tag color="green">启用</Tag> : <Tag color="red">停用</Tag> },
    { title: "操作", valueType: "option", width: 80, fixed: "right", render: (_value, tool) => <Button type="link" size="small" onClick={() => void open(tool)}>管理</Button> },
  ];

  return <>
    <Alert
      type="info"
      showIcon
      message={`数据库已登记 ${tools.length} 项真实内置工具，其中 ${tools.filter((tool) => tool.enabled !== false && tool.bindable).length} 项可由普通 Skill 选择。`}
      description="这里管理展示、风险、启停、Skill 绑定和兼容策略；工具名、权限、契约与注入方式来自已签名 App 实现，不能在 Console 伪造或删除。"
    />
    <ProTable<SkillTool>
      rowKey="name" columns={columns} dataSource={visible} loading={loading} search={false}
      pagination={false} scroll={{ x: 1250 }} options={{ reload: () => void reload(), density: true, setting: true }}
      toolBarRender={() => [<Input.Search key="search" allowClear className="skill-search" placeholder="搜索工具、分类或说明" value={query} onChange={(event) => setQuery(event.target.value)} />]}
    />
    <Drawer
      width={660} open={Boolean(editing)} title={editing ? `管理内置工具 · ${editing.name}` : "管理内置工具"}
      onClose={() => setEditing(null)} destroyOnHidden
      extra={<Button type="primary" loading={saving} onClick={() => form.submit()}>保存</Button>}
    >
      {editing && <Space direction="vertical" size="large" className="full-width">
        <Descriptions bordered size="small" column={2} items={[
          { key: "name", label: "实现名", children: <Typography.Text code copyable>{editing.name}</Typography.Text> },
          { key: "exposure", label: "注入方式", children: TOOL_EXPOSURE[editing.exposure || "skill"] },
          { key: "contract", label: "工具契约", children: editing.contract_version || "1" },
          { key: "permissions", label: "实现权限", span: 2, children: <Space wrap>{(editing.permissions || []).map((permission) => <Tag key={permission}>{permission}</Tag>)}</Space> },
        ]} />
        <Form<ToolFormValues> form={form} layout="vertical" onFinish={async (values) => {
          setSaving(true);
          try {
            await consoleApi.updateTool(editing.name, values);
            message.success("工具目录已更新");
            setEditing(null);
            await reload();
          } catch (reason) {
            message.error(reason instanceof Error ? reason.message : "工具目录更新失败");
          } finally {
            setSaving(false);
          }
        }}>
          <Row gutter={12}><Col span={14}><Form.Item name="label" label="显示名称" rules={[{ required: true, whitespace: true }]}><Input maxLength={120} /></Form.Item></Col><Col span={10}><Form.Item name="category" label="分类"><Input maxLength={80} /></Form.Item></Col></Row>
          <Form.Item name="description" label="说明"><Input.TextArea rows={3} maxLength={500} showCount /></Form.Item>
          <Row gutter={12}>
            <Col span={8}><Form.Item name="risk_level" label="风险级别"><Select options={Object.entries(TOOL_RISK).map(([value, meta]) => ({ value, label: meta.label }))} /></Form.Item></Col>
            <Col span={10}><Form.Item name="min_app_version" label="最低 App 版本" rules={[{ required: true, pattern: /^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?$/ }]}><Input /></Form.Item></Col>
            <Col span={6}><Form.Item name="sort" label="排序"><InputNumber min={0} precision={0} className="full-width" /></Form.Item></Col>
          </Row>
          <Row gutter={12}>
            <Col span={12}><Form.Item name="enabled" label="目录状态" valuePropName="checked"><Switch checkedChildren="启用" unCheckedChildren="停用" /></Form.Item></Col>
            <Col span={12}><Form.Item name="bindable" label="允许普通 Skill 绑定" valuePropName="checked" extra={editing.exposure === "skill" ? undefined : "仅 Skill 可声明类型允许绑定。"}><Switch disabled={editing.exposure !== "skill"} /></Form.Item></Col>
          </Row>
        </Form>
        <Card size="small" title="变更审计">
          <List size="small" dataSource={audit} locale={{ emptyText: "暂无变更" }} renderItem={(entry) => <List.Item><Space><Tag>{entry.action}</Tag><Typography.Text>{entry.actor_id}</Typography.Text><Typography.Text type="secondary">{new Date(entry.created_at * 1000).toLocaleString()}</Typography.Text></Space></List.Item>} />
        </Card>
      </Space>}
    </Drawer>
  </>;
}

function SkillRecommendations({
  skills,
  categories,
}: {
  skills: CatalogItem<SkillData>[];
  categories: CatalogItem<SkillCategoryData>[];
}) {
  const { message } = App.useApp();
  const [items, setItems] = useState<CatalogItem<Record<string, unknown>>[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<CatalogItem<Record<string, unknown>> | null | undefined>(undefined);
  const [form] = Form.useForm<{
    provider: string; skill_slug: string; title: string; icon: string;
    category_slug: string; description: string; sort: number;
  }>();
  const provider = Form.useWatch("provider", form);

  async function load() {
    setLoading(true);
    try {
      const result = await consoleApi.catalog<Record<string, unknown>>("SKILL_RECOMMENDATIONS", true);
      setItems(result.items || []);
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : "推荐位加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  function syncAgentMateCategory(slug: string) {
    const skill = skills.find((item) => item.data.slug === slug);
    if (skill) form.setFieldValue("category_slug", skill.data.category_slug);
  }

  function open(item: CatalogItem<Record<string, unknown>> | null) {
    setEditing(item);
    const data = item?.data || {};
    const skillSlug = String(data.skill_slug || "");
    const inherited = skills.find((skill) => skill.data.slug === skillSlug)?.data.category_slug;
    const legacy = categories.find((category) => category.data.name === String(data.category || ""))?.data.slug;
    form.setFieldsValue({
      provider: String(data.provider || "agentmate"),
      skill_slug: skillSlug,
      title: String(data.title || ""),
      icon: String(data.icon || ""),
      category_slug: String(data.category_slug || inherited || legacy || ""),
      description: String(data.description || ""),
      sort: item?.sort || 0,
    });
  }

  const columns: ProColumns<CatalogItem<Record<string, unknown>>>[] = [
    { title: "技能", render: (_value, item) => <Space><Avatar shape="square">{String(item.data.icon || "✨")}</Avatar><div><Typography.Text strong>{String(item.data.title || item.data.skill_slug)}</Typography.Text><div><Typography.Text type="secondary">{String(item.data.description || "")}</Typography.Text></div></div></Space> },
    { title: "slug", width: 180, render: (_value, item) => <Typography.Text code>{String(item.data.skill_slug || "")}</Typography.Text> },
    { title: "分类", width: 120, render: (_value, item) => <Tag>{String(item.data.category || "未分类")}</Tag> },
    { title: "来源", width: 110, render: (_value, item) => <Tag>{String(item.data.provider || "agentmate")}</Tag> },
    { title: "排序", dataIndex: "sort", width: 80 },
    { title: "状态", width: 90, render: (_value, item) => <Switch size="small" checked={item.enabled} onChange={async (enabled) => { await consoleApi.updateCatalogItem(item.id, { enabled }); await load(); }} /> },
    { title: "操作", valueType: "option", width: 140, render: (_value, item) => <Space><Button type="link" size="small" onClick={() => open(item)}>编辑</Button><Popconfirm title="删除此推荐位？" onConfirm={async () => { await consoleApi.deleteCatalogItem(item.id); await load(); }}><Button type="link" danger size="small">删除</Button></Popconfirm></Space> },
  ];

  return <>
    <ProTable<CatalogItem<Record<string, unknown>>>
      rowKey="id" columns={columns} dataSource={items} loading={loading} search={false}
      options={{ reload: () => void load(), density: true }}
      toolBarRender={() => [<Button key="new" type="primary" icon={<PlusOutlined />} onClick={() => open(null)}>新增推荐位</Button>]}
    />
    <Drawer width={580} open={editing !== undefined} title={editing ? "编辑推荐位" : "新增推荐位"} onClose={() => setEditing(undefined)} destroyOnHidden extra={<Button type="primary" onClick={() => form.submit()}>保存</Button>}>
      <Form form={form} layout="vertical" onFinish={async (values) => {
        const { sort, ...valuesData } = values;
        const selectedCategory = categories.find((category) => category.data.slug === values.category_slug);
        const skill = skills.find((item) => item.data.slug === values.skill_slug);
        const data = {
          ...(editing?.data || {}), ...valuesData,
          category_slug: values.provider === "agentmate" ? skill?.data.category_slug : values.category_slug,
          category: values.provider === "agentmate" ? skill?.data.category : selectedCategory?.data.name,
          placement: "skills.recommended",
        };
        try {
          if (editing) await consoleApi.updateCatalogItem(editing.id, { data, sort });
          else await consoleApi.createCatalogItem("SKILL_RECOMMENDATIONS", { ...data, starts_at: 0, ends_at: 0 }, sort);
          message.success("推荐位已保存");
          setEditing(undefined);
          await load();
        } catch (reason) {
          message.error(reason instanceof Error ? reason.message : "保存失败");
        }
      }}>
        <Form.Item name="provider" label="来源" rules={[{ required: true }]}>
          <Select options={[{ value: "agentmate", label: "AgentMate" }, { value: "skillhub", label: "SkillHub" }]} onChange={(value) => { if (value === "agentmate") syncAgentMateCategory(form.getFieldValue("skill_slug")); }} />
        </Form.Item>
        <Form.Item name="skill_slug" label="技能 slug" rules={[{ required: true, pattern: /^[A-Za-z0-9][A-Za-z0-9._-]*$/ }]}>
          <AutoComplete options={skills.map((item) => ({ value: item.data.slug, label: `${item.data.name} · ${item.data.slug}` }))} placeholder="选择 AgentMate 技能或输入 SkillHub slug" onSelect={(value) => { if (provider === "agentmate") syncAgentMateCategory(value); }} />
        </Form.Item>
        <Form.Item name="title" label="展示标题"><Input /></Form.Item>
        <Row gutter={12}>
          <Col span={8}><Form.Item name="icon" label="图标"><IconPicker ariaLabel="选择推荐位图标" /></Form.Item></Col>
          <Col span={16}>
            <Form.Item name="category_slug" label="分类" rules={[{ required: true, message: "请选择分类" }]} extra={provider === "agentmate" ? "AgentMate 技能自动继承定义分类。" : undefined}>
              <Select
                disabled={provider === "agentmate"}
                showSearch
                optionFilterProp="label"
                options={categories.map((category) => ({ value: category.data.slug, label: `${category.data.icon || "🧩"} ${category.data.name}`, disabled: !category.enabled }))}
              />
            </Form.Item>
          </Col>
        </Row>
        <Form.Item name="description" label="简介"><Input.TextArea rows={4} /></Form.Item>
        <Form.Item name="sort" label="排序"><InputNumber min={0} className="full-width" /></Form.Item>
      </Form>
    </Drawer>
  </>;
}
