import { App, Button, Drawer, Form, Input, InputNumber, Popconfirm, Select, Space, Switch, Tag, Typography } from "antd";
import { DeleteOutlined, EditOutlined, PlusOutlined } from "@ant-design/icons";
import { PageContainer, ProTable } from "@ant-design/pro-components";
import type { ProColumns } from "@ant-design/pro-components";
import { useEffect, useMemo, useState } from "react";
import { consoleApi } from "../api";
import type { CatalogData, CatalogItem } from "../types";

export default function RawCatalogPage() {
  const { message } = App.useApp();
  const [items, setItems] = useState<CatalogItem<CatalogData>[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string>();
  const [editor, setEditor] = useState<CatalogItem<CatalogData> | null | undefined>(undefined);
  const [form] = Form.useForm<{ category: string; sort: number; data: string }>();
  async function load() { setLoading(true); try { setItems((await consoleApi.catalog(undefined, true)).items || []); } catch (reason) { message.error(reason instanceof Error ? reason.message : "目录加载失败"); } finally { setLoading(false); } }
  useEffect(() => { void load(); }, []);
  const categories = useMemo(() => [...new Set(items.map((item) => item.category))].sort(), [items]);
  const visible = items.filter((item) => (!category || item.category === category) && (!query || `${item.category} ${JSON.stringify(item.data)}`.toLowerCase().includes(query.toLowerCase())));
  function open(item: CatalogItem<CatalogData> | null) { setEditor(item); form.setFieldsValue({ category: item?.category || "", sort: item?.sort || 0, data: JSON.stringify(item?.data || {}, null, 2) }); }
  const columns: ProColumns<CatalogItem<CatalogData>>[] = [
    { title: "分类", dataIndex: "category", width: 190, render: (value) => <Tag>{String(value)}</Tag> },
    { title: "数据", dataIndex: "data", ellipsis: true, render: (_value, item) => <Typography.Text code>{JSON.stringify(item.data)}</Typography.Text> },
    { title: "版本", dataIndex: "version", width: 80 },
    { title: "排序", dataIndex: "sort", width: 80 },
    { title: "启用", dataIndex: "enabled", width: 80, render: (_value, item) => <Switch size="small" checked={item.enabled} onChange={async (enabled) => { await consoleApi.updateCatalogItem(item.id, { enabled }); await load(); }} /> },
    { title: "操作", valueType: "option", width: 150, render: (_value, item) => <Space><Button type="link" size="small" icon={<EditOutlined />} onClick={() => open(item)}>编辑</Button><Popconfirm title="删除此目录项？" onConfirm={async () => { try { await consoleApi.deleteCatalogItem(item.id); message.success("已删除"); await load(); } catch (reason) { message.error(reason instanceof Error ? reason.message : "删除失败"); } }}><Button type="link" danger size="small" icon={<DeleteOutlined />}>删除</Button></Popconfirm></Space> },
  ];
  return (
    <PageContainer title="高级 JSON" subTitle="直接维护 Server 下发的裸目录项" extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => open(null)}>新增目录项</Button>} header={{ breadcrumb: { items: [{ title: "系统" }, { title: "高级 JSON" }] } }}>
      <ProTable<CatalogItem<CatalogData>> rowKey="id" columns={columns} dataSource={visible} loading={loading} search={false} scroll={{ x: 900 }} options={{ reload: () => void load(), density: true, setting: true }} toolBarRender={() => [<Input.Search key="search" allowClear placeholder="搜索分类或 JSON" value={query} onChange={(event) => setQuery(event.target.value)} />, <Select key="category" allowClear placeholder="全部分类" value={category} options={categories.map((value) => ({ value, label: value }))} onChange={setCategory} />]} />
      <Drawer width={720} open={editor !== undefined} title={editor ? "编辑目录项" : "新增目录项"} onClose={() => setEditor(undefined)} destroyOnHidden extra={<Button type="primary" onClick={() => form.submit()}>保存</Button>}>
        <Form form={form} layout="vertical" onFinish={async (values) => { let data: CatalogData; try { data = JSON.parse(values.data) as CatalogData; } catch { message.error("JSON 格式无效"); return; } try { if (editor) await consoleApi.updateCatalogItem(editor.id, { data, sort: values.sort }); else await consoleApi.createCatalogItem(values.category, data, values.sort); message.success("目录项已保存"); setEditor(undefined); await load(); } catch (reason) { message.error(reason instanceof Error ? reason.message : "保存失败"); } }}>
          <Form.Item name="category" label="分类" rules={[{ required: true, whitespace: true }]}><Input disabled={Boolean(editor)} /></Form.Item>
          <Form.Item name="sort" label="排序"><InputNumber min={0} precision={0} className="full-width" /></Form.Item>
          <Form.Item name="data" label="JSON 数据" rules={[{ required: true }]}><Input.TextArea rows={24} className="code-input" spellCheck={false} /></Form.Item>
        </Form>
      </Drawer>
    </PageContainer>
  );
}
