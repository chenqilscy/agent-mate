import { App, Button, Card, Col, Empty, Progress, Row, Space, Statistic, Tag, Typography } from "antd";
import { CompatList as List } from "../components/CompatList";
import { AppstoreOutlined, ProjectOutlined, TeamOutlined, UserOutlined } from "@ant-design/icons";
import { PageContainer } from "@ant-design/pro-components";
import { useEffect, useState } from "react";
import { consoleApi } from "../api";
import { navigate } from "../router";
import type { Account, Project } from "../types";

export default function OverviewPage({ account }: { account: Account }) {
  const { message } = App.useApp();
  const [projects, setProjects] = useState<Project[]>([]);
  const [counts, setCounts] = useState({ organizations: 0, experts: 0, connectors: 0, skills: 0 });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      consoleApi.projects(),
      consoleApi.organizations(),
      account.is_platform_admin ? consoleApi.catalog("EXPERT_DEFS", true) : Promise.resolve({ items: [] }),
      account.is_platform_admin ? consoleApi.catalog("CONN_DEFS", true) : Promise.resolve({ items: [] }),
      account.is_platform_admin ? consoleApi.skills() : Promise.resolve({ items: [] }),
    ]).then(([projectResult, orgResult, experts, connectors, skills]) => {
      setProjects(projectResult.projects || []);
      setCounts({ organizations: orgResult.orgs?.length || 0, experts: experts.items.length, connectors: connectors.items.length, skills: skills.items.length });
    }).catch((reason) => message.error(reason instanceof Error ? reason.message : "概览加载失败"))
      .finally(() => setLoading(false));
  }, [account.is_platform_admin, message]);

  const cards = [
    { title: "项目", value: projects.length, icon: <ProjectOutlined />, path: "/projects" },
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
            <Space direction="vertical" size={18} className="full-width">
              <Space><span className="status-dot online" /><Typography.Text strong>AgentMate Server 在线</Typography.Text></Space>
              <div><Typography.Text type="secondary">账号权限</Typography.Text><div><Tag color={account.is_platform_admin ? "blue" : "default"}>{account.is_platform_admin ? "平台管理员" : "普通成员"}</Tag></div></div>
              <div><Typography.Text type="secondary">目录迁移进度</Typography.Text><Progress percent={100} status="success" /></div>
            </Space>
          </Card>
        </Col>
      </Row>
    </PageContainer>
  );
}
