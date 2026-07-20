import {
  App as AntApp,
  Avatar,
  Button,
  ConfigProvider,
  Dropdown,
  Result,
  Space,
  Spin,
  Switch,
  Tag,
  theme,
  Tooltip,
} from "antd";
import {
  AppstoreOutlined,
  BellOutlined,
  BookOutlined,
  DashboardOutlined,
  LogoutOutlined,
  MoonOutlined,
  ProjectOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
  SunOutlined,
  TeamOutlined,
  ToolOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { ProLayout } from "@ant-design/pro-components";
import { useEffect, useMemo, useState } from "react";
import { ApiError, consoleApi, getToken, setToken } from "./api";
import LoginPage from "./LoginPage";
import SkillsPage from "./SkillsPage";
import type { Account, ThemeMode } from "./types";

const THEME_KEY = "agentmate.console.theme";

const routes = [
  { path: "/", name: "概览", icon: <DashboardOutlined /> },
  { path: "/projects", name: "项目", icon: <ProjectOutlined /> },
  { path: "/organizations", name: "组织与成员", icon: <TeamOutlined /> },
  {
    path: "/catalog",
    name: "目录",
    icon: <AppstoreOutlined />,
    children: [
      { path: "/catalog/experts", name: "专家", icon: <UserOutlined /> },
      { path: "/catalog/connectors", name: "连接器", icon: <ToolOutlined /> },
      { path: "/catalog/skills", name: "技能", icon: <SafetyCertificateOutlined /> },
      { path: "/catalog/knowledge", name: "知识库", icon: <BookOutlined /> },
    ],
  },
  { path: "/users", name: "用户", icon: <UserOutlined /> },
  { path: "/settings/catalog", name: "高级 JSON", icon: <SettingOutlined /> },
];

function ConsoleContent({ account, mode, onToggleTheme, onLogout }: {
  account: Account;
  mode: ThemeMode;
  onToggleTheme: () => void;
  onLogout: () => void;
}) {
  if (!account.is_platform_admin) {
    return (
      <Result
        status="403"
        title="需要平台管理员权限"
        subTitle="技能目录属于 AgentMate Server 的平台级能力。"
        extra={<Button type="primary" href="/">返回 Console 概览</Button>}
      />
    );
  }

  return (
    <ProLayout
      title="AgentMate Console"
      logo={<div className="brand-mark">C</div>}
      layout="mix"
      fixedHeader
      fixSiderbar
      breakpoint="lg"
      location={{ pathname: "/catalog/skills" }}
      route={{ path: "/", routes }}
      menuItemRender={(item, dom) => <a href={item.path}>{dom}</a>}
      avatarProps={{
        src: <Avatar size="small" icon={<UserOutlined />} />,
        title: account.name,
        render: (_props, dom) => (
          <Dropdown
            menu={{
              items: [
                { key: "identity", disabled: true, label: <Space>{account.name}<Tag color="blue">平台管理员</Tag></Space> },
                { type: "divider" },
                { key: "logout", icon: <LogoutOutlined />, label: "退出登录", onClick: onLogout },
              ],
            }}
          >
            {dom}
          </Dropdown>
        ),
      }}
      actionsRender={() => [
        <Tooltip title={mode === "dark" ? "切换浅色主题" : "切换深色主题"} key="theme">
          <Switch
            aria-label="切换主题"
            checked={mode === "dark"}
            checkedChildren={<MoonOutlined />}
            unCheckedChildren={<SunOutlined />}
            onChange={onToggleTheme}
          />
        </Tooltip>,
        <Tooltip title="通知" key="notifications">
          <Button type="text" icon={<BellOutlined />} href="/notifications" aria-label="通知" />
        </Tooltip>,
      ]}
      token={{
        header: { colorBgHeader: mode === "dark" ? "#151b2a" : "#ffffff" },
        sider: { colorMenuBackground: mode === "dark" ? "#111827" : "#ffffff" },
      }}
    >
      <SkillsPage />
    </ProLayout>
  );
}

export default function ConsoleApp() {
  const [account, setAccount] = useState<Account | null>(null);
  const [booting, setBooting] = useState(true);
  const [mode, setMode] = useState<ThemeMode>(() =>
    localStorage.getItem(THEME_KEY) === "light" ? "light" : "dark",
  );

  useEffect(() => {
    document.body.classList.toggle("dark", mode === "dark");
    document.documentElement.style.colorScheme = mode;
    localStorage.setItem(THEME_KEY, mode);
  }, [mode]);

  useEffect(() => {
    let active = true;
    async function boot() {
      if (!getToken()) {
        setBooting(false);
        return;
      }
      try {
        const response = await consoleApi.me();
        if (active) setAccount(response.account);
      } catch (reason) {
        if (reason instanceof ApiError && reason.status === 401) setToken("");
      } finally {
        if (active) setBooting(false);
      }
    }
    void boot();
    return () => { active = false; };
  }, []);

  const themeConfig = useMemo(() => ({
    algorithm: mode === "dark"
      ? [theme.darkAlgorithm, theme.compactAlgorithm]
      : [theme.defaultAlgorithm, theme.compactAlgorithm],
    token: {
      colorPrimary: "#16b37a",
      borderRadius: 8,
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
    },
  }), [mode]);

  async function logout() {
    try { await consoleApi.logout(); } catch { /* local token removal is authoritative for this browser */ }
    setToken("");
    setAccount(null);
  }

  return (
    <ConfigProvider theme={themeConfig}>
      <AntApp>
        {booting ? (
          <div className="boot-screen"><Spin size="large" tip="正在连接 AgentMate Server…" /></div>
        ) : account ? (
          <ConsoleContent
            account={account}
            mode={mode}
            onToggleTheme={() => setMode((current) => current === "dark" ? "light" : "dark")}
            onLogout={() => void logout()}
          />
        ) : (
          <LoginPage onAuthenticated={setAccount} />
        )}
      </AntApp>
    </ConfigProvider>
  );
}
