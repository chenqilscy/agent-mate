import {
  App,
  Avatar,
  Button,
  Dropdown,
  Input,
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
      extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setEditor({ item: null, tab: "info" })}>新增技能</Button>}
      header={{ breadcrumb: { items: [{ title: "目录" }, { title: "技能" }] } }}
    >
      <Tabs
        activeKey="manage"
        className="catalog-tabs"
        items={[
          { key: "gallery", label: "目录预览" },
          { key: "manage", label: "目录管理" },
          { key: "recommendations", label: "推荐位管理" },
        ]}
        onChange={(key) => {
          if (key !== "manage") window.location.href = `/legacy/catalog/skills?tab=${key}`;
        }}
      />
      <ProTable<CatalogItem<SkillData>>
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
      />
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
