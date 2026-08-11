import {
  App as AntApp, Avatar, Badge, Button, ConfigProvider, Dropdown, Result, Space, Spin,
  Switch, Tag, Tooltip, theme,
} from "antd";
import { uiPalette, uiThemeColorToken } from "../../src/theme/palette";
import { UI_CONTROL_FONT_WEIGHT, uiTypographyToken } from "../../src/theme/typography";
import {
  AppstoreOutlined, BellOutlined, BookOutlined, DashboardOutlined, DesktopOutlined, LogoutOutlined,
  MoonOutlined, PlusOutlined, ProjectOutlined, SafetyCertificateOutlined, SettingOutlined, SunOutlined,
  TeamOutlined, ToolOutlined, UserOutlined, ScheduleOutlined,
} from "@ant-design/icons";
import { ProLayout } from "@ant-design/pro-components";
import { lazy, Suspense, useEffect, useLayoutEffect, useMemo, useState } from "react";
import { ApiError, consoleApi, getToken, setToken } from "./api";
import LoginPage from "./LoginPage";
import { navigate, usePathname } from "./router";
import type { Account, ThemeMode } from "./types";

const WorkspacePage = lazy(() => import("./pages/WorkspacePage"));
const OverviewPage = lazy(() => import("./pages/OverviewPage"));
const ProjectsPage = lazy(() => import("./pages/ProjectsPage"));
const ProjectDetailPage = lazy(() => import("./pages/ProjectDetailPage"));
const OrganizationsPage = lazy(() => import("./pages/OrganizationsPage"));
const NotificationsPage = lazy(() => import("./pages/NotificationsPage"));
const AutomationsPage = lazy(() => import("./pages/AutomationsPage"));
const LocalAgentsPage = lazy(() => import("./pages/LocalAgentsPage"));
const UsersPage = lazy(() => import("./pages/UsersPage"));
const CatalogPage = lazy(() => import("./pages/CatalogPage"));
const RawCatalogPage = lazy(() => import("./pages/RawCatalogPage"));
const PlatformSettingsPage = lazy(() => import("./pages/PlatformSettingsPage"));
const SkillsPage = lazy(() => import("./SkillsPage"));

const THEME_KEY = "agentmate.console.theme";
const ADMIN_PREFIXES = ["/admin", "/catalog/", "/users", "/settings/"];
const PAGE_TITLES: Record<string, string> = {
  "/": "我的工作台", "/admin": "管理总览", "/projects": "项目", "/organizations": "组织与成员",
  "/notifications": "通知", "/automations": "自动化", "/local-agents": "Local Agent", "/catalog/experts": "专家", "/catalog/connectors": "连接器",
  "/catalog/skills": "技能", "/catalog/knowledge": "知识库模板", "/users": "用户",
  "/settings/platform": "平台设置", "/settings/catalog": "能力定义 JSON",
};

const baseRoutes = [
  { path: "/workspace", name: "工作区", icon: <DashboardOutlined />, children: [
    { path: "/", name: "我的工作台", icon: <DashboardOutlined /> },
    { path: "/projects", name: "项目", icon: <ProjectOutlined /> },
    { path: "/organizations", name: "组织与成员", icon: <TeamOutlined /> },
    { path: "/local-agents", name: "Local Agent", icon: <DesktopOutlined /> },
    { path: "/automations", name: "自动化", icon: <ScheduleOutlined /> },
  ] },
];
const adminRoutes = [
  { path: "/capabilities", name: "能力中心", icon: <AppstoreOutlined />, children: [
    { path: "/catalog/experts", name: "专家", icon: <UserOutlined /> },
    { path: "/catalog/connectors", name: "连接器", icon: <ToolOutlined /> },
    { path: "/catalog/skills", name: "技能", icon: <SafetyCertificateOutlined /> },
    { path: "/catalog/knowledge", name: "知识库模板", icon: <BookOutlined /> },
  ] },
  { path: "/administration", name: "系统管理", icon: <SettingOutlined />, children: [
    { path: "/admin", name: "管理总览", icon: <DashboardOutlined /> },
    { path: "/users", name: "用户与权限", icon: <UserOutlined /> },
    { path: "/settings/platform", name: "平台设置", icon: <SettingOutlined /> },
    { path: "/settings/catalog", name: "能力定义 JSON", icon: <ToolOutlined /> },
  ] },
];

function CurrentPage({ account, pathname, onUnreadChange }: { account: Account; pathname: string; onUnreadChange: (count: number) => void }) {
  const projectMatch = pathname.match(/^\/projects\/([^/]+)$/);
  if (!account.is_platform_admin && ADMIN_PREFIXES.some((prefix) => pathname.startsWith(prefix))) return <Result status="403" title="需要平台管理员权限" subTitle="当前账号无权访问平台能力配置或系统设置。" extra={<Button type="primary" onClick={() => navigate("/")}>返回概览</Button>} />;
  if (pathname === "/projects/new") return <ProjectsPage createOnMount />;
  if (projectMatch) return <ProjectDetailPage projectId={decodeURIComponent(projectMatch[1])} />;
  switch (pathname) {
    case "/": return <WorkspacePage account={account} />;
    case "/admin": return <OverviewPage account={account} />;
    case "/projects": return <ProjectsPage />;
    case "/organizations": return <OrganizationsPage />;
    case "/local-agents": return <LocalAgentsPage />;
    case "/automations": return <AutomationsPage />;
    case "/notifications": return <NotificationsPage onUnreadChange={onUnreadChange} />;
    case "/catalog/experts": return <CatalogPage section="experts" />;
    case "/catalog/connectors": return <CatalogPage section="connectors" />;
    case "/catalog/skills": return <SkillsPage />;
    case "/catalog/knowledge": return <CatalogPage section="knowledge" />;
    case "/users": return <UsersPage current={account} />;
    case "/settings/platform": return <PlatformSettingsPage />;
    case "/settings/catalog": return <RawCatalogPage />;
    default: return <Result status="404" title="页面不存在" extra={<Button type="primary" onClick={() => navigate("/")}>返回概览</Button>} />;
  }
}

function ConsoleContent({ account, mode, onToggleTheme, onLogout }: { account: Account; mode: ThemeMode; onToggleTheme: () => void; onLogout: () => void }) {
  const pathname = usePathname();
  const [unread, setUnread] = useState(0);
  const routes = useMemo(() => account.is_platform_admin ? [...baseRoutes, ...adminRoutes] : baseRoutes, [account.is_platform_admin]);
  const adminSurface = ADMIN_PREFIXES.some((prefix) => pathname.startsWith(prefix));
  const productTitle = adminSurface ? "AgentMate Console" : "AgentMate Workspace";
  useEffect(() => {
    const key = pathname.match(/^\/projects\/[^/]+$/) ? "/projects" : pathname;
    document.title = `${PAGE_TITLES[key] || (key === "/projects" ? "项目" : productTitle)} · ${productTitle}`;
  }, [pathname, productTitle]);
  useEffect(() => { consoleApi.notifications().then((result) => setUnread(result.unread || 0)).catch(() => undefined); }, [pathname]);
  return (
    <ProLayout
      title={productTitle}
      logo={<div className="brand-mark">{adminSurface ? "C" : "W"}</div>}
      layout="mix"
      fixedHeader
      fixSiderbar
      breakpoint="lg"
      location={{ pathname: pathname.match(/^\/projects\/[^/]+$/) ? "/projects" : pathname }}
      route={{ path: "/", routes }}
      menu={{ type: "group", collapsedShowGroupTitle: true }}
      menuItemRender={(item, dom) => <a href={item.path} onClick={(event) => { event.preventDefault(); navigate(item.path || "/"); }}>{dom}</a>}
      avatarProps={{
        src: <Avatar size="small" icon={<UserOutlined />} />,
        title: account.name,
        render: (_props, dom) => <Dropdown menu={{ items: [
          { key: "identity", disabled: true, label: <Space>{account.name}<Tag color={account.is_platform_admin ? "blue" : "default"}>{account.is_platform_admin ? "平台管理员" : "普通用户"}</Tag></Space> },
          { type: "divider" }, { key: "logout", icon: <LogoutOutlined />, label: "退出登录", onClick: onLogout },
        ] }}>{dom}</Dropdown>,
      }}
      actionsRender={() => [
        <Dropdown
          key="create"
          trigger={["click"]}
          menu={{
            items: [
              {
                key: "project",
                icon: <ProjectOutlined />,
                label: "新建项目",
                onClick: () => navigate("/projects/new"),
              },
              {
                key: "organization",
                icon: <TeamOutlined />,
                label: "管理组织",
                onClick: () => navigate("/organizations"),
              },
            ],
          }}
        >
          <Tooltip title="快速新建">
            <Button
              type="primary"
              className="console-create-action"
              icon={<PlusOutlined />}
              aria-label="快速新建"
            >
              <span className="console-create-action-label">新建</span>
            </Button>
          </Tooltip>
        </Dropdown>,
        <Tooltip title={mode === "dark" ? "切换浅色主题" : "切换深色主题"} key="theme"><Switch aria-label="切换主题" checked={mode === "dark"} checkedChildren={<MoonOutlined />} unCheckedChildren={<SunOutlined />} onChange={onToggleTheme} /></Tooltip>,
        <Tooltip title="通知" key="notifications"><Badge count={unread} size="small"><Button type="text" icon={<BellOutlined />} aria-label="通知" onClick={() => navigate("/notifications")} /></Badge></Tooltip>,
      ]}
      token={{ header: { colorBgHeader: uiPalette[mode].header }, sider: { colorMenuBackground: uiPalette[mode].sidebar } }}
    >
      <Suspense fallback={<div className="page-loading"><Spin size="large" description="页面加载中…" /></div>}><CurrentPage account={account} pathname={pathname} onUnreadChange={setUnread} /></Suspense>
    </ProLayout>
  );
}

export default function ConsoleApp() {
  const [account, setAccount] = useState<Account | null>(null);
  const [booting, setBooting] = useState(true);
  const [mode, setMode] = useState<ThemeMode>(() => localStorage.getItem(THEME_KEY) === "light" ? "light" : "dark");
  useLayoutEffect(() => { document.body.classList.toggle("dark", mode === "dark"); document.documentElement.style.colorScheme = mode; localStorage.setItem(THEME_KEY, mode); }, [mode]);
  useEffect(() => { let active = true; async function boot() { if (!getToken()) { setBooting(false); return; } try { const response = await consoleApi.me(); if (active) setAccount(response.account); } catch (reason) { if (reason instanceof ApiError && reason.status === 401) setToken(""); } finally { if (active) setBooting(false); } } void boot(); return () => { active = false; }; }, []);
  const themeConfig = useMemo(() => ({
    algorithm: mode === "dark" ? theme.darkAlgorithm : theme.defaultAlgorithm,
    token: { colorPrimary: "#16b37a", borderRadius: 8, controlHeight: 32, ...uiTypographyToken, ...uiThemeColorToken(mode) },
    components: {
      Button: { fontWeight: UI_CONTROL_FONT_WEIGHT },
      Card: { paddingLG: 16 },
      Layout: {
        bodyBg: uiPalette[mode].page,
        headerBg: uiPalette[mode].header,
        siderBg: uiPalette[mode].sidebar,
      },
      Modal: { borderRadiusLG: 10 },
    },
  }), [mode]);
  async function logout() { try { await consoleApi.logout(); } catch { /* browser token removal is authoritative */ } setToken(""); setAccount(null); navigate("/", true); }
  const toggleTheme = () => setMode((current) => current === "dark" ? "light" : "dark");
  return <ConfigProvider componentSize="small" theme={themeConfig}><AntApp>{booting ? <div className="boot-screen"><Spin size="large" description="正在连接 AgentMate Server…" /></div> : account ? <ConsoleContent account={account} mode={mode} onToggleTheme={toggleTheme} onLogout={() => void logout()} /> : <LoginPage onAuthenticated={setAccount} themeMode={mode} onToggleTheme={toggleTheme} />}</AntApp></ConfigProvider>;
}
