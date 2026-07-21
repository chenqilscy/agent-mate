import {
  App as AntApp, Avatar, Badge, Button, ConfigProvider, Dropdown, Result, Space, Spin,
  Switch, Tag, Tooltip, theme,
} from "antd";
import { UI_CONTROL_FONT_WEIGHT, uiTypographyToken } from "../../src/theme/typography";
import {
  AppstoreOutlined, BellOutlined, BookOutlined, DashboardOutlined, LogoutOutlined,
  MoonOutlined, ProjectOutlined, SafetyCertificateOutlined, SettingOutlined, SunOutlined,
  TeamOutlined, ToolOutlined, UserOutlined,
} from "@ant-design/icons";
import { ProLayout } from "@ant-design/pro-components";
import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { ApiError, consoleApi, getToken, setToken } from "./api";
import LoginPage from "./LoginPage";
import { navigate, usePathname } from "./router";
import type { Account, ThemeMode } from "./types";

const OverviewPage = lazy(() => import("./pages/OverviewPage"));
const ProjectsPage = lazy(() => import("./pages/ProjectsPage"));
const ProjectDetailPage = lazy(() => import("./pages/ProjectDetailPage"));
const OrganizationsPage = lazy(() => import("./pages/OrganizationsPage"));
const NotificationsPage = lazy(() => import("./pages/NotificationsPage"));
const UsersPage = lazy(() => import("./pages/UsersPage"));
const CatalogPage = lazy(() => import("./pages/CatalogPage"));
const RawCatalogPage = lazy(() => import("./pages/RawCatalogPage"));
const SkillsPage = lazy(() => import("./SkillsPage"));

const THEME_KEY = "agentmate.console.theme";
const ADMIN_PREFIXES = ["/catalog/", "/users", "/settings/"];
const PAGE_TITLES: Record<string, string> = {
  "/": "概览", "/projects": "项目", "/organizations": "组织与成员",
  "/notifications": "通知", "/catalog/experts": "专家", "/catalog/connectors": "连接器",
  "/catalog/skills": "技能", "/catalog/knowledge": "知识库", "/users": "用户",
  "/settings/catalog": "高级 JSON",
};

const baseRoutes = [
  { path: "/", name: "概览", icon: <DashboardOutlined /> },
  { path: "/projects", name: "项目", icon: <ProjectOutlined /> },
  { path: "/organizations", name: "组织与成员", icon: <TeamOutlined /> },
];
const adminRoutes = [
  { path: "/catalog", name: "目录", icon: <AppstoreOutlined />, children: [
    { path: "/catalog/experts", name: "专家", icon: <UserOutlined /> },
    { path: "/catalog/connectors", name: "连接器", icon: <ToolOutlined /> },
    { path: "/catalog/skills", name: "技能", icon: <SafetyCertificateOutlined /> },
    { path: "/catalog/knowledge", name: "知识库", icon: <BookOutlined /> },
  ] },
  { path: "/users", name: "用户", icon: <UserOutlined /> },
  { path: "/settings/catalog", name: "高级 JSON", icon: <SettingOutlined /> },
];

function CurrentPage({ account, pathname, onUnreadChange }: { account: Account; pathname: string; onUnreadChange: (count: number) => void }) {
  const projectMatch = pathname.match(/^\/projects\/([^/]+)$/);
  if (!account.is_platform_admin && ADMIN_PREFIXES.some((prefix) => pathname.startsWith(prefix))) return <Result status="403" title="需要平台管理员权限" subTitle="当前账号无权访问平台目录或系统设置。" extra={<Button type="primary" onClick={() => navigate("/")}>返回概览</Button>} />;
  if (projectMatch) return <ProjectDetailPage projectId={decodeURIComponent(projectMatch[1])} />;
  switch (pathname) {
    case "/": return <OverviewPage account={account} />;
    case "/projects": return <ProjectsPage />;
    case "/organizations": return <OrganizationsPage />;
    case "/notifications": return <NotificationsPage onUnreadChange={onUnreadChange} />;
    case "/catalog/experts": return <CatalogPage section="experts" />;
    case "/catalog/connectors": return <CatalogPage section="connectors" />;
    case "/catalog/skills": return <SkillsPage />;
    case "/catalog/knowledge": return <CatalogPage section="knowledge" />;
    case "/users": return <UsersPage current={account} />;
    case "/settings/catalog": return <RawCatalogPage />;
    default: return <Result status="404" title="页面不存在" extra={<Button type="primary" onClick={() => navigate("/")}>返回概览</Button>} />;
  }
}

function ConsoleContent({ account, mode, onToggleTheme, onLogout }: { account: Account; mode: ThemeMode; onToggleTheme: () => void; onLogout: () => void }) {
  const pathname = usePathname();
  const [unread, setUnread] = useState(0);
  const routes = useMemo(() => account.is_platform_admin ? [...baseRoutes, ...adminRoutes] : baseRoutes, [account.is_platform_admin]);
  useEffect(() => {
    const key = pathname.match(/^\/projects\/[^/]+$/) ? "/projects" : pathname;
    document.title = `${PAGE_TITLES[key] || (key === "/projects" ? "项目" : "AgentMate Console")} · AgentMate Console`;
  }, [pathname]);
  useEffect(() => { consoleApi.notifications().then((result) => setUnread(result.unread || 0)).catch(() => undefined); }, [pathname]);
  return (
    <ProLayout
      title="AgentMate Console"
      logo={<div className="brand-mark">C</div>}
      layout="mix"
      fixedHeader
      fixSiderbar
      breakpoint="lg"
      location={{ pathname: pathname.match(/^\/projects\/[^/]+$/) ? "/projects" : pathname }}
      route={{ path: "/", routes }}
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
        <Tooltip title={mode === "dark" ? "切换浅色主题" : "切换深色主题"} key="theme"><Switch aria-label="切换主题" checked={mode === "dark"} checkedChildren={<MoonOutlined />} unCheckedChildren={<SunOutlined />} onChange={onToggleTheme} /></Tooltip>,
        <Tooltip title="通知" key="notifications"><Badge count={unread} size="small"><Button type="text" icon={<BellOutlined />} aria-label="通知" onClick={() => navigate("/notifications")} /></Badge></Tooltip>,
      ]}
      token={{ header: { colorBgHeader: mode === "dark" ? "#151b2a" : "#ffffff" }, sider: { colorMenuBackground: mode === "dark" ? "#111827" : "#ffffff" } }}
    >
      <Suspense fallback={<div className="page-loading"><Spin size="large" tip="页面加载中…" /></div>}><CurrentPage account={account} pathname={pathname} onUnreadChange={setUnread} /></Suspense>
    </ProLayout>
  );
}

export default function ConsoleApp() {
  const [account, setAccount] = useState<Account | null>(null);
  const [booting, setBooting] = useState(true);
  const [mode, setMode] = useState<ThemeMode>(() => localStorage.getItem(THEME_KEY) === "light" ? "light" : "dark");
  useEffect(() => { document.body.classList.toggle("dark", mode === "dark"); document.documentElement.style.colorScheme = mode; localStorage.setItem(THEME_KEY, mode); }, [mode]);
  useEffect(() => { let active = true; async function boot() { if (!getToken()) { setBooting(false); return; } try { const response = await consoleApi.me(); if (active) setAccount(response.account); } catch (reason) { if (reason instanceof ApiError && reason.status === 401) setToken(""); } finally { if (active) setBooting(false); } } void boot(); return () => { active = false; }; }, []);
  const themeConfig = useMemo(() => ({
    algorithm: mode === "dark" ? theme.darkAlgorithm : theme.defaultAlgorithm,
    token: { colorPrimary: "#16b37a", borderRadius: 8, ...uiTypographyToken },
    components: {
      Button: { fontWeight: UI_CONTROL_FONT_WEIGHT },
    },
  }), [mode]);
  async function logout() { try { await consoleApi.logout(); } catch { /* browser token removal is authoritative */ } setToken(""); setAccount(null); navigate("/", true); }
  return <ConfigProvider componentSize="small" theme={themeConfig}><AntApp>{booting ? <div className="boot-screen"><Spin size="large" tip="正在连接 AgentMate Server…" /></div> : account ? <ConsoleContent account={account} mode={mode} onToggleTheme={() => setMode((current) => current === "dark" ? "light" : "dark")} onLogout={() => void logout()} /> : <LoginPage onAuthenticated={setAccount} />}</AntApp></ConfigProvider>;
}
