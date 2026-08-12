import {
  Alert,
  App,
  Avatar,
  Button,
  Card,
  Col,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Input,
  Modal,
  Pagination,
  Popconfirm,
  Row,
  Select,
  Space,
  Spin,
  Tabs,
  Tag,
  Timeline,
  Typography,
  Upload,
} from "antd";
import { CompatList as List } from "../components/CompatList";
import { IconPicker } from "../../../src/components/ui/IconPicker";
import {
  ArrowLeftOutlined,
  CloudUploadOutlined,
  FileTextOutlined,
  PlusOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import { PageContainer, ProTable } from "@ant-design/pro-components";
import type { ProColumns } from "@ant-design/pro-components";
import { useCallback, useEffect, useRef, useState } from "react";
import { consoleApi } from "../api";
import {
  ProjectGantt,
  ProjectIterations,
  ProjectAnalytics,
  ProjectOverview,
  ProjectPlan,
  ProjectTasks,
  ProjectWorkload,
  ProjectWorkspaceActions,
  ProjectWorkProvider,
} from "../components/project/ProjectWorkspace";
import type { ProjectWorkspaceTab } from "../components/project/ProjectWorkspace";
import { ProjectGovernance } from "../components/project/ProjectGovernance";
import { navigate } from "../router";
import type {
  CatalogData,
  CatalogItem,
  AssetRecord,
  CommentRecord,
  KnowledgeBase,
  KnowledgeDocument,
  KnowledgeSearchHit,
  Member,
  Project,
  TimelineEvent,
} from "../types";

const ROLE_OPTIONS = ["Admin", "Member", "Viewer"].map((value) => ({
  value,
  label: value,
}));
const PROJECT_TABS: readonly ProjectWorkspaceTab[] = [
  "overview",
  "analytics",
  "plan",
  "backlog",
  "tasks",
  "workload",
  "milestones",
  "sprints",
  "gantt",
  "iterations",
  "governance",
  "knowledge",
  "assets",
  "collab",
  "config",
];
type ProjectWorkspaceSection =
  | "overview"
  | "analytics"
  | "work"
  | "planning"
  | "team"
  | "governance"
  | "knowledge"
  | "assets"
  | "config";
const PROJECT_SECTION_BY_TAB: Record<
  ProjectWorkspaceTab,
  ProjectWorkspaceSection
> = {
  overview: "overview",
  analytics: "analytics",
  plan: "work",
  backlog: "work",
  tasks: "work",
  workload: "team",
  milestones: "planning",
  sprints: "planning",
  gantt: "planning",
  iterations: "planning",
  governance: "governance",
  knowledge: "knowledge",
  assets: "assets",
  collab: "team",
  config: "config",
};
const PROJECT_SECTION_DEFAULT: Record<
  ProjectWorkspaceSection,
  ProjectWorkspaceTab
> = {
  overview: "overview",
  analytics: "analytics",
  work: "plan",
  planning: "milestones",
  team: "workload",
  governance: "governance",
  knowledge: "knowledge",
  assets: "assets",
  config: "config",
};

function requestedProjectTab(): ProjectWorkspaceTab {
  const requested = new URLSearchParams(window.location.search).get("tab");
  return PROJECT_TABS.includes(requested as ProjectWorkspaceTab)
    ? (requested as ProjectWorkspaceTab)
    : "overview";
}
function errorText(reason: unknown, fallback: string): string {
  return reason instanceof Error ? reason.message : fallback;
}
function canWrite(project: Project): boolean {
  return project.role !== "Viewer" && !project.archived_at;
}
function canManage(project: Project): boolean {
  return (
    (project.role === "Owner" || project.role === "Admin") &&
    !project.archived_at
  );
}

export default function ProjectDetailPage({
  projectId,
}: {
  projectId: string;
}) {
  const { message } = App.useApp();
  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<ProjectWorkspaceTab>(requestedProjectTab);
  async function load() {
    setLoading(true);
    try {
      setProject(await consoleApi.project(projectId));
    } catch (reason) {
      message.error(errorText(reason, "项目加载失败"));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void load();
  }, [projectId]);
  useEffect(() => {
    const syncTabFromUrl = () => {
      const url = new URL(window.location.href);
      const requested = url.searchParams.get("tab");
      const next = requestedProjectTab();
      setTab(next);
      if (
        requested &&
        !PROJECT_TABS.includes(requested as ProjectWorkspaceTab)
      ) {
        url.searchParams.delete("tab");
        window.history.replaceState(null, "", url);
      }
    };
    syncTabFromUrl();
    window.addEventListener("popstate", syncTabFromUrl);
    return () => window.removeEventListener("popstate", syncTabFromUrl);
  }, [projectId]);

  const selectProjectTab = useCallback(
    (next: ProjectWorkspaceTab) => {
      if (next === tab) return;
      setTab(next);
      const url = new URL(window.location.href);
      if (next === "overview") url.searchParams.delete("tab");
      else url.searchParams.set("tab", next);
      window.history.pushState(null, "", url);
    },
    [tab],
  );
  const renderProjectView = (view: ProjectWorkspaceTab) => {
    switch (view) {
      case "overview":
        return <ProjectOverview />;
      case "analytics":
        return <ProjectAnalytics />;
      case "plan":
        return <ProjectPlan />;
      case "backlog":
        return <ProjectTasks scope="backlog" />;
      case "tasks":
        return <ProjectTasks scope="all" />;
      case "workload":
        return <ProjectWorkload />;
      case "gantt":
        return <ProjectGantt />;
      case "milestones":
        return <ProjectIterations sectionOnly="milestones" />;
      case "sprints":
        return <ProjectIterations sectionOnly="sprints" />;
      case "iterations":
        return <ProjectIterations sectionOnly="fields" />;
      case "governance":
        return project ? <ProjectGovernance project={project} /> : null;
      case "knowledge":
        return project ? <KnowledgeTab project={project} /> : null;
      case "assets":
        return project ? <AssetsTab project={project} /> : null;
      case "collab":
        return project ? <CollaborationTab project={project} /> : null;
      case "config":
        return project ? (
          <ConfigTab
            project={project}
            onSaved={load}
            onNavigateKnowledge={() => selectProjectTab("knowledge")}
          />
        ) : null;
    }
  };
  const renderProjectSection = (
    views: Array<{ key: ProjectWorkspaceTab; label: string }>,
  ) =>
    views.length === 1 ? (
      renderProjectView(views[0].key)
    ) : (
      <Tabs
        className="project-workspace-subtabs"
        activeKey={tab}
        onChange={(key) => selectProjectTab(key as ProjectWorkspaceTab)}
        more={{ trigger: "click" }}
        items={views.map((view) => ({
          ...view,
          children: renderProjectView(view.key),
        }))}
      />
    );
  const activeSection = PROJECT_SECTION_BY_TAB[tab];
  return (
    <PageContainer
      title={project?.name || "项目"}
      subTitle={project?.instruction || "未设置项目指令"}
      loading={loading}
      tags={
        project ? (
          <Space>
            <Tag color={project.role === "Viewer" ? "default" : "green"}>
              {project.role}
              {project.role === "Viewer" ? " · 只读" : ""}
            </Tag>
            {project.archived_at > 0 && <Tag color="orange">已归档 · 只读</Tag>}
          </Space>
        ) : undefined
      }
      extra={
        <Button
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate("/projects")}
        >
          返回项目
        </Button>
      }
      header={{
        breadcrumb: {
          items: [
            { title: "工作区" },
            { title: "项目", onClick: () => navigate("/projects") },
            { title: project?.name || projectId },
          ],
        },
      }}
    >
      {project ? (
        <ProjectWorkProvider
          project={project}
          onNavigateTab={selectProjectTab}
        >
          <Tabs
            className="project-workspace-tabs"
            activeKey={activeSection}
            onChange={(key) =>
              selectProjectTab(
                PROJECT_SECTION_DEFAULT[key as ProjectWorkspaceSection],
              )
            }
            more={{ trigger: "click" }}
            tabBarExtraContent={<ProjectWorkspaceActions activeTab={tab} />}
            items={[
              {
                key: "overview",
                label: "概览",
                children: renderProjectSection([
                  { key: "overview", label: "概览" },
                ]),
              },
              {
                key: "analytics",
                label: "数据",
                children: renderProjectSection([
                  { key: "analytics", label: "执行分析" },
                ]),
              },
              {
                key: "work",
                label: "任务",
                children: renderProjectSection([
                  { key: "plan", label: "当前 Sprint" },
                  { key: "backlog", label: "Backlog" },
                  { key: "tasks", label: "全部任务" },
                ]),
              },
              {
                key: "planning",
                label: "计划",
                children: renderProjectSection([
                  { key: "milestones", label: "里程碑" },
                  { key: "sprints", label: "Sprint" },
                  { key: "gantt", label: "时间线" },
                  { key: "iterations", label: "字段" },
                ]),
              },
              {
                key: "team",
                label: "团队",
                children: renderProjectSection([
                  { key: "workload", label: "负载" },
                  { key: "collab", label: "协作" },
                ]),
              },
              {
                key: "governance",
                label: "治理",
                children: renderProjectSection([
                  { key: "governance", label: "风险与决策" },
                ]),
              },
              {
                key: "knowledge",
                label: "知识",
                children: renderProjectSection([
                  { key: "knowledge", label: "知识库" },
                ]),
              },
              {
                key: "assets",
                label: "资产",
                children: renderProjectSection([
                  { key: "assets", label: "Server 资产" },
                ]),
              },
              {
                key: "config",
                label: "设置",
                children: renderProjectSection([
                  { key: "config", label: "项目设置" },
                ]),
              },
            ]}
          />
        </ProjectWorkProvider>
      ) : (
        !loading && <Empty description="项目不存在或无权访问" />
      )}
    </PageContainer>
  );
}

function formatAssetSize(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 * 1024 * 1024)
    return `${(value / 1024 / 1024).toFixed(1)} MB`;
  return `${(value / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

function AssetsTab({ project }: { project: Project }) {
  const { message } = App.useApp();
  const [items, setItems] = useState<AssetRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await consoleApi.projectAssets(project.id);
      setItems(result.assets || []);
    } catch (reason) {
      message.error(errorText(reason, "Server 资产加载失败"));
    } finally {
      setLoading(false);
    }
  }, [message, project.id]);
  useEffect(() => {
    void load();
  }, [load]);
  const columns: ProColumns<AssetRecord>[] = [
    {
      title: "资产",
      dataIndex: "name",
      render: (_value, item) => (
        <Space>
          <FileTextOutlined />
          <div>
            <Typography.Text strong>{item.name}</Typography.Text>
            <div>
              <Typography.Text type="secondary">
                {item.mime_type} · {formatAssetSize(item.size)}
              </Typography.Text>
            </div>
          </div>
        </Space>
      ),
    },
    {
      title: "存储",
      dataIndex: "storage_state",
      width: 130,
      render: (_value, item) =>
        item.storage_state === "committed" ? (
          <Tag color="green">Server 已提交</Tag>
        ) : item.storage_state === "uploading" ? (
          <Tag color="processing">上传中</Tag>
        ) : (
          <Tag>仅元数据</Tag>
        ),
    },
    {
      title: "完整性",
      dataIndex: "validation_status",
      width: 130,
      render: (_value, item) =>
        item.validation_status === "verified" ? (
          <Tag color="blue">哈希已核验</Tag>
        ) : (
          <Tag color="orange">待核验</Tag>
        ),
    },
    {
      title: "SHA-256",
      dataIndex: "sha256",
      width: 150,
      render: (value) => (
        <Typography.Text code copyable={{ text: String(value || "") }}>
          {String(value || "").slice(0, 12) || "-"}
        </Typography.Text>
      ),
    },
    {
      title: "更新时间",
      dataIndex: "updated_at",
      width: 180,
      render: (value) =>
        value ? new Date(Number(value) * 1000).toLocaleString("zh-CN") : "-",
    },
    {
      title: "操作",
      valueType: "option",
      width: 150,
      render: (_value, item) => [
        <Button
          key="download"
          type="link"
          size="small"
          disabled={item.storage_state !== "committed"}
          onClick={async () => {
            try {
              await consoleApi.downloadAsset(item);
            } catch (reason) {
              message.error(errorText(reason, "资产下载失败"));
            }
          }}
        >
          下载
        </Button>,
        canWrite(project) ? (
          <Popconfirm
            key="delete"
            title="删除 Server 资产引用？"
            description="不会删除任何设备上的外部原文件。"
            onConfirm={async () => {
              try {
                await consoleApi.deleteAsset(item);
                message.success("Server 资产引用已删除");
                await load();
              } catch (reason) {
                message.error(errorText(reason, "资产删除失败"));
              }
            }}
          >
            <Button type="link" danger size="small">
              删除
            </Button>
          </Popconfirm>
        ) : null,
      ],
    },
  ];
  return (
    <ProTable<AssetRecord>
      rowKey="id"
      columns={columns}
      dataSource={items}
      loading={loading}
      search={false}
      options={{ reload: () => void load(), density: true }}
      pagination={{ pageSize: 20 }}
      locale={{ emptyText: "暂无已提交的 Server 资产" }}
    />
  );
}

function KnowledgeTab({ project }: { project: Project }) {
  const { message } = App.useApp();
  const [items, setItems] = useState<KnowledgeBase[]>([]);
  const [loading, setLoading] = useState(true);
  const [configured, setConfigured] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [editingKb, setEditingKb] = useState<KnowledgeBase | null>(null);
  const [selected, setSelected] = useState<KnowledgeBase | null>(null);
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [docLoading, setDocLoading] = useState(false);
  const [docError, setDocError] = useState("");
  const [docPage, setDocPage] = useState(1);
  const [docPageSize, setDocPageSize] = useState(10);
  const [docTotal, setDocTotal] = useState(0);
  const [docSearch, setDocSearch] = useState("");
  const [docKeyword, setDocKeyword] = useState("");
  const [testQuery, setTestQuery] = useState("");
  const [testLoading, setTestLoading] = useState(false);
  const [testHits, setTestHits] = useState<KnowledgeSearchHit[]>([]);
  const [testRan, setTestRan] = useState(false);
  const docRequest = useRef(0);
  const [form] = Form.useForm<Partial<KnowledgeBase> & { name: string }>();
  async function load() {
    setLoading(true);
    try {
      const result = await consoleApi.knowledgeBases(project.id);
      setItems(result.items || []);
      setConfigured(result.configured);
    } catch (reason) {
      message.error(errorText(reason, "知识库加载失败"));
    } finally {
      setLoading(false);
    }
  }
  const fetchDocuments = useCallback(
    async (
      kbId: string,
      page: number,
      pageSize: number,
      keyword: string,
      silent = false,
    ) => {
      const requestId = ++docRequest.current;
      if (!silent) {
        setDocLoading(true);
        setDocError("");
      }
      try {
        const result = await consoleApi.knowledgeDocuments(
          project.id,
          kbId,
          page,
          pageSize,
          keyword,
        );
        if (requestId !== docRequest.current) return;
        setDocuments(result.items || []);
        setDocTotal(result.total || 0);
        setDocError("");
      } catch (reason) {
        if (requestId !== docRequest.current) return;
        const detail = errorText(reason, "文档加载失败");
        setDocError(detail);
        if (!silent) message.error(detail);
      } finally {
        if (requestId === docRequest.current && !silent) setDocLoading(false);
      }
    },
    [message, project.id],
  );
  function openDocs(kb: KnowledgeBase) {
    setSelected(kb);
    setDocuments([]);
    setDocTotal(0);
    setDocPage(1);
    setDocPageSize(10);
    setDocSearch("");
    setDocKeyword("");
    setDocError("");
    setTestQuery("");
    setTestHits([]);
    setTestRan(false);
    void fetchDocuments(kb.id, 1, 10, "");
  }
  function closeDocs() {
    docRequest.current += 1;
    setSelected(null);
    setDocuments([]);
    setTestHits([]);
    setTestRan(false);
  }
  const hasPendingDocuments = documents.some(
    (doc) => doc.vector_status === 0 && doc.parse_status !== "legacy_pending",
  );
  useEffect(() => {
    if (!selected || !hasPendingDocuments) return;
    const timer = window.setInterval(() => {
      void fetchDocuments(selected.id, docPage, docPageSize, docKeyword, true);
    }, 4000);
    return () => window.clearInterval(timer);
  }, [
    docKeyword,
    docPage,
    docPageSize,
    fetchDocuments,
    hasPendingDocuments,
    selected?.id,
  ]);
  async function runKnowledgeTest() {
    const query = testQuery.trim();
    if (!selected || !query) {
      message.warning("请输入要检索的问题");
      return;
    }
    setTestLoading(true);
    setTestRan(false);
    try {
      const result = await consoleApi.searchProjectKnowledge(project.id, {
        query,
        knowledge_ids: [selected.id],
        top_k: 8,
      });
      setTestHits(result.hits || []);
      setTestRan(true);
    } catch (reason) {
      setTestHits([]);
      setTestRan(false);
      message.error(errorText(reason, "检索测试失败"));
    } finally {
      setTestLoading(false);
    }
  }
  useEffect(() => {
    void load();
  }, [project.id]);
  const columns: ProColumns<KnowledgeBase>[] = [
    {
      title: "知识库",
      dataIndex: "name",
      render: (_value, item) => (
        <Space>
          <Avatar shape="square">{item.icon || "📚"}</Avatar>
          <div>
            <Typography.Text strong>{item.name}</Typography.Text>
            <div>
              <Typography.Text type="secondary">
                {item.description || "暂无简介"}
              </Typography.Text>
            </div>
          </div>
        </Space>
      ),
    },
    {
      title: "状态",
      width: 140,
      render: (_value, item) =>
        item.provider_status === "ready" ? (
          <Tag color="green">WeKnora 已就绪</Tag>
        ) : item.provider_status === "legacy_pending" ? (
          <Tag color="orange">旧库待迁移</Tag>
        ) : item.provider_status === "migrating" ? (
          <Tag color="processing">迁移中</Tag>
        ) : (
          <Tag color="red">暂不可用</Tag>
        ),
    },
    { title: "文档", dataIndex: "doc_count", width: 80 },
    {
      title: "操作",
      valueType: "option",
      width: 260,
      render: (_value, item) => (
        <Space>
          <Button type="link" size="small" onClick={() => openDocs(item)}>
            打开
          </Button>
          {canManage(project) && (
            <Button
              type="link"
              size="small"
              onClick={() => {
                setEditingKb(item);
                form.setFieldsValue(item);
                setCreateOpen(true);
              }}
            >
              编辑
            </Button>
          )}
          {canManage(project) && item.provider_status === "legacy_pending" && (
            <Button
              type="link"
              size="small"
              onClick={async () => {
                try {
                  await consoleApi.migrateKnowledgeBase(project.id, item.id);
                  message.success("旧知识库已提交到中央 WeKnora");
                  await load();
                } catch (reason) {
                  message.error(errorText(reason, "迁移失败"));
                }
              }}
            >
              迁移
            </Button>
          )}
          {canManage(project) && (
            <Popconfirm
              title={`删除知识库“${item.name}”及全部文档？`}
              onConfirm={async () => {
                try {
                  await consoleApi.deleteKnowledgeBase(project.id, item.id);
                  message.success("知识库已删除");
                  await load();
                } catch (reason) {
                  message.error(errorText(reason, "删除失败"));
                }
              }}
            >
              <Button type="link" danger size="small">
                删除
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];
  return (
    <>
      {!configured && (
        <Alert
          type="warning"
          showIcon
          title="中央 WeKnora 尚未配置"
          description="请让平台管理员在 AgentMate Server 部署环境配置 WeKnora 服务凭据；密钥不会下发到 Console 或 AgentMate。"
        />
      )}
      <ProTable<KnowledgeBase>
        rowKey="id"
        columns={columns}
        dataSource={items}
        loading={loading}
        search={false}
        options={{ reload: () => void load(), density: true }}
        toolBarRender={() =>
          canManage(project)
            ? [
                <Button
                  key="new"
                  type="primary"
                  disabled={!configured}
                  icon={<PlusOutlined />}
                  onClick={() => {
                    setEditingKb(null);
                    form.resetFields();
                    form.setFieldsValue({ icon: "📚" });
                    setCreateOpen(true);
                  }}
                >
                  新建知识库
                </Button>,
              ]
            : []
        }
      />
      <Modal
        title={editingKb ? "编辑知识库" : "新建中央知识库"}
        open={createOpen}
        onCancel={() => {
          setCreateOpen(false);
          setEditingKb(null);
        }}
        onOk={() => form.submit()}
        destroyOnHidden
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={async (values) => {
            try {
              if (editingKb)
                await consoleApi.updateKnowledgeBase(
                  project.id,
                  editingKb.id,
                  values,
                );
              else await consoleApi.createKnowledgeBase(project.id, values);
              message.success(
                editingKb ? "知识库已更新" : "知识库已在 WeKnora 创建",
              );
              setCreateOpen(false);
              setEditingKb(null);
              form.resetFields();
              await load();
            } catch (reason) {
              message.error(
                errorText(reason, editingKb ? "更新失败" : "创建失败"),
              );
            }
          }}
        >
          <Row gutter={12}>
            <Col span={6}>
              <Form.Item name="icon" label="图标">
                <IconPicker ariaLabel="选择知识库图标" />
              </Form.Item>
            </Col>
            <Col span={18}>
              <Form.Item
                name="name"
                label="名称"
                rules={[{ required: true, whitespace: true }]}
              >
                <Input />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="description" label="用途简介">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Alert
            type="info"
            showIcon
            title="解析、切片、嵌入与检索均由中央 WeKnora 完成，项目成员无需再配置 API Key。"
          />
        </Form>
      </Modal>
      <Drawer
        size={720}
        open={Boolean(selected)}
        title={
          selected ? `${selected.icon || "📚"} ${selected.name}` : "知识库"
        }
        onClose={closeDocs}
        destroyOnHidden
      >
        {selected && (
          <>
            <Descriptions
              column={1}
              bordered
              size="small"
              items={[
                {
                  key: "desc",
                  label: "用途",
                  children: selected.description || "-",
                },
                {
                  key: "provider",
                  label: "知识服务",
                  children:
                    selected.provider_status === "ready"
                      ? "中央 WeKnora（已就绪）"
                      : selected.provider_error || "旧库待迁移",
                },
                {
                  key: "boundary",
                  label: "凭据边界",
                  children: "WeKnora API Key 仅保存在 AgentMate Server",
                },
              ]}
            />
            <Card
              className="drawer-card"
              title={
                <Space>
                  文档
                  <Typography.Text type="secondary">{docTotal}</Typography.Text>
                  {hasPendingDocuments && (
                    <Tag color="processing">解析中 · 自动刷新</Tag>
                  )}
                </Space>
              }
              extra={
                canWrite(project) &&
                selected.provider_status === "ready" && (
                  <Upload
                    showUploadList={false}
                    beforeUpload={(file) => {
                      void (async () => {
                        try {
                          await consoleApi.uploadKnowledgeDocument(
                            project.id,
                            selected.id,
                            file,
                          );
                          message.success("文档已上传，WeKnora 正在解析");
                          setDocPage(1);
                          setDocSearch("");
                          setDocKeyword("");
                          await Promise.all([
                            fetchDocuments(selected.id, 1, docPageSize, ""),
                            load(),
                          ]);
                        } catch (reason) {
                          message.error(errorText(reason, "上传失败"));
                        }
                      })();
                      return false;
                    }}
                  >
                    <Button icon={<CloudUploadOutlined />}>上传文档</Button>
                  </Upload>
                )
              }
            >
              <Space orientation="vertical" size={12} className="full-width">
                <Input.Search
                  value={docSearch}
                  allowClear
                  placeholder="搜索文档名称"
                  onChange={(event) => setDocSearch(event.target.value)}
                  onSearch={(value) => {
                    const keyword = value.trim();
                    setDocKeyword(keyword);
                    setDocPage(1);
                    void fetchDocuments(selected.id, 1, docPageSize, keyword);
                  }}
                />
                {docError && (
                  <Alert
                    type="error"
                    showIcon
                    title="文档状态刷新失败"
                    description={docError}
                  />
                )}
                <Spin spinning={docLoading}>
                  <List
                    rowKey="id"
                    dataSource={documents}
                    locale={{
                      emptyText: docKeyword ? "没有匹配的文档" : "还没有文档",
                    }}
                    renderItem={(doc) => (
                      <List.Item
                        actions={
                          canWrite(project)
                            ? [
                                <Popconfirm
                                  key="delete"
                                  title="删除此文档？"
                                  onConfirm={async () => {
                                    try {
                                      await consoleApi.deleteKnowledgeDocument(
                                        project.id,
                                        selected.id,
                                        doc.id,
                                      );
                                      message.success("文档已删除");
                                      const nextPage =
                                        documents.length === 1 && docPage > 1
                                          ? docPage - 1
                                          : docPage;
                                      setDocPage(nextPage);
                                      await Promise.all([
                                        fetchDocuments(
                                          selected.id,
                                          nextPage,
                                          docPageSize,
                                          docKeyword,
                                        ),
                                        load(),
                                      ]);
                                    } catch (reason) {
                                      message.error(
                                        errorText(reason, "删除失败"),
                                      );
                                    }
                                  }}
                                >
                                  <Button danger type="link" size="small">
                                    删除
                                  </Button>
                                </Popconfirm>,
                              ]
                            : []
                        }
                      >
                        <List.Item.Meta
                          avatar={<FileTextOutlined />}
                          title={doc.filename}
                          description={`${doc.size ? `${(doc.size / 1024).toFixed(1)} KB · ` : ""}${doc.vector_status === 1 ? "解析完成" : doc.vector_status === 2 ? `失败：${doc.fail_msg || "未知"}` : doc.parse_status === "legacy_pending" ? "旧文档待迁移" : `解析中${doc.parse_status ? `（${doc.parse_status}）` : ""}`}`}
                        />
                      </List.Item>
                    )}
                  />
                </Spin>
                {docTotal > 0 && (
                  <Pagination
                    current={docPage}
                    pageSize={docPageSize}
                    total={docTotal}
                    showSizeChanger
                    pageSizeOptions={[10, 20, 50, 100]}
                    showTotal={(total) => `共 ${total} 个文档`}
                    onChange={(page, pageSize) => {
                      setDocPage(page);
                      setDocPageSize(pageSize);
                      void fetchDocuments(
                        selected.id,
                        page,
                        pageSize,
                        docKeyword,
                      );
                    }}
                  />
                )}
              </Space>
            </Card>
            {selected.provider_status === "ready" && (
              <Card className="drawer-card" title="检索测试">
                <Space orientation="vertical" size={12} className="full-width">
                  <Typography.Text type="secondary">
                    用真实项目检索链路验证当前知识库是否能召回正确内容。
                  </Typography.Text>
                  <Input.Search
                    value={testQuery}
                    allowClear
                    enterButton="检索"
                    loading={testLoading}
                    placeholder="输入问题或关键词"
                    onChange={(event) => setTestQuery(event.target.value)}
                    onSearch={() => void runKnowledgeTest()}
                  />
                  {testRan && (
                    <List
                      rowKey={(hit, index) =>
                        `${hit.metadata?.doc_id || "hit"}-${index}`
                      }
                      dataSource={testHits}
                      locale={{ emptyText: "未检索到匹配内容" }}
                      renderItem={(hit) => (
                        <List.Item>
                          <List.Item.Meta
                            title={
                              <Space>
                                <Typography.Text strong>
                                  {hit.metadata?.doc_name || "未知来源"}
                                </Typography.Text>
                                {typeof hit.score === "number" && (
                                  <Tag>得分 {hit.score.toFixed(3)}</Tag>
                                )}
                              </Space>
                            }
                            description={
                              <Typography.Paragraph
                                ellipsis={{
                                  rows: 5,
                                  expandable: "collapsible",
                                }}
                              >
                                {hit.text}
                              </Typography.Paragraph>
                            }
                          />
                        </List.Item>
                      )}
                    />
                  )}
                </Space>
              </Card>
            )}
          </>
        )}
      </Drawer>
    </>
  );
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
  async function load() {
    const results = await Promise.allSettled([
      consoleApi.projectMembers(project.id),
      consoleApi.presence(project.id),
      consoleApi.comments(project.id),
      consoleApi.timeline(project.id),
    ]);
    if (results[0].status === "fulfilled")
      setMembers(results[0].value.members || []);
    if (results[1].status === "fulfilled")
      setPresence(results[1].value.presence || []);
    if (results[2].status === "fulfilled")
      setComments(results[2].value.comments || []);
    if (results[3].status === "fulfilled")
      setTimeline(results[3].value.events || []);
    const failed = results.filter(
      (result) => result.status === "rejected",
    ).length;
    if (failed)
      message.warning(`有 ${failed} 项协作数据暂时加载失败，其他区域仍可使用`);
  }
  useEffect(() => {
    void load();
  }, [project.id]);
  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} xl={11}>
        <Card
          title="成员"
          extra={<Tag icon={<TeamOutlined />}>{members.length}</Tag>}
        >
          <List
            dataSource={members}
            locale={{ emptyText: "还没有成员" }}
            renderItem={(member) => (
              <List.Item
                actions={
                  canManage(project) && member.role !== "Owner"
                    ? [
                        <Select
                          key="role"
                          size="small"
                          value={member.role}
                          options={ROLE_OPTIONS}
                          onChange={async (role) => {
                            await consoleApi.updateProjectMember(
                              project.id,
                              member.account_id,
                              role,
                            );
                            await load();
                          }}
                        />,
                        <Popconfirm
                          key="remove"
                          title="移除此成员？"
                          onConfirm={async () => {
                            await consoleApi.removeProjectMember(
                              project.id,
                              member.account_id,
                            );
                            await load();
                          }}
                        >
                          <Button type="link" danger size="small">
                            移除
                          </Button>
                        </Popconfirm>,
                      ]
                    : []
                }
              >
                <List.Item.Meta
                  avatar={<Avatar>{member.name.slice(0, 1)}</Avatar>}
                  title={member.name}
                  description={member.email}
                />
                <Tag>{member.role}</Tag>
              </List.Item>
            )}
          />
          {canManage(project) && (
            <Form
              form={memberForm}
              layout="inline"
              className="inline-form"
              initialValues={{ role: "Member" }}
              onFinish={async ({ name, role }) => {
                try {
                  await consoleApi.addProjectMember(project.id, name, role);
                  message.success("成员已加入");
                  memberForm.resetFields();
                  await load();
                } catch (reason) {
                  message.error(errorText(reason, "加入失败"));
                }
              }}
            >
              <Form.Item name="name" rules={[{ required: true }]}>
                <Input placeholder="账号名" />
              </Form.Item>
              <Form.Item name="role">
                <Select options={ROLE_OPTIONS} />
              </Form.Item>
              <Button type="primary" htmlType="submit">
                加入
              </Button>
            </Form>
          )}
        </Card>
        <Card title="邀请码" className="section-card">
          {canManage(project) ? (
            <Space orientation="vertical" className="full-width">
              <Space>
                <Select
                  value={inviteRole}
                  options={ROLE_OPTIONS}
                  id="invite-role"
                  onChange={setInviteRole}
                />
                <Button
                  onClick={async () => {
                    try {
                      setInviteCode(
                        (
                          await consoleApi.inviteProjectMember(
                            project.id,
                            inviteRole,
                          )
                        ).code,
                      );
                    } catch (reason) {
                      message.error(errorText(reason, "生成失败"));
                    }
                  }}
                >
                  生成邀请码
                </Button>
              </Space>
              {inviteCode && (
                <Typography.Text code copyable>
                  {inviteCode}
                </Typography.Text>
              )}
            </Space>
          ) : (
            <Typography.Text type="secondary">
              需要 Admin/Owner 权限
            </Typography.Text>
          )}
        </Card>
        <Card title="在线状态" className="section-card">
          <Space wrap>
            {presence.length ? (
              presence.map((item) => (
                <Tag color="green" key={item.account_id}>
                  {item.name}
                </Tag>
              ))
            ) : (
              <Typography.Text type="secondary">暂无在线成员</Typography.Text>
            )}
          </Space>
        </Card>
      </Col>
      <Col xs={24} xl={13}>
        <Card title="讨论">
          <List
            dataSource={comments}
            locale={{ emptyText: "暂无评论" }}
            renderItem={(comment) => (
              <List.Item>
                <List.Item.Meta
                  avatar={
                    <Avatar>
                      {(
                        comment.author_name ||
                        comment.account_name ||
                        "?"
                      ).slice(0, 1)}
                    </Avatar>
                  }
                  title={comment.author_name || comment.account_name || "成员"}
                  description={
                    <>
                      <Typography.Paragraph>
                        {comment.body}
                      </Typography.Paragraph>
                      <Typography.Text type="secondary">
                        {comment.created_at
                          ? new Date(comment.created_at * 1000).toLocaleString()
                          : ""}
                      </Typography.Text>
                    </>
                  }
                />
              </List.Item>
            )}
          />
          {canWrite(project) ? (
            <Form
              form={commentForm}
              layout="vertical"
              onFinish={async ({ body }) => {
                try {
                  await consoleApi.createComment(project.id, body);
                  commentForm.resetFields();
                  await load();
                } catch (reason) {
                  message.error(errorText(reason, "发送失败"));
                }
              }}
            >
              <Form.Item
                name="body"
                rules={[{ required: true, whitespace: true }]}
              >
                <Input.TextArea
                  rows={3}
                  placeholder="写评论…可 @用户名 提及成员"
                />
              </Form.Item>
              <Button type="primary" htmlType="submit">
                发送
              </Button>
            </Form>
          ) : (
            <Alert type="info" showIcon title="当前项目只读，不能发表评论" />
          )}
        </Card>
        <Card title="团队时间线" className="section-card">
          {timeline.length ? (
            <Timeline
              items={timeline.map((event) => ({
                content: (
                  <>
                    <Typography.Text strong>
                      {event.actor_name || event.actor || "成员"}
                    </Typography.Text>{" "}
                    {event.title || event.summary || event.detail || event.kind}
                    <div>
                      <Typography.Text type="secondary">
                        {event.created_at
                          ? new Date(event.created_at * 1000).toLocaleString()
                          : ""}
                      </Typography.Text>
                    </div>
                  </>
                ),
              }))}
            />
          ) : (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="暂无时间线事件"
            />
          )}
        </Card>
      </Col>
    </Row>
  );
}

type ProjectCapabilityOption = {
  value: string;
  label: string;
  icon: string;
  description: string;
  meta: string;
  tags: string[];
  status?: { label: string; color: string };
};

function catalogField(data: Record<string, unknown>, ...keys: string[]) {
  for (const key of keys) {
    const value = data[key];
    if (typeof value === "string" && value.trim()) return value.trim();
    if (typeof value === "number") return String(value);
  }
  return "";
}

function catalogTags(value: unknown) {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is string | number =>
      typeof item === "string" || typeof item === "number",
    )
    .map(String)
    .filter(Boolean);
}

function mapProjectCapabilityOptions(
  items: CatalogItem<CatalogData>[],
  kind: "connector" | "expert" | "skill",
): ProjectCapabilityOption[] {
  return items.map((item) => {
    const data: Record<string, unknown> =
      typeof item.data === "object" && item.data
        ? item.data
        : { value: item.data };
    const label = catalogField(data, "name", "title", "slug", "value") || item.id;
    const value =
      kind === "skill"
        ? catalogField(data, "slug", "key") || label
        : label;
    const description =
      catalogField(data, "description", "desc", "intro", "subtitle") ||
      "目录暂未提供详细说明";
    const category = catalogField(data, "category");
    const tags = [
      ...catalogTags(data.tags),
      ...(kind === "skill" ? catalogTags(data.tools) : []),
    ];
    const connectorStatus = catalogField(data, "status");
    return {
      value,
      label,
      icon: catalogField(data, "icon", "avatar") || label.slice(0, 1),
      description,
      meta:
        category ||
        (kind === "connector"
          ? "连接器目录"
          : kind === "expert"
            ? "项目专家"
            : "项目技能"),
      tags: [...new Set(tags)].slice(0, 4),
      status:
        kind === "connector" && connectorStatus
          ? connectorStatus === "tok"
            ? { label: "需本机配置", color: "gold" }
            : { label: "目录内置", color: "green" }
          : undefined,
    };
  });
}

function ProjectCapabilityPicker({
  value = [],
  onChange,
  options,
  disabled = false,
  searchPlaceholder,
  emptyDescription,
}: {
  value?: string[];
  onChange?: (value: string[]) => void;
  options: ProjectCapabilityOption[];
  disabled?: boolean;
  searchPlaceholder: string;
  emptyDescription: string;
}) {
  const [query, setQuery] = useState("");
  const selected = new Set(value);
  const knownValues = new Set(options.map((option) => option.value));
  const missing = value.filter((item) => !knownValues.has(item));
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const visible = options.filter((option) =>
    [option.label, option.description, option.meta, ...option.tags]
      .join(" ")
      .toLocaleLowerCase()
      .includes(normalizedQuery),
  );
  const toggle = (item: string) => {
    if (disabled) return;
    onChange?.(
      selected.has(item)
        ? value.filter((current) => current !== item)
        : [...value, item],
    );
  };
  return (
    <div className="project-capability-picker">
      <div className="project-capability-picker-toolbar">
        <Input.Search
          allowClear
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={searchPlaceholder}
          aria-label={searchPlaceholder}
        />
        <Typography.Text type="secondary">
          已选 {value.length} / 目录 {options.length}
        </Typography.Text>
      </div>
      {missing.length ? (
        <Alert
          type="warning"
          showIcon
          title={`${missing.length} 个历史能力已不在当前目录`}
          description={
            <Space size={[4, 6]} wrap>
              {missing.map((item) => (
                <Tag
                  key={item}
                  closable={!disabled}
                  onClose={(event) => {
                    event.preventDefault();
                    toggle(item);
                  }}
                >
                  {item}
                </Tag>
              ))}
            </Space>
          }
        />
      ) : null}
      {visible.length ? (
        <div className="project-capability-grid">
          {visible.map((option) => {
            const active = selected.has(option.value);
            return (
              <button
                key={option.value}
                type="button"
                className={`project-capability-option${active ? " is-selected" : ""}`}
                aria-pressed={active}
                disabled={disabled}
                onClick={() => toggle(option.value)}
              >
                <span className="project-capability-option-icon" aria-hidden="true">
                  {option.icon}
                </span>
                <span className="project-capability-option-copy">
                  <span className="project-capability-option-head">
                    <Typography.Text strong>{option.label}</Typography.Text>
                    {option.status ? (
                      <Tag color={option.status.color}>{option.status.label}</Tag>
                    ) : active ? (
                      <Tag color="green">已选择</Tag>
                    ) : null}
                  </span>
                  <Typography.Text type="secondary" className="project-capability-option-description">
                    {option.description}
                  </Typography.Text>
                  <span className="project-capability-option-meta">
                    <Tag>{option.meta}</Tag>
                    {option.tags.map((tag) => (
                      <Tag key={tag}>{tag}</Tag>
                    ))}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      ) : (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={normalizedQuery ? "没有匹配的能力" : emptyDescription}
        />
      )}
    </div>
  );
}

function ConfigTab({
  project,
  onSaved,
  onNavigateKnowledge,
}: {
  project: Project;
  onSaved: () => Promise<void>;
  onNavigateKnowledge: () => void;
}) {
  const { message } = App.useApp();
  const [basicForm] = Form.useForm<{ name: string; org_id?: string }>();
  const [form] = Form.useForm<{
    instruction: string;
    connectors: string[];
    experts: string[];
    skills: string[];
  }>();
  const [organizations, setOrganizations] = useState<
    { id: string; name: string }[]
  >([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [nextOwner, setNextOwner] = useState("");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteName, setDeleteName] = useState("");
  const [options, setOptions] = useState({
    connectors: [] as ProjectCapabilityOption[],
    experts: [] as ProjectCapabilityOption[],
    skills: [] as ProjectCapabilityOption[],
  });
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState("");
  const [catalogReload, setCatalogReload] = useState(0);
  const [configDirty, setConfigDirty] = useState(false);
  const [configSaving, setConfigSaving] = useState(false);
  const instruction = Form.useWatch("instruction", form) || "";
  const selectedConnectors = Form.useWatch("connectors", form) || [];
  const selectedExperts = Form.useWatch("experts", form) || [];
  const selectedSkills = Form.useWatch("skills", form) || [];
  useEffect(() => {
    basicForm.setFieldsValue({
      name: project.name,
      org_id: project.org_id || undefined,
    });
    form.setFieldsValue({
      instruction: project.instruction || "",
      connectors: project.connectors || [],
      experts: project.experts || [],
      skills: project.skills || [],
    });
    setConfigDirty(false);
  }, [project.id, project.updated_at]);
  useEffect(() => {
    let current = true;
    setCatalogLoading(true);
    setCatalogError("");
    Promise.all([
      consoleApi.catalog<CatalogData>("CONN_DEFS"),
      consoleApi.catalog<CatalogData>("EXPERT_DEFS"),
      consoleApi.catalog<CatalogData>("APP_SKILLS"),
    ])
      .then(([connectors, experts, skills]) => {
        if (!current) return;
        setOptions({
          connectors: mapProjectCapabilityOptions(connectors.items, "connector"),
          experts: mapProjectCapabilityOptions(experts.items, "expert"),
          skills: mapProjectCapabilityOptions(skills.items, "skill"),
        });
      })
      .catch((reason) => {
        if (current) setCatalogError(errorText(reason, "项目能力目录加载失败"));
      })
      .finally(() => {
        if (current) setCatalogLoading(false);
      });
    return () => {
      current = false;
    };
  }, [project.id, project.updated_at, catalogReload]);
  useEffect(() => {
    let current = true;
    Promise.all([
      consoleApi.organizations(),
      consoleApi.projectMembers(project.id),
    ])
      .then(([orgResult, memberResult]) => {
        if (!current) return;
        setOrganizations(orgResult.orgs || []);
        setMembers(memberResult.members || []);
      })
      .catch((reason) => message.error(errorText(reason, "项目管理信息加载失败")));
    return () => {
      current = false;
    };
  }, [project.id, project.updated_at]);
  const governs = project.role === "Owner" || project.role === "Admin";
  const owner = project.role === "Owner";
  const active = !project.archived_at;
  return (
    <div className="tab-stack">
      <Card
        title="基本信息"
        extra={
          project.archived_at > 0 ? <Tag color="orange">已归档</Tag> : undefined
        }
      >
        <Form
          form={basicForm}
          layout="vertical"
          disabled={!governs || !active}
          onFinish={async (values) => {
            try {
              await consoleApi.updateProject(project.id, values);
              message.success("项目信息已保存");
              await onSaved();
            } catch (reason) {
              message.error(errorText(reason, "保存失败"));
            }
          }}
        >
          <Form.Item
            name="name"
            label="项目名称"
            rules={[{ required: true, whitespace: true }]}
          >
            <Input maxLength={120} />
          </Form.Item>
          <Form.Item
            name="org_id"
            label="所属组织"
            extra={owner ? "Owner 可调整组织归属" : "仅 Owner 可调整组织归属"}
          >
            <Select
              allowClear
              disabled={!owner}
              placeholder="个人项目"
              options={organizations.map((org) => ({
                value: org.id,
                label: org.name,
              }))}
            />
          </Form.Item>
          {governs && active && (
            <Button type="primary" htmlType="submit">
              保存基本信息
            </Button>
          )}
        </Form>
      </Card>
      <Card
        title="项目能力配置"
        extra={
          <Space wrap>
            <Tag color={configDirty ? "gold" : "green"}>
              {configDirty ? "有未保存变更" : "已同步"}
            </Tag>
            <Typography.Text type="secondary">仅 Admin / Owner 可管理</Typography.Text>
          </Space>
        }
        className="project-capability-config"
      >
        {!active ? (
          <Alert
            type="warning"
            showIcon
            title="归档项目的能力配置只读"
            description="恢复项目后才能调整默认指令与能力装载。"
          />
        ) : !governs ? (
          <Alert
            type="info"
            showIcon
            title={`当前角色为 ${project.role}，能力配置只读`}
            description="项目 Owner 或 Admin 可以调整项目默认能力。"
          />
        ) : null}
        <Alert
          type="info"
          showIcon
          title="这里配置项目的默认能力装载"
          description="新会话会合并这些项目默认项与会话级装载。连接器在目录中可选不代表设备已经就绪；安装、授权与兼容性由 Local Agent 管理，本页不保存连接器凭据。"
        />
        <div className="project-capability-summary" aria-label="当前能力配置摘要">
          <div className="project-capability-summary-item">
            <Typography.Text type="secondary">项目指令</Typography.Text>
            <Typography.Text strong>{instruction.trim() ? "已配置" : "未配置"}</Typography.Text>
          </div>
          <div className="project-capability-summary-item">
            <Typography.Text type="secondary">连接器</Typography.Text>
            <Typography.Text strong>{selectedConnectors.length} 项</Typography.Text>
          </div>
          <div className="project-capability-summary-item">
            <Typography.Text type="secondary">专家 / 技能</Typography.Text>
            <Typography.Text strong>
              {selectedExperts.length} / {selectedSkills.length} 项
            </Typography.Text>
          </div>
          <div className="project-capability-summary-item">
            <Typography.Text type="secondary">关联知识库</Typography.Text>
            <Space size={8} wrap>
              <Typography.Text strong>{project.knowledge_ids.length} 个</Typography.Text>
              <Button type="link" size="small" onClick={onNavigateKnowledge}>
                管理
              </Button>
            </Space>
          </div>
        </div>
        <Form
          form={form}
          layout="vertical"
          disabled={!governs || !active}
          onValuesChange={() => setConfigDirty(true)}
          onFinish={async (values) => {
            setConfigSaving(true);
            try {
              await consoleApi.updateProject(project.id, values);
              message.success("项目能力配置已保存");
              await onSaved();
              setConfigDirty(false);
            } catch (reason) {
              message.error(errorText(reason, "保存失败"));
            } finally {
              setConfigSaving(false);
            }
          }}
        >
          <section className="project-capability-section" aria-labelledby="project-instruction-title">
            <div className="project-capability-section-head">
              <div>
                <Typography.Title level={5} id="project-instruction-title">
                  项目默认指令
                </Typography.Title>
                <Typography.Text type="secondary">
                  约束项目内 Agent 的工作方式、交付标准与边界，不要在此填写密钥或个人隐私。
                </Typography.Text>
              </div>
              <Tag>{instruction.length.toLocaleString()} / 20,000</Tag>
            </div>
            <Form.Item name="instruction" className="project-capability-instruction">
              <Input.TextArea
                rows={5}
                maxLength={20_000}
                placeholder="例如：先读取项目规范；涉及生产变更必须给出回滚方案；交付前运行项目验证。"
              />
            </Form.Item>
          </section>
          <section className="project-capability-section" aria-labelledby="project-loadout-title">
            <div className="project-capability-section-head">
              <div>
                <Typography.Title level={5} id="project-loadout-title">
                  默认能力装载
                </Typography.Title>
                <Typography.Text type="secondary">
                  按用途搜索并选择。项目仍引用但目录已不可用的历史项会单独提示。
                </Typography.Text>
              </div>
              <Typography.Text type="secondary">
                共选择 {selectedConnectors.length + selectedExperts.length + selectedSkills.length} 项
              </Typography.Text>
            </div>
            {catalogError ? (
              <Alert
                type="error"
                showIcon
                title="能力目录暂时不可用"
                description={catalogError}
                action={<Button onClick={() => setCatalogReload((value) => value + 1)}>重试</Button>}
              />
            ) : null}
            <Spin spinning={catalogLoading} description="正在加载能力目录…">
              <Tabs
                className="project-capability-tabs"
                items={[
                  {
                    key: "connectors",
                    label: `连接器 ${selectedConnectors.length}`,
                    children: (
                      <Form.Item name="connectors" noStyle>
                        <ProjectCapabilityPicker
                          options={options.connectors}
                          disabled={!governs || !active || Boolean(catalogError)}
                          searchPlaceholder="搜索连接器名称、说明或配置状态"
                          emptyDescription="目录中没有可用连接器"
                        />
                      </Form.Item>
                    ),
                  },
                  {
                    key: "experts",
                    label: `专家 ${selectedExperts.length}`,
                    children: (
                      <Form.Item name="experts" noStyle>
                        <ProjectCapabilityPicker
                          options={options.experts}
                          disabled={!governs || !active || Boolean(catalogError)}
                          searchPlaceholder="搜索专家名称、领域或说明"
                          emptyDescription="目录中没有可用专家"
                        />
                      </Form.Item>
                    ),
                  },
                  {
                    key: "skills",
                    label: `技能 ${selectedSkills.length}`,
                    children: (
                      <Form.Item name="skills" noStyle>
                        <ProjectCapabilityPicker
                          options={options.skills}
                          disabled={!governs || !active || Boolean(catalogError)}
                          searchPlaceholder="搜索技能名称、分类、工具或说明"
                          emptyDescription="目录中没有可用技能"
                        />
                      </Form.Item>
                    ),
                  },
                ]}
              />
            </Spin>
          </section>
          {governs && active && (
            <div className="project-capability-actions">
              <Typography.Text type="secondary">
                保存后作为本项目的新会话默认值；已打开会话的临时装载不会被覆盖。
              </Typography.Text>
              <Button
                type="primary"
                htmlType="submit"
                loading={configSaving}
                disabled={!configDirty || catalogLoading || Boolean(catalogError)}
              >
                保存能力配置
              </Button>
            </div>
          )}
        </Form>
      </Card>
      {owner && (
        <Card title="所有权与生命周期">
          <Space orientation="vertical" size={16} className="full-width">
            {active ? (
              <>
                <div>
                  <Typography.Text strong>转移所有权</Typography.Text>
                  <Typography.Paragraph type="secondary">
                    新 Owner 必须已是项目 Admin 或 Member；转移后你会保留 Admin
                    身份。
                  </Typography.Paragraph>
                  <Space wrap>
                    <Select
                      style={{ minWidth: 240 }}
                      value={nextOwner || undefined}
                      placeholder="选择新 Owner"
                      options={members
                        .filter(
                          (member) =>
                            member.account_id !== project.owner_id &&
                            member.role !== "Viewer",
                        )
                        .map((member) => ({
                          value: member.account_id,
                          label: `${member.name} · ${member.role}`,
                        }))}
                      onChange={setNextOwner}
                    />
                    <Popconfirm
                      title="确认转移项目所有权？"
                      description="该操作会立即改变最终管理权。"
                      onConfirm={async () => {
                        try {
                          await consoleApi.transferProject(
                            project.id,
                            nextOwner,
                          );
                          message.success("所有权已转移");
                          await onSaved();
                        } catch (reason) {
                          message.error(errorText(reason, "转移失败"));
                        }
                      }}
                    >
                      <Button disabled={!nextOwner}>转移</Button>
                    </Popconfirm>
                  </Space>
                </div>
                <div>
                  <Typography.Text strong>归档项目</Typography.Text>
                  <Typography.Paragraph type="secondary">
                    归档后项目保留全部数据并统一只读，可随时恢复。
                  </Typography.Paragraph>
                  <Popconfirm
                    title="归档此项目？"
                    onConfirm={async () => {
                      try {
                        await consoleApi.archiveProject(project.id);
                        message.success("项目已归档");
                        await onSaved();
                      } catch (reason) {
                        message.error(errorText(reason, "归档失败"));
                      }
                    }}
                  >
                    <Button>归档项目</Button>
                  </Popconfirm>
                </div>
              </>
            ) : (
              <>
                <Alert
                  type="warning"
                  showIcon
                  title="项目已归档"
                  description="当前所有业务写入均已关闭。恢复后方可继续编辑或转移所有权。"
                />
                <Button
                  type="primary"
                  onClick={async () => {
                    try {
                      await consoleApi.restoreProject(project.id);
                      message.success("项目已恢复");
                      await onSaved();
                    } catch (reason) {
                      message.error(errorText(reason, "恢复失败"));
                    }
                  }}
                >
                  恢复项目
                </Button>
                <div>
                  <Typography.Text strong type="danger">
                    永久删除
                  </Typography.Text>
                  <Typography.Paragraph type="secondary">
                    仅归档项目可删除；如仍有关联知识库，必须先删除知识库，避免远端资源成为孤儿。
                  </Typography.Paragraph>
                  <Button
                    danger
                    onClick={() => {
                      setDeleteName("");
                      setDeleteOpen(true);
                    }}
                  >
                    永久删除项目
                  </Button>
                </div>
              </>
            )}
          </Space>
        </Card>
      )}
      <Modal
        title="永久删除项目"
        open={deleteOpen}
        okText="永久删除"
        okButtonProps={{ danger: true, disabled: deleteName !== project.name }}
        onCancel={() => setDeleteOpen(false)}
        onOk={async () => {
          try {
            await consoleApi.deleteProject(project.id, deleteName);
            message.success("项目已永久删除");
            navigate("/projects");
          } catch (reason) {
            message.error(errorText(reason, "删除失败"));
          }
        }}
      >
        <Alert
          type="error"
          showIcon
          title="此操作不可撤销"
          description={`请输入项目名称“${project.name}”确认。`}
        />
        <Input
          className="section-card"
          value={deleteName}
          onChange={(event) => setDeleteName(event.target.value)}
          placeholder={project.name}
        />
      </Modal>
    </div>
  );
}
