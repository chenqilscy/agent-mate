import { Alert, App, Avatar, Button, Card, Col, Collapse, Divider, Drawer, Empty, Form, Input, InputNumber, Popconfirm, Radio, Row, Select, Space, Switch, Tabs, Tag, Typography } from "antd";
import { DeleteOutlined, EditOutlined, PlusOutlined } from "@ant-design/icons";
import { PageContainer, ProTable } from "@ant-design/pro-components";
import type { ProColumns } from "@ant-design/pro-components";
import { useEffect, useMemo, useState } from "react";
import { consoleApi } from "../api";
import type { CatalogData, CatalogItem } from "../types";

type Section = "experts" | "connectors" | "knowledge";
type TabKey = "gallery" | "manage" | "recommendations";
type TypedCategory = "EXPERT_DEFS" | "CONN_DEFS";

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

interface SecretEnvRow {
  target?: string;
  source?: string;
}

interface CatalogFormValues {
  category: string;
  sort: number;
  slug?: string;
  name?: string;
  avatar?: string;
  icon?: string;
  subtitle?: string;
  intro?: string;
  persona?: string;
  tags?: string[];
  expertCategory?: string;
  functional?: boolean;
  desc?: string;
  status?: "rdy" | "tok";
  launchMode?: "builtin" | "stdio";
  builtinServer?: string;
  command?: string;
  launchArgs?: string[];
  requires?: string[];
  requiresBin?: string[];
  secretEnv?: SecretEnvRow[];
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

const CATEGORY_LABELS: Record<string, string> = {
  EXPERT_DEFS: "专家定义",
  EXP_TEAMS: "专家团定义",
  CONN_DEFS: "连接器定义",
  EXPERT_RECOMMENDATIONS: "专家推荐位",
  CONNECTOR_RECOMMENDATIONS: "连接器推荐位",
  KB_TPLS: "知识库模板",
};

const BUILTIN_SERVERS = ["notes", "clock", "search", "telegram", "kdocs"];
const ENV_NAME_PATTERN = /^[A-Z_][A-Z0-9_]*$/;

function objectData(item: CatalogItem<CatalogData> | null | undefined): Record<string, unknown> {
  const data = item?.data;
  return typeof data === "object" && data !== null ? data : {};
}

function recordData(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function titleOf(item: CatalogItem<CatalogData>): string {
  const data = objectData(item);
  return String(data.name || data.title || data.slug || data.key || data.connector_slug || data.expert_slug || "未命名配置");
}
function descriptionOf(item: CatalogItem<CatalogData>): string {
  const data = objectData(item);
  return String(data.description || data.desc || data.intro || data.prompt || data.placement || "暂无说明");
}
function slugOf(item: CatalogItem<CatalogData>): string {
  const data = objectData(item);
  return String(data.slug || data.key || data.connector_slug || data.expert_slug || "");
}
function isTypedCategory(category: string | undefined): category is TypedCategory {
  return category === "EXPERT_DEFS" || category === "CONN_DEFS";
}
function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category] || category;
}

function valuesFromData(category: string, data: Record<string, unknown>, sort: number): Partial<CatalogFormValues> {
  if (category === "EXPERT_DEFS") {
    return {
      category,
      sort,
      slug: String(data.slug || ""),
      name: String(data.name || ""),
      avatar: String(data.avatar || ""),
      subtitle: String(data.subtitle || ""),
      intro: String(data.intro || ""),
      persona: String(data.persona || ""),
      tags: stringArray(data.tags),
      expertCategory: String(data.category || ""),
      functional: data.functional !== false,
    };
  }
  if (category === "CONN_DEFS") {
    const launch = recordData(data.launch);
    const secretEnv = Object.entries(recordData(launch.secret_env)).map(([target, source]) => ({ target, source: String(source) }));
    return {
      category,
      sort,
      slug: String(data.slug || ""),
      name: String(data.name || ""),
      icon: String(data.icon || ""),
      desc: String(data.desc || data.description || ""),
      status: data.status === "tok" ? "tok" : "rdy",
      launchMode: launch.builtin_server ? "builtin" : "stdio",
      builtinServer: String(launch.builtin_server || ""),
      command: String(launch.command || ""),
      launchArgs: stringArray(launch.args),
      requires: stringArray(launch.requires),
      requiresBin: stringArray(launch.requires_bin),
      secretEnv,
    };
  }
  return { category, sort };
}

function nonEmptyStrings(values: string[] | undefined): string[] {
  return (values || []).map((value) => value.trim()).filter(Boolean);
}

function buildTypedData(category: TypedCategory, values: CatalogFormValues, baseData: Record<string, unknown>): Record<string, unknown> {
  if (category === "EXPERT_DEFS") {
    return {
      ...baseData,
      slug: values.slug?.trim() || "",
      name: values.name?.trim() || "",
      avatar: values.avatar?.trim() || "",
      subtitle: values.subtitle?.trim() || "",
      intro: values.intro?.trim() || "",
      persona: values.persona?.trim() || "",
      tags: nonEmptyStrings(values.tags),
      category: values.expertCategory?.trim() || "",
      functional: values.functional !== false,
    };
  }

  const launch: Record<string, unknown> = values.launchMode === "builtin"
    ? { builtin_server: values.builtinServer?.trim() || "", builtin: true }
    : { command: values.command?.trim() || "", args: nonEmptyStrings(values.launchArgs) };
  const requires = nonEmptyStrings(values.requires);
  const requiresBin = nonEmptyStrings(values.requiresBin);
  if (requires.length) launch.requires = requires;
  if (requiresBin.length) launch.requires_bin = requiresBin;
  if (values.launchMode === "stdio") {
    const secretEnv = Object.fromEntries((values.secretEnv || [])
      .map((row) => [row.target?.trim() || "", row.source?.trim() || ""])
      .filter(([target, source]) => target && source));
    if (Object.keys(secretEnv).length) launch.secret_env = secretEnv;
  }
  return {
    ...baseData,
    slug: values.slug?.trim() || "",
    name: values.name?.trim() || "",
    icon: values.icon?.trim() || "",
    desc: values.desc?.trim() || "",
    status: values.status || "rdy",
    launch,
  };
}

function StringListField({ name, label, placeholder, help }: { name: "launchArgs" | "requires" | "requiresBin"; label: string; placeholder: string; help?: string }) {
  const rules = name === "requires" ? [{ pattern: ENV_NAME_PATTERN, message: "仅允许大写环境变量名" }] : undefined;
  return (
    <Form.Item label={label} extra={help}>
      <Form.List name={name}>
        {(fields, { add, remove }) => (
          <Space direction="vertical" className="full-width" size={8}>
            {fields.map((field) => (
              <Space key={field.key} className="full-width" align="baseline">
                <Form.Item {...field} noStyle rules={rules}><Input placeholder={placeholder} /></Form.Item>
                <Button type="text" danger icon={<DeleteOutlined />} aria-label={`删除${label}`} onClick={() => remove(field.name)} />
              </Space>
            ))}
            <Button type="dashed" block icon={<PlusOutlined />} onClick={() => add()}>{`添加${label}`}</Button>
          </Space>
        )}
      </Form.List>
    </Form.Item>
  );
}

function SecretEnvField() {
  return (
    <Form.Item label="凭据变量映射" extra="这里只填写环境变量名，不填写 token、密码或 OAuth 值。">
      <Form.List name="secretEnv">
        {(fields, { add, remove }) => (
          <Space direction="vertical" className="full-width" size={8}>
            {fields.map((field) => (
              <Space key={field.key} className="full-width" align="baseline">
                <Form.Item name={[field.name, "target"]} rules={[{ pattern: ENV_NAME_PATTERN, message: "仅允许大写环境变量名" }]}><Input placeholder="MCP 进程变量名" /></Form.Item>
                <Typography.Text type="secondary">←</Typography.Text>
                <Form.Item name={[field.name, "source"]} rules={[{ pattern: ENV_NAME_PATTERN, message: "仅允许大写环境变量名" }]}><Input placeholder="backend/.env 变量名" /></Form.Item>
                <Button type="text" danger icon={<DeleteOutlined />} aria-label="删除凭据映射" onClick={() => remove(field.name)} />
              </Space>
            ))}
            <Button type="dashed" block icon={<PlusOutlined />} onClick={() => add()}>{"添加凭据映射"}</Button>
          </Space>
        )}
      </Form.List>
    </Form.Item>
  );
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
  const [baseData, setBaseData] = useState<Record<string, unknown>>({});
  const [advancedJson, setAdvancedJson] = useState("{}");
  const [jsonDirty, setJsonDirty] = useState(false);
  const [jsonError, setJsonError] = useState("");
  const [form] = Form.useForm<CatalogFormValues>();
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
    const data = objectData(item);
    setEditor({ item, category });
    setBaseData(data);
    setJsonError("");
    setJsonDirty(false);
    form.resetFields();
    form.setFieldsValue({ ...valuesFromData(category, data, item?.sort || 0) });
    setAdvancedJson(JSON.stringify(data, null, 2));
  }
  function syncJsonFromForm() {
    const values = form.getFieldsValue(true);
    if (!isTypedCategory(values.category) || jsonDirty) return;
    setAdvancedJson(JSON.stringify(buildTypedData(values.category, values, baseData), null, 2));
  }
  function applyAdvancedJson() {
    const category = form.getFieldValue("category") as string;
    let data: unknown;
    try { data = JSON.parse(advancedJson); } catch { setJsonError("JSON 格式无效，请修正后再应用"); return; }
    if (!data || typeof data !== "object" || Array.isArray(data)) { setJsonError("定义必须是 JSON 对象"); return; }
    const record = data as Record<string, unknown>;
    setBaseData(record);
    form.setFieldsValue({ ...valuesFromData(category, record, form.getFieldValue("sort") || 0) });
    setAdvancedJson(JSON.stringify(record, null, 2));
    setJsonDirty(false);
    setJsonError("");
    message.success("JSON 已应用到表单");
  }
  async function save(values: CatalogFormValues) {
    let data: CatalogData;
    if (isTypedCategory(values.category) && !jsonDirty) {
      data = buildTypedData(values.category, values, baseData);
    } else {
      try { data = JSON.parse(advancedJson) as CatalogData; } catch { setJsonError("JSON 格式无效，请修正后再保存"); return; }
    }
    try {
      if (editor?.item) await consoleApi.updateCatalogItem(editor.item.id, { data, sort: values.sort });
      else await consoleApi.createCatalogItem(values.category, data, values.sort);
      message.success(editor?.item ? `${activeItemLabel}已更新` : `${activeItemLabel}已创建`); setEditor(null); await load();
    } catch (reason) { message.error(reason instanceof Error ? reason.message : "保存失败"); }
  }

  const columns: ProColumns<CatalogItem<CatalogData>>[] = [
    { title: activeItemLabel, dataIndex: "id", render: (_value, item) => <Space><Avatar shape="square">{String(objectData(item).icon || objectData(item).avatar || titleOf(item).slice(0, 1))}</Avatar><div><Typography.Text strong>{titleOf(item)}</Typography.Text><div><Typography.Text type="secondary" ellipsis>{descriptionOf(item)}</Typography.Text></div></div></Space> },
    { title: "标识", width: 190, render: (_value, item) => slugOf(item) ? <Typography.Text code copyable>{slugOf(item)}</Typography.Text> : "-" },
    ...(categories.length > 1 ? [{ title: "类型", dataIndex: "category", width: 150, render: (value: unknown) => <Tag>{categoryLabel(String(value))}</Tag> } as ProColumns<CatalogItem<CatalogData>>] : []),
    { title: "排序", dataIndex: "sort", width: 80 },
    { title: "状态", dataIndex: "enabled", width: 100, render: (_value, item) => <Switch size="small" checked={item.enabled} checkedChildren="启用" unCheckedChildren="停用" onChange={async (enabled) => { try { await consoleApi.updateCatalogItem(item.id, { enabled }); message.success("状态已更新"); await load(); } catch (reason) { message.error(reason instanceof Error ? reason.message : "更新失败"); } }} /> },
    { title: "操作", valueType: "option", width: 150, render: (_value, item) => <Space><Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEditor(item)}>编辑</Button><Popconfirm title={`删除此${activeItemLabel}？`} onConfirm={async () => { try { await consoleApi.deleteCatalogItem(item.id); message.success(`${activeItemLabel}已删除`); await load(); } catch (reason) { message.error(reason instanceof Error ? reason.message : "删除失败"); } }}><Button type="link" danger size="small" icon={<DeleteOutlined />}>删除</Button></Popconfirm></Space> },
  ];

  const tabs = [
    { key: "gallery", label: config.galleryLabel },
    { key: "manage", label: config.manageLabel },
    ...(config.recommendation ? [{ key: "recommendations", label: "推荐位管理" }] : []),
  ];
  const watchedCategory = Form.useWatch("category", form);
  const currentCategory = watchedCategory || editor?.category || categories[0];
  const typed = isTypedCategory(currentCategory);

  return (
    <PageContainer title={config.title} subTitle={config.subtitle} extra={tab !== "gallery" ? <Button type="primary" icon={<PlusOutlined />} onClick={() => openEditor(null)}>新增{activeItemLabel}</Button> : undefined} header={{ breadcrumb: { items: [{ title: "能力中心" }, { title: config.title }] } }}>
      <Tabs className="catalog-tabs" activeKey={tab} items={tabs} onChange={(key) => { const next = key as TabKey; setTab(next); const url = new URL(window.location.href); url.searchParams.set("tab", next); history.replaceState(null, "", url); }} />
      {tab === "gallery" ? (
        <Card loading={loading} title={config.galleryTitle} extra={<Input.Search allowClear placeholder={`搜索${config.itemLabel}`} value={query} onChange={(event) => setQuery(event.target.value)} />}>
          {visible.length ? <Row gutter={[16, 16]}>{visible.map((item) => <Col xs={24} md={12} xl={8} key={item.id}><Card size="small" className="catalog-card"><Space align="start"><Avatar shape="square" size={44}>{String(objectData(item).icon || objectData(item).avatar || titleOf(item).slice(0, 1))}</Avatar><div><Typography.Title level={5}>{titleOf(item)}</Typography.Title><Typography.Paragraph type="secondary" ellipsis={{ rows: 2 }}>{descriptionOf(item)}</Typography.Paragraph><Space wrap>{slugOf(item) && <Tag>{slugOf(item)}</Tag>}<Tag color="green">已启用</Tag></Space></div></Space></Card></Col>)}</Row> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={`暂无可用${config.itemLabel}`} />}
        </Card>
      ) : <ProTable<CatalogItem<CatalogData>> rowKey="id" columns={columns} dataSource={visible} loading={loading} search={false} options={{ reload: () => void load(), density: true, setting: true }} toolBarRender={() => [<Input.Search key="search" allowClear placeholder="搜索名称、标识或简介" value={query} onChange={(event) => setQuery(event.target.value)} />]} />}
      <Drawer width={760} open={Boolean(editor)} title={editor?.item ? `编辑 ${titleOf(editor.item)}` : `新增${activeItemLabel}`} onClose={() => setEditor(null)} destroyOnHidden extra={<Button type="primary" onClick={() => form.submit()}>保存</Button>}>
        <Form form={form} layout="vertical" onFinish={(values) => void save(values)} onValuesChange={syncJsonFromForm}>
          <Form.Item name="category" label="定义类型" rules={[{ required: true }]}><Select disabled={Boolean(editor?.item)} options={categories.map((value) => ({ value, label: categoryLabel(value) }))} /></Form.Item>
          <Form.Item name="sort" label="排序"><InputNumber min={0} precision={0} className="full-width" /></Form.Item>
          {currentCategory === "EXPERT_DEFS" && <>
            <Alert type="info" showIcon message="专家定义会影响运行时 Persona；slug 创建后不可修改。" />
            <Divider />
            <Row gutter={16}>
              <Col xs={24} md={16}><Form.Item name="name" label="名称" rules={[{ required: true, whitespace: true, message: "请输入专家名称" }]}><Input maxLength={120} placeholder="创业伙伴" /></Form.Item></Col>
              <Col xs={24} md={8}><Form.Item name="avatar" label="头像"><Input maxLength={8} placeholder="🚀" /></Form.Item></Col>
            </Row>
            <Form.Item name="slug" label="slug（稳定身份）" rules={[{ required: true, pattern: /^[A-Za-z0-9][A-Za-z0-9._-]*$/, message: "仅允许字母、数字与 . _ -" }]}><Input disabled={Boolean(editor?.item)} maxLength={120} placeholder="entrepreneur-partner" /></Form.Item>
            <Form.Item name="subtitle" label="副标题"><Input maxLength={120} placeholder="林正刚" /></Form.Item>
            <Form.Item name="intro" label="简介"><Input.TextArea rows={3} maxLength={500} showCount /></Form.Item>
            <Form.Item name="persona" label="Persona（运行提示词）" rules={[{ required: true, whitespace: true, message: "请输入 Persona" }]}><Input.TextArea rows={6} maxLength={5000} showCount /></Form.Item>
            <Form.Item name="tags" label="标签"><Select mode="tags" tokenSeparators={[",", "，"]} placeholder="输入标签后回车" /></Form.Item>
            <Form.Item name="expertCategory" label="分类"><Input maxLength={80} placeholder="OPC·一人公司" /></Form.Item>
            <Form.Item name="functional" label="运行状态" valuePropName="checked"><Switch checkedChildren="可运行" unCheckedChildren="仅展示" /></Form.Item>
          </>}
          {currentCategory === "CONN_DEFS" && <>
            <Alert type="info" showIcon message="连接器只维护公开启动定义；真实 token 和密码永远保存在本机 backend。" />
            <Divider />
            <Row gutter={16}>
              <Col xs={24} md={16}><Form.Item name="name" label="名称" rules={[{ required: true, whitespace: true, message: "请输入连接器名称" }]}><Input maxLength={120} placeholder="GitHub" /></Form.Item></Col>
              <Col xs={24} md={8}><Form.Item name="icon" label="图标"><Input maxLength={8} placeholder="🐙" /></Form.Item></Col>
            </Row>
            <Form.Item name="slug" label="slug（稳定身份）" rules={[{ required: true, pattern: /^[A-Za-z0-9][A-Za-z0-9._-]*$/, message: "仅允许字母、数字与 . _ -" }]}><Input disabled={Boolean(editor?.item)} maxLength={120} placeholder="github" /></Form.Item>
            <Form.Item name="desc" label="说明"><Input.TextArea rows={3} maxLength={500} showCount /></Form.Item>
            <Row gutter={16}>
              <Col xs={24} md={12}><Form.Item name="status" label="状态" rules={[{ required: true }]}><Select options={[{ value: "rdy", label: "rdy · 内置即用" }, { value: "tok", label: "tok · 需要凭据或 CLI" }]} /></Form.Item></Col>
              <Col xs={24} md={12}><Form.Item name="launchMode" label="启动方式" rules={[{ required: true }]}><Radio.Group options={[{ value: "builtin", label: "内置服务" }, { value: "stdio", label: "第三方 stdio" }]} /></Form.Item></Col>
            </Row>
            {typed && <Form.Item noStyle shouldUpdate={(prev, next) => prev.launchMode !== next.launchMode}>
              {({ getFieldValue }) => getFieldValue("launchMode") === "builtin" ? <>
                <Form.Item name="builtinServer" label="内置服务" rules={[{ required: true, message: "请选择内置服务" }]}><Select options={BUILTIN_SERVERS.map((value) => ({ value, label: value }))} placeholder="选择随 App 交付的服务" /></Form.Item>
                <StringListField name="requires" label="所需环境变量" placeholder="TELEGRAM_BOT_TOKEN" help="仅填写变量名；运行时缺失会明确跳过连接器。" />
                <StringListField name="requiresBin" label="所需本机 CLI" placeholder="kdocs-cli" />
              </> : <>
                <Form.Item name="command" label="启动命令" rules={[{ required: true, whitespace: true, message: "请输入启动命令" }]}><Input placeholder="npx" /></Form.Item>
                <StringListField name="launchArgs" label="命令参数" placeholder="-y 或 @modelcontextprotocol/server-github" />
                <StringListField name="requires" label="所需环境变量" placeholder="GITHUB_TOKEN" />
                <StringListField name="requiresBin" label="所需本机 CLI" placeholder="git" />
                <SecretEnvField />
              </>}
            </Form.Item>}
          </>}
          {!typed && <Alert type="info" showIcon message="该目录类型暂使用高级 JSON 编辑；专家和连接器定义已提供字段化表单。" />}
          <Collapse className="drawer-form" items={[{ key: "advanced", label: typed ? "高级 JSON（可选）" : "定义 JSON", children: <Space direction="vertical" className="full-width" size={10}>
            <Typography.Text type="secondary">{typed ? "表单修改会自动生成 JSON；如需维护扩展字段，可编辑 JSON 后点击“应用到表单”。" : "该目录类型由 Server 按真实定义结构校验。"}</Typography.Text>
            <Input.TextArea value={advancedJson} status={jsonError ? "error" : undefined} onChange={(event) => { setAdvancedJson(event.target.value); setJsonDirty(true); setJsonError(""); }} rows={typed ? 12 : 22} className="code-input" spellCheck={false} />
            {jsonError && <Typography.Text type="danger">{jsonError}</Typography.Text>}
            {typed && <Button onClick={applyAdvancedJson}>应用 JSON 到表单</Button>}
          </Space> }]} />
        </Form>
      </Drawer>
    </PageContainer>
  );
}
