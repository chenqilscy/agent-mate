import {
  App,
  AutoComplete,
  Avatar,
  Button,
  Card,
  Col,
  Drawer,
  Dropdown,
  Empty,
  Form,
  Input,
  InputNumber,
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
import SkillEditor from "./SkillEditor";
import type { CatalogItem, SkillData, SkillTool } from "./types";

type StatusFilter = "all" | "enabled" | "disabled";
type SkillTab = "gallery" | "manage" | "recommendations";

export default function SkillsPage() {
  const { message, modal } = App.useApp();
  const actionRef = useRef<ActionType>(null);
  const [items, setItems] = useState<CatalogItem<SkillData>[]>([]);
  const [tools, setTools] = useState<SkillTool[]>([]);
  const [loading, setLoading] = useState(true);
  const [mutatingId, setMutatingId] = useState("");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string | undefined>();
  const [status, setStatus] = useState<StatusFilter>("all");
  const requestedTab = new URLSearchParams(window.location.search).get("tab");
  const [tab, setTab] = useState<SkillTab>(requestedTab === "manage" || requestedTab === "recommendations" ? requestedTab : "gallery");
  const [editor, setEditor] = useState<{ item: CatalogItem<SkillData> | null; tab: "info" | "files" } | null>(null);

  async function load() {
    setLoading(true);
    try {
      const [skills, toolCatalog] = await Promise.all([consoleApi.skills(), consoleApi.skillTools()]);
      setItems(skills.items.sort((left, right) => left.sort - right.sort));
      setTools(toolCatalog.tools || []);
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : "技能目录加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  const categories = useMemo(() => [...new Set(items.map((item) => item.data.category).filter(Boolean))].sort(), [items]);
  const visibleItems = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return items.filter((item) => {
      const skill = item.data;
      const haystack = `${skill.name} ${skill.slug} ${skill.description}`.toLowerCase();
      return (!normalized || haystack.includes(normalized))
        && (!category || skill.category === category)
        && (status === "all" || item.enabled === (status === "enabled"));
    });
  }, [category, items, query, status]);

  async function toggleSkill(item: CatalogItem<SkillData>, enabled: boolean) {
    setMutatingId(item.id);
    try {
      await consoleApi.updateSkill(item.id, { enabled });
      message.success(enabled ? "技能已启用" : "技能已停用");
      await load();
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : "状态更新失败");
    } finally {
      setMutatingId("");
    }
  }

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

  function archiveSkill(item: CatalogItem<SkillData>) {
    modal.confirm({
      title: `归档技能“${item.data.name}”？`,
      content: `slug ${item.data.slug} 会保留，以保护已安装客户端；稍后仍可重新启用。`,
      okText: "归档",
      okButtonProps: { danger: true },
      cancelText: "取消",
      onOk: async () => {
        try {
          await consoleApi.archiveSkill(item.id);
          message.success("技能已归档");
          await load();
        } catch (reason) {
          message.error(reason instanceof Error ? reason.message : "归档失败");
        }
      },
    });
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
        <Switch
          size="small"
          checked={item.enabled}
          loading={mutatingId === item.id}
          checkedChildren="启用"
          unCheckedChildren="停用"
          onChange={(checked) => void toggleSkill(item, checked)}
        />
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
                  { key: "archive", icon: <DeleteOutlined />, danger: true, label: "归档", disabled: !item.enabled, onClick: () => archiveSkill(item) },
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
          { key: "recommendations", label: "推荐位管理" },
        ]}
        onChange={(key) => { const next = key as SkillTab; setTab(next); const url = new URL(window.location.href); url.searchParams.set("tab", next); history.replaceState(null, "", url); }}
      />
      {tab === "gallery" ? (
        <Card loading={loading} title="客户端生效预览" extra={<Input.Search allowClear placeholder="搜索技能" value={query} onChange={(event) => setQuery(event.target.value)} />}>
          {visibleItems.filter((item) => item.enabled).length ? <Row gutter={[16, 16]}>{visibleItems.filter((item) => item.enabled).map((item) => <Col xs={24} md={12} xl={8} key={item.id}><Card size="small" className="catalog-card"><Space align="start"><Avatar shape="square" size={44}>{item.data.icon || <SafetyCertificateOutlined />}</Avatar><div><Typography.Title level={5}>{item.data.name}</Typography.Title><Typography.Paragraph type="secondary" ellipsis={{ rows: 2 }}>{item.data.description}</Typography.Paragraph><Space wrap><Tag>{item.data.slug}</Tag>{item.data.category && <Tag color="blue">{item.data.category}</Tag>}</Space></div></Space></Card></Col>)}</Row> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无生效技能" />}
        </Card>
      ) : tab === "recommendations" ? <SkillRecommendations skills={items} /> : <ProTable<CatalogItem<SkillData>>
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
          <Select key="category" allowClear className="skill-filter" placeholder="全部分类" value={category} options={categories.map((value) => ({ value, label: value }))} onChange={setCategory} />,
          <Select<StatusFilter> key="status" className="skill-filter" value={status} options={[{ value: "all", label: "全部状态" }, { value: "enabled", label: "已启用" }, { value: "disabled", label: "已停用" }]} onChange={setStatus} />,
        ]}
      />}
      <SkillEditor
        open={Boolean(editor)}
        item={editor?.item || null}
        tools={tools}
        initialTab={editor?.tab || "info"}
        onClose={() => setEditor(null)}
        onSaved={() => void load()}
      />
    </PageContainer>
  );
}

function SkillRecommendations({ skills }: { skills: CatalogItem<SkillData>[] }) {
  const { message } = App.useApp();
  const [items, setItems] = useState<CatalogItem<Record<string, unknown>>[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<CatalogItem<Record<string, unknown>> | null | undefined>(undefined);
  const [form] = Form.useForm<{ provider: string; skill_slug: string; title: string; icon: string; category: string; description: string; sort: number }>();
  async function load() { setLoading(true); try { const result = await consoleApi.catalog<Record<string, unknown>>("SKILL_RECOMMENDATIONS", true); setItems(result.items || []); } catch (reason) { message.error(reason instanceof Error ? reason.message : "推荐位加载失败"); } finally { setLoading(false); } }
  useEffect(() => { void load(); }, []);
  function open(item: CatalogItem<Record<string, unknown>> | null) { setEditing(item); const data = item?.data || {}; form.setFieldsValue({ provider: String(data.provider || "agentmate"), skill_slug: String(data.skill_slug || ""), title: String(data.title || ""), icon: String(data.icon || ""), category: String(data.category || ""), description: String(data.description || ""), sort: item?.sort || 0 }); }
  const columns: ProColumns<CatalogItem<Record<string, unknown>>>[] = [
    { title: "技能", render: (_value, item) => <Space><Avatar shape="square">{String(item.data.icon || "✨")}</Avatar><div><Typography.Text strong>{String(item.data.title || item.data.skill_slug)}</Typography.Text><div><Typography.Text type="secondary">{String(item.data.description || "")}</Typography.Text></div></div></Space> },
    { title: "slug", width: 180, render: (_value, item) => <Typography.Text code>{String(item.data.skill_slug || "")}</Typography.Text> },
    { title: "来源", width: 110, render: (_value, item) => <Tag>{String(item.data.provider || "agentmate")}</Tag> },
    { title: "排序", dataIndex: "sort", width: 80 },
    { title: "状态", width: 90, render: (_value, item) => <Switch size="small" checked={item.enabled} onChange={async (enabled) => { await consoleApi.updateCatalogItem(item.id, { enabled }); await load(); }} /> },
    { title: "操作", valueType: "option", width: 140, render: (_value, item) => <Space><Button type="link" size="small" onClick={() => open(item)}>编辑</Button><Popconfirm title="删除此推荐位？" onConfirm={async () => { await consoleApi.deleteCatalogItem(item.id); await load(); }}><Button type="link" danger size="small">删除</Button></Popconfirm></Space> },
  ];
  return <><ProTable<CatalogItem<Record<string, unknown>>> rowKey="id" columns={columns} dataSource={items} loading={loading} search={false} options={{ reload: () => void load(), density: true }} toolBarRender={() => [<Button key="new" type="primary" icon={<PlusOutlined />} onClick={() => open(null)}>新增推荐位</Button>]} /><Drawer width={580} open={editing !== undefined} title={editing ? "编辑推荐位" : "新增推荐位"} onClose={() => setEditing(undefined)} destroyOnHidden extra={<Button type="primary" onClick={() => form.submit()}>保存</Button>}><Form form={form} layout="vertical" onFinish={async (values) => { const { sort, ...valuesData } = values; const data = { ...(editing?.data || {}), ...valuesData, placement: "skills.recommended" }; try { if (editing) await consoleApi.updateCatalogItem(editing.id, { data, sort }); else await consoleApi.createCatalogItem("SKILL_RECOMMENDATIONS", { ...data, starts_at: 0, ends_at: 0 }, sort); message.success("推荐位已保存"); setEditing(undefined); await load(); } catch (reason) { message.error(reason instanceof Error ? reason.message : "保存失败"); } }}><Form.Item name="provider" label="来源" rules={[{ required: true }]}><Select options={[{ value: "agentmate", label: "AgentMate" }, { value: "skillhub", label: "SkillHub" }]} /></Form.Item><Form.Item name="skill_slug" label="技能 slug" rules={[{ required: true, pattern: /^[A-Za-z0-9][A-Za-z0-9._-]*$/ }]}><AutoComplete options={skills.map((item) => ({ value: item.data.slug, label: `${item.data.name} · ${item.data.slug}` }))} placeholder="选择 AgentMate 技能或输入 SkillHub slug" /></Form.Item><Form.Item name="title" label="展示标题"><Input /></Form.Item><Row gutter={12}><Col span={8}><Form.Item name="icon" label="图标"><Input /></Form.Item></Col><Col span={16}><Form.Item name="category" label="分类"><Input /></Form.Item></Col></Row><Form.Item name="description" label="简介"><Input.TextArea rows={4} /></Form.Item><Form.Item name="sort" label="排序"><InputNumber min={0} className="full-width" /></Form.Item></Form></Drawer></>;
}
