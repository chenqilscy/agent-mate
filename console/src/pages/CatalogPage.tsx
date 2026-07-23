import { App, Avatar, Button, Card, Col, Drawer, Empty, Form, Input, InputNumber, Popconfirm, Row, Select, Space, Switch, Tabs, Tag, Typography } from "antd";
import { DeleteOutlined, EditOutlined, PlusOutlined } from "@ant-design/icons";
import { PageContainer, ProTable } from "@ant-design/pro-components";
import type { ProColumns } from "@ant-design/pro-components";
import { useEffect, useMemo, useState } from "react";
import { consoleApi } from "../api";
import type { CatalogData, CatalogItem } from "../types";

type Section = "experts" | "connectors" | "knowledge";
type TabKey = "gallery" | "manage" | "recommendations";

interface SectionConfig {
  title: string;
  subtitle: string;
  definitions: string[];
  itemLabel: string;
  galleryLabel: string;
  manageLabel: string;
  galleryTitle: string;
  recommendation?: string;
}

const CONFIG: Record<Section, SectionConfig> = {
  experts: {
    title: "专家",
    subtitle: "管理专家、专家团与客户端推荐位",
    definitions: ["EXPERT_DEFS", "EXP_TEAMS"],
    itemLabel: "专家能力",
    galleryLabel: "专家浏览",
    manageLabel: "专家管理",
    galleryTitle: "App 当前可用专家",
    recommendation: "EXPERT_RECOMMENDATIONS",
  },
  connectors: {
    title: "连接器",
    subtitle: "管理客户端可用连接器与推荐位",
    definitions: ["CONN_DEFS"],
    itemLabel: "连接器",
    galleryLabel: "连接器浏览",
    manageLabel: "连接器管理",
    galleryTitle: "App 当前可用连接器",
    recommendation: "CONNECTOR_RECOMMENDATIONS",
  },
  knowledge: {
    title: "知识库模板",
    subtitle: "管理新建知识库时可复用的模板与切片参数",
    definitions: ["KB_TPLS"],
    itemLabel: "知识库模板",
    galleryLabel: "模板浏览",
    manageLabel: "模板管理",
    galleryTitle: "当前可用知识库模板",
  },
};

function objectData(item: CatalogItem<CatalogData>): Record<string, unknown> {
  return typeof item.data === "object" && item.data !== null ? item.data : { value: item.data };
}
function titleOf(item: CatalogItem<CatalogData>): string {
  const data = objectData(item);
  return String(data.name || data.title || data.slug || data.key || data.connector_slug || data.expert_slug || "未命名配置");
}
function descriptionOf(item: CatalogItem<CatalogData>): string {
  const data = objectData(item);
  return String(data.description || data.desc || data.prompt || data.placement || "暂无说明");
}
function slugOf(item: CatalogItem<CatalogData>): string {
  const data = objectData(item);
  return String(data.slug || data.key || data.connector_slug || data.expert_slug || "");
}

export default function CatalogPage({ section }: { section: Section }) {
  const config = CONFIG[section];
  const { message } = App.useApp();
  const initial = new URLSearchParams(window.location.search).get("tab") as TabKey | null;
  const [tab, setTab] = useState<TabKey>(initial && ["gallery", "manage", "recommendations"].includes(initial) ? initial : "gallery");
  const categories = useMemo(() => tab === "recommendations" && config.recommendation ? [config.recommendation] : config.definitions, [config, tab]);
  const [items, setItems] = useState<CatalogItem<CatalogData>[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [editor, setEditor] = useState<{ item: CatalogItem<CatalogData> | null; category: string } | null>(null);
  const [form] = Form.useForm<{ category: string; sort: number; data: string }>();
  const activeItemLabel = tab === "recommendations" ? "推荐位" : config.itemLabel;

  async function load() {
    setLoading(true);
    try {
      const results = await Promise.all(categories.map((category) => consoleApi.catalog<CatalogData>(category, tab !== "gallery")));
      setItems(results.flatMap((result) => result.items || []).sort((left, right) => left.sort - right.sort));
    } catch (reason) { message.error(reason instanceof Error ? reason.message : `${config.title}加载失败`); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, [tab, section]);

  const visible = items.filter((item) => !query.trim() || `${titleOf(item)} ${slugOf(item)} ${descriptionOf(item)}`.toLowerCase().includes(query.trim().toLowerCase()));
  function openEditor(item: CatalogItem<CatalogData> | null) {
    const category = item?.category || categories[0];
    setEditor({ item, category });
    form.setFieldsValue({ category, sort: item?.sort || 0, data: JSON.stringify(item?.data || {}, null, 2) });
  }
  async function save(values: { category: string; sort: number; data: string }) {
    let data: CatalogData;
    try { data = JSON.parse(values.data) as CatalogData; } catch { message.error("JSON 格式无效"); return; }
    try {
      if (editor?.item) await consoleApi.updateCatalogItem(editor.item.id, { data, sort: values.sort });
      else await consoleApi.createCatalogItem(values.category, data, values.sort);
      message.success(editor?.item ? `${activeItemLabel}已更新` : `${activeItemLabel}已创建`); setEditor(null); await load();
    } catch (reason) { message.error(reason instanceof Error ? reason.message : "保存失败"); }
  }

  const columns: ProColumns<CatalogItem<CatalogData>>[] = [
    { title: activeItemLabel, dataIndex: "id", render: (_value, item) => <Space><Avatar shape="square">{String(objectData(item).icon || titleOf(item).slice(0, 1))}</Avatar><div><Typography.Text strong>{titleOf(item)}</Typography.Text><div><Typography.Text type="secondary" ellipsis>{descriptionOf(item)}</Typography.Text></div></div></Space> },
    { title: "标识", width: 190, render: (_value, item) => slugOf(item) ? <Typography.Text code copyable>{slugOf(item)}</Typography.Text> : "-" },
    ...(categories.length > 1 ? [{ title: "类型", dataIndex: "category", width: 150, render: (value: unknown) => <Tag>{String(value)}</Tag> } as ProColumns<CatalogItem<CatalogData>>] : []),
    { title: "排序", dataIndex: "sort", width: 80 },
    { title: "状态", dataIndex: "enabled", width: 100, render: (_value, item) => <Switch size="small" checked={item.enabled} checkedChildren="启用" unCheckedChildren="停用" onChange={async (enabled) => { try { await consoleApi.updateCatalogItem(item.id, { enabled }); message.success("状态已更新"); await load(); } catch (reason) { message.error(reason instanceof Error ? reason.message : "更新失败"); } }} /> },
    { title: "操作", valueType: "option", width: 150, render: (_value, item) => <Space><Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEditor(item)}>编辑</Button><Popconfirm title={`删除此${activeItemLabel}？`} onConfirm={async () => { try { await consoleApi.deleteCatalogItem(item.id); message.success(`${activeItemLabel}已删除`); await load(); } catch (reason) { message.error(reason instanceof Error ? reason.message : "删除失败"); } }}><Button type="link" danger size="small" icon={<DeleteOutlined />}>删除</Button></Popconfirm></Space> },
  ];

  const tabs = [
    { key: "gallery", label: config.galleryLabel },
    { key: "manage", label: config.manageLabel },
    ...(config.recommendation ? [{ key: "recommendations", label: "推荐位管理" }] : []),
  ];

  return (
    <PageContainer title={config.title} subTitle={config.subtitle} extra={tab !== "gallery" ? <Button type="primary" icon={<PlusOutlined />} onClick={() => openEditor(null)}>新增{activeItemLabel}</Button> : undefined} header={{ breadcrumb: { items: [{ title: "能力中心" }, { title: config.title }] } }}>
      <Tabs className="catalog-tabs" activeKey={tab} items={tabs} onChange={(key) => { const next = key as TabKey; setTab(next); const url = new URL(window.location.href); url.searchParams.set("tab", next); history.replaceState(null, "", url); }} />
      {tab === "gallery" ? (
        <Card loading={loading} title={config.galleryTitle} extra={<Input.Search allowClear placeholder={`搜索${config.itemLabel}`} value={query} onChange={(event) => setQuery(event.target.value)} />}>
          {visible.length ? <Row gutter={[16, 16]}>{visible.map((item) => <Col xs={24} md={12} xl={8} key={item.id}><Card size="small" className="catalog-card"><Space align="start"><Avatar shape="square" size={44}>{String(objectData(item).icon || titleOf(item).slice(0, 1))}</Avatar><div><Typography.Title level={5}>{titleOf(item)}</Typography.Title><Typography.Paragraph type="secondary" ellipsis={{ rows: 2 }}>{descriptionOf(item)}</Typography.Paragraph><Space wrap>{slugOf(item) && <Tag>{slugOf(item)}</Tag>}<Tag color="green">已启用</Tag></Space></div></Space></Card></Col>)}</Row> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={`暂无可用${config.itemLabel}`} />}
        </Card>
      ) : <ProTable<CatalogItem<CatalogData>> rowKey="id" columns={columns} dataSource={visible} loading={loading} search={false} options={{ reload: () => void load(), density: true, setting: true }} toolBarRender={() => [<Input.Search key="search" allowClear placeholder="搜索名称、标识或简介" value={query} onChange={(event) => setQuery(event.target.value)} />]} />}
      <Drawer width={680} open={Boolean(editor)} title={editor?.item ? `编辑 ${titleOf(editor.item)}` : `新增${activeItemLabel}`} onClose={() => setEditor(null)} destroyOnHidden extra={<Button type="primary" onClick={() => form.submit()}>保存</Button>}>
        <Form form={form} layout="vertical" onFinish={(values) => void save(values)}>
          <Form.Item name="category" label="定义类型" rules={[{ required: true }]}><Select disabled={Boolean(editor?.item)} options={categories.map((value) => ({ value, label: value }))} /></Form.Item>
          <Form.Item name="sort" label="排序"><InputNumber min={0} precision={0} className="full-width" /></Form.Item>
          <Form.Item name="data" label="定义 JSON" extra="使用真实能力定义结构；保存时由 Server 做类型校验。" rules={[{ required: true }]}><Input.TextArea rows={22} className="code-input" spellCheck={false} /></Form.Item>
        </Form>
      </Drawer>
    </PageContainer>
  );
}
