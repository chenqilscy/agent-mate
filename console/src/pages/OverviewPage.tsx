import { App, Button, Card, Col, Empty, Progress, Row, Space, Statistic, Tag, Typography } from "antd";
import { CompatList as List } from "../components/CompatList";
import { AppstoreOutlined, CheckCircleOutlined, ProjectOutlined, TeamOutlined, UserOutlined, WarningOutlined } from "@ant-design/icons";
import { PageContainer } from "@ant-design/pro-components";
import { useEffect, useState } from "react";
import { consoleApi } from "../api";
import { navigate } from "../router";
import type { Account, Project, ProjectHealthPortfolio, ProjectHealthStatus } from "../types";

const HEALTH_LABEL: Record<ProjectHealthStatus, string> = { critical: "严重风险", attention: "需关注", healthy: "健康" };
const HEALTH_COLOR: Record<ProjectHealthStatus, string> = { critical: "error", attention: "warning", healthy: "success" };
const transitionLabel = (item: ProjectHealthPortfolio["items"][number]) => item.last_transition
  ? `${item.last_transition.direction === "worsened" ? "最近恶化" : "最近恢复"}：${HEALTH_LABEL[item.last_transition.from_status]} → ${HEALTH_LABEL[item.last_transition.to_status]}`
  : item.health.reasons[0]?.label || "当前无异常项";

export default function OverviewPage({ account }: { account: Account }) {
  const { message } = App.useApp();
  const [projects, setProjects] = useState<Project[]>([]);
  const [portfolio, setPortfolio] = useState<ProjectHealthPortfolio | null>(null);
  const [counts, setCounts] = useState({ organizations: 0, experts: 0, connectors: 0, skills: 0 });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      consoleApi.projects(),
      consoleApi.organizations(),
      account.is_platform_admin ? consoleApi.catalog("EXPERT_DEFS", true) : Promise.resolve({ items: [] }),
      account.is_platform_admin ? consoleApi.catalog("CONN_DEFS", true) : Promise.resolve({ items: [] }),
      account.is_platform_admin ? consoleApi.skills() : Promise.resolve({ items: [] }),
      consoleApi.projectHealthScan().catch(() => null).then(() => consoleApi.projectHealthPortfolio()),
    ]).then(([projectResult, orgResult, experts, connectors, skills, healthPortfolio]) => {
      setProjects(projectResult.projects || []);
      setPortfolio(healthPortfolio);
      setCounts({ organizations: orgResult.orgs?.length || 0, experts: experts.items.length, connectors: connectors.items.length, skills: skills.items.length });
    }).catch((reason) => message.error(reason instanceof Error ? reason.message : "概览加载失败"))
      .finally(() => setLoading(false));
  }, [account.is_platform_admin, message]);

  const cards = [
    { title: "项目", value: projects.length, icon: <ProjectOutlined />, path: "/projects" },
    { title: "严重风险", value: portfolio?.summary.critical_projects || 0, icon: <WarningOutlined />, path: "/projects" },
    { title: "需关注", value: portfolio?.summary.attention_projects || 0, icon: <CheckCircleOutlined />, path: "/projects" },
    { title: "组织", value: counts.organizations, icon: <TeamOutlined />, path: "/organizations" },
    ...(account.is_platform_admin ? [
      { title: "专家", value: counts.experts, icon: <UserOutlined />, path: "/catalog/experts" },
      { title: "连接器", value: counts.connectors, icon: <AppstoreOutlined />, path: "/catalog/connectors" },
      { title: "技能", value: counts.skills, icon: <AppstoreOutlined />, path: "/catalog/skills" },
    ] : []),
  ];

  return (
    <PageContainer title="概览" subTitle="AgentMate Server 管理总览" header={{ breadcrumb: { items: [{ title: "工作区" }, { title: "概览" }] } }}>
      <div className="overview-stat-grid">
        {cards.map((item) => (
          <Card hoverable loading={loading} onClick={() => navigate(item.path)} key={item.title}>
            <Statistic title={item.title} value={item.value} prefix={item.icon} />
          </Card>
        ))}
      </div>
      <Card
        className="section-card"
        title="项目健康优先级"
        extra={<Space><Tag color="error">严重 {portfolio?.summary.critical_projects || 0}</Tag><Tag color="warning">关注 {portfolio?.summary.attention_projects || 0}</Tag><Button type="link" onClick={() => navigate("/projects")}>查看全部</Button></Space>}
      >
        {portfolio?.items.length ? (
          <List dataSource={portfolio.items.slice(0, 6)} renderItem={(item) => (
            <List.Item actions={[<Button type="link" key="open" onClick={() => navigate(`/projects/${item.project.id}`)}>处理</Button>]}>
              <List.Item.Meta
                title={<Space wrap><span>{item.project.name}</span><Tag color={HEALTH_COLOR[item.health.status]}>{HEALTH_LABEL[item.health.status]}</Tag><Tag>{item.project.role}</Tag></Space>}
                description={transitionLabel(item)}
              />
              <div className="overview-health-progress">
                <Typography.Text type="secondary">任务完成 {item.health.summary.completion_percent}%</Typography.Text>
                <Progress percent={item.health.summary.completion_percent} showInfo={false} status={item.health.status === "critical" ? "exception" : item.health.status === "healthy" ? "success" : "normal"} />
              </div>
            </List.Item>
          )} />
        ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有可统计的项目" />}
      </Card>
      <Row gutter={[16, 16]} className="section-row">
        <Col xs={24} lg={15}>
          <Card title="最近项目" extra={<Button type="link" onClick={() => navigate("/projects")}>查看全部</Button>}>
            {projects.length ? (
              <List dataSource={projects.slice(0, 6)} renderItem={(project) => (
                <List.Item actions={[<Button type="link" key="open" onClick={() => navigate(`/projects/${project.id}`)}>打开</Button>]}>
                  <List.Item.Meta title={project.name} description={project.instruction || "未设置项目指令"} />
                  <Tag>{project.role}</Tag>
                </List.Item>
              )} />
            ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有项目" />}
          </Card>
        </Col>
        <Col xs={24} lg={9}>
          <Card title="服务状态">
            <Space orientation="vertical" size={18} className="full-width">
              <Space><span className="status-dot online" /><Typography.Text strong>AgentMate Server 在线</Typography.Text></Space>
              <div><Typography.Text type="secondary">账号权限</Typography.Text><div><Tag color={account.is_platform_admin ? "blue" : "default"}>{account.is_platform_admin ? "平台管理员" : "普通成员"}</Tag></div></div>
              <div><Typography.Text type="secondary">能力数据迁移</Typography.Text><Progress percent={100} status="success" /></div>
            </Space>
          </Card>
        </Col>
      </Row>
    </PageContainer>
  );
}
