import { DeleteOutlined, EditOutlined, PlusOutlined } from "@ant-design/icons";
import { App, Avatar, Button, Col, Drawer, Form, Input, InputNumber, Popconfirm, Row, Space, Switch, Tag, Typography } from "antd";
import { ProTable } from "@ant-design/pro-components";
import type { ProColumns } from "@ant-design/pro-components";
import { useState } from "react";
import { IconPicker } from "../../src/components/ui/IconPicker";
import { consoleApi } from "./api";
import type { CatalogItem, SkillCategoryData, SkillData } from "./types";

interface CategoryFormValues extends SkillCategoryData {
  sort: number;
}

export default function SkillCategories({
  categories,
  skills,
  loading,
  reload,
}: {
  categories: CatalogItem<SkillCategoryData>[];
  skills: CatalogItem<SkillData>[];
  loading: boolean;
  reload: () => Promise<void>;
}) {
  const { message } = App.useApp();
  const [form] = Form.useForm<CategoryFormValues>();
  const [editing, setEditing] = useState<CatalogItem<SkillCategoryData> | null | undefined>(undefined);
  const [saving, setSaving] = useState(false);

  function open(item: CatalogItem<SkillCategoryData> | null) {
    setEditing(item);
    form.setFieldsValue({
      slug: item?.data.slug || "",
      name: item?.data.name || "",
      icon: item?.data.icon || "🧩",
      description: item?.data.description || "",
      sort: item?.sort ?? categories.length * 10,
    });
  }

  async function save(values: CategoryFormValues) {
    const { sort, ...data } = values;
    setSaving(true);
    try {
      if (editing) await consoleApi.updateCatalogItem(editing.id, { data, sort });
      else await consoleApi.createCatalogItem("SKILL_CATEGORIES", data, sort);
      message.success(editing ? "分类已更新" : "分类已创建");
      setEditing(undefined);
      await reload();
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : "分类保存失败");
    } finally {
      setSaving(false);
    }
  }

  const columns: ProColumns<CatalogItem<SkillCategoryData>>[] = [
    {
      title: "分类",
      width: 320,
      render: (_value, item) => (
        <Space>
          <Avatar shape="square">{item.data.icon || "🧩"}</Avatar>
          <div>
            <Typography.Text strong>{item.data.name}</Typography.Text>
            <div><Typography.Text type="secondary">{item.data.description || "暂无说明"}</Typography.Text></div>
          </div>
        </Space>
      ),
    },
    { title: "slug", width: 170, render: (_value, item) => <Typography.Text code copyable>{item.data.slug}</Typography.Text> },
    {
      title: "技能数",
      width: 90,
      align: "center",
      render: (_value, item) => skills.filter((skill) => skill.data.category_slug === item.data.slug).length,
    },
    { title: "排序", dataIndex: "sort", width: 80, align: "center" },
    {
      title: "状态",
      width: 110,
      render: (_value, item) => (
        <Switch
          size="small"
          checked={item.enabled}
          checkedChildren="启用"
          unCheckedChildren="停用"
          aria-label={`${item.data.name}分类状态`}
          onChange={async (enabled) => {
            try {
              await consoleApi.updateCatalogItem(item.id, { enabled });
              await reload();
            } catch (reason) {
              message.error(reason instanceof Error ? reason.message : "分类状态更新失败");
            }
          }}
        />
      ),
    },
    {
      title: "操作",
      valueType: "option",
      width: 150,
      render: (_value, item) => (
        <Space size={4}>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => open(item)}>编辑</Button>
          <Popconfirm
            title="删除这个分类？"
            description="仍被 Skill 或发布版本引用时，Server 会拒绝删除。"
            okButtonProps={{ danger: true }}
            onConfirm={async () => {
              try {
                await consoleApi.deleteCatalogItem(item.id);
                message.success("分类已删除");
                await reload();
              } catch (reason) {
                message.error(reason instanceof Error ? reason.message : "分类删除失败");
              }
            }}
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return <>
    <ProTable<CatalogItem<SkillCategoryData>>
      rowKey="id"
      columns={columns}
      dataSource={categories}
      loading={loading}
      search={false}
      pagination={false}
      scroll={{ x: 920 }}
      cardBordered
      options={{ density: true, reload: () => void reload(), setting: true }}
      locale={{ emptyText: "还没有技能分类" }}
      toolBarRender={() => [<Button key="new" type="primary" icon={<PlusOutlined />} onClick={() => open(null)}>新增分类</Button>]}
    />
    <Drawer
      size={620}
      open={editing !== undefined}
      title={editing ? `编辑分类 · ${editing.data.name}` : "新增技能分类"}
      onClose={() => setEditing(undefined)}
      destroyOnHidden
      extra={<Button type="primary" loading={saving} onClick={() => form.submit()}>保存</Button>}
    >
      <Form<CategoryFormValues> form={form} layout="vertical" requiredMark="optional" onFinish={(values) => void save(values)}>
        <Row gutter={16}>
          <Col xs={24} md={14}>
            <Form.Item name="slug" label="slug（稳定身份）" rules={[
              { required: true, message: "请输入 slug" },
              { pattern: /^[A-Za-z0-9][A-Za-z0-9._-]*$/, message: "仅允许字母、数字与 . _ -" },
            ]}>
              <Input disabled={Boolean(editing)} maxLength={80} placeholder="office" />
            </Form.Item>
          </Col>
          <Col xs={24} md={10}>
            <Form.Item name="sort" label="排序" rules={[{ required: true }]}>
              <InputNumber min={0} precision={0} className="full-width" />
            </Form.Item>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col xs={24} md={8}><Form.Item name="icon" label="图标"><IconPicker ariaLabel="选择分类图标" /></Form.Item></Col>
          <Col xs={24} md={16}><Form.Item name="name" label="名称" rules={[{ required: true, whitespace: true, message: "请输入分类名称" }]}><Input maxLength={80} /></Form.Item></Col>
        </Row>
        <Form.Item name="description" label="说明"><Input.TextArea rows={4} maxLength={500} showCount /></Form.Item>
        {editing && <Space wrap><Tag>{editing.enabled ? "当前启用" : "当前停用"}</Tag><Typography.Text type="secondary">slug 创建后不可修改；分类名称可以安全调整。</Typography.Text></Space>}
      </Form>
    </Drawer>
  </>;
}
