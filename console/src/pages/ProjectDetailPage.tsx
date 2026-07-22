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
  ProjectOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import { PageContainer, ProTable } from "@ant-design/pro-components";
import type { ProColumns } from "@ant-design/pro-components";
import { useCallback, useEffect, useRef, useState } from "react";
import { consoleApi } from "../api";
import {
  ProjectGantt,
  ProjectIterations,
  ProjectOverview,
  ProjectPlan,
  ProjectTasks,
  ProjectWorkload,
  ProjectWorkProvider,
} from "../components/project/ProjectWorkspace";
import type { ProjectWorkspaceTab } from "../components/project/ProjectWorkspace";
import { navigate } from "../router";
import type {
  CatalogData,
  CatalogItem,
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
  "plan",
  "tasks",
  "workload",
  "gantt",
  "iterations",
  "knowledge",
  "collab",
  "config",
];

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
          <Card className="project-hero">
            <Space size={16}>
              <Avatar shape="square" size={52} icon={<ProjectOutlined />} />
              <div>
                <Typography.Title level={4}>{project.name}</Typography.Title>
                <Typography.Text type="secondary">
                  {project.instruction || "未设置项目指令"}
                </Typography.Text>
              </div>
            </Space>
          </Card>
          <Tabs
            className="project-workspace-tabs"
            activeKey={tab}
            onChange={(key) => selectProjectTab(key as ProjectWorkspaceTab)}
            more={{ trigger: "click" }}
            items={[
              { key: "overview", label: "概览", children: <ProjectOverview /> },
              { key: "plan", label: "计划", children: <ProjectPlan /> },
              { key: "tasks", label: "任务", children: <ProjectTasks /> },
              { key: "workload", label: "负载", children: <ProjectWorkload /> },
              { key: "gantt", label: "甘特", children: <ProjectGantt /> },
              {
                key: "iterations",
                label: "计划设置",
                children: <ProjectIterations />,
              },
              {
                key: "knowledge",
                label: "知识库",
                children: <KnowledgeTab project={project} />,
              },
              {
                key: "collab",
                label: "协作",
                children: <CollaborationTab project={project} />,
              },
              {
                key: "config",
                label: "配置",
                children: <ConfigTab project={project} onSaved={load} />,
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
          message="中央 WeKnora 尚未配置"
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
            message="解析、切片、嵌入与检索均由中央 WeKnora 完成，项目成员无需再配置 API Key。"
          />
        </Form>
      </Modal>
      <Drawer
        width={720}
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
              <Space direction="vertical" size={12} className="full-width">
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
                    message="文档状态刷新失败"
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
                <Space direction="vertical" size={12} className="full-width">
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
            <Space direction="vertical" className="full-width">
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
            <Alert type="info" showIcon message="当前项目只读，不能发表评论" />
          )}
        </Card>
        <Card title="团队时间线" className="section-card">
          {timeline.length ? (
            <Timeline
              items={timeline.map((event) => ({
                children: (
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

function ConfigTab({
  project,
  onSaved,
}: {
  project: Project;
  onSaved: () => Promise<void>;
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
    connectors: [] as { value: string; label: string }[],
    experts: [] as { value: string; label: string }[],
    skills: [] as { value: string; label: string }[],
  });
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
    Promise.all([
      consoleApi.catalog<CatalogData>("NP_CONNS"),
      consoleApi.catalog<CatalogData>("EXPERT_DEFS"),
      consoleApi.catalog<CatalogData>("APP_SKILLS"),
      consoleApi.organizations(),
      consoleApi.projectMembers(project.id),
    ])
      .then(([connectors, experts, skills, orgResult, memberResult]) => {
        const map = (items: CatalogItem<CatalogData>[], stable = false) =>
          items.map((item) => {
            const data =
              typeof item.data === "object" && item.data
                ? item.data
                : { value: item.data };
            const label = String(
              data.name || data.title || data.slug || data.value || item.id,
            );
            const value = stable
              ? String(data.slug || data.key || label)
              : label;
            return { value, label };
          });
        setOptions({
          connectors: map(connectors.items),
          experts: map(experts.items),
          skills: map(skills.items, true),
        });
        setOrganizations(orgResult.orgs || []);
        setMembers(memberResult.members || []);
      })
      .catch((reason) => message.error(errorText(reason, "目录选项加载失败")));
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
          <Typography.Text type="secondary">
            仅 Admin / Owner 可管理
          </Typography.Text>
        }
      >
        <Form
          form={form}
          layout="vertical"
          disabled={!governs || !active}
          onFinish={async (values) => {
            try {
              await consoleApi.updateProject(project.id, values);
              message.success("项目配置已保存");
              await onSaved();
            } catch (reason) {
              message.error(errorText(reason, "保存失败"));
            }
          }}
        >
          <Form.Item name="instruction" label="项目指令">
            <Input.TextArea rows={6} />
          </Form.Item>
          <Form.Item name="connectors" label="连接器">
            <Select
              mode="multiple"
              options={options.connectors}
              placeholder="选择连接器"
            />
          </Form.Item>
          <Form.Item name="experts" label="专家">
            <Select
              mode="multiple"
              options={options.experts}
              placeholder="选择专家"
            />
          </Form.Item>
          <Form.Item name="skills" label="技能">
            <Select
              mode="multiple"
              options={options.skills}
              placeholder="选择技能"
            />
          </Form.Item>
          {governs && active && (
            <Button type="primary" htmlType="submit">
              保存配置
            </Button>
          )}
        </Form>
      </Card>
      {owner && (
        <Card title="所有权与生命周期">
          <Space direction="vertical" size={16} className="full-width">
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
                  message="项目已归档"
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
          message="此操作不可撤销"
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
