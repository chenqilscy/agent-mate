import { LockOutlined, UserOutlined } from "@ant-design/icons";
import { LoginForm, ProFormText } from "@ant-design/pro-components";
import { Alert, Button, Card, Divider, Input, Segmented, Space, Typography } from "antd";
import { useEffect, useState } from "react";
import { consoleApi, setToken } from "./api";
import type { Account } from "./types";

interface LoginPageProps {
  onAuthenticated: (account: Account) => void;
}

export default function LoginPage({ onAuthenticated }: LoginPageProps) {
  const [mode, setMode] = useState<"login" | "register" | "bootstrap">("login");
  const [error, setError] = useState("");
  const [providers, setProviders] = useState<{ id: string; label: string }[]>([]);
  const [inviteCode, setInviteCode] = useState("");
  const [ssoBusy, setSsoBusy] = useState("");
  const [canRegister, setCanRegister] = useState(false);
  const [minPasswordLength, setMinPasswordLength] = useState(12);
  const [canBootstrap, setCanBootstrap] = useState(false);

  useEffect(() => {
    void consoleApi.ssoProviders()
      .then((result) => setProviders(result.providers))
      .catch(() => setProviders([]));
    void consoleApi.authCapabilities().then((result) => {
      setCanRegister(result.password_registration);
      setCanBootstrap(result.bootstrap_available);
      setMinPasswordLength(result.min_password_length || 12);
    }).catch(() => setCanRegister(false));
  }, []);

  async function startSso(provider: string) {
    setError("");
    setSsoBusy(provider);
    let popup: Window | null = null;
    try {
      const attempt = await consoleApi.ssoStart(provider, inviteCode.trim());
      popup = window.open(attempt.auth_url, "_blank", "noopener,noreferrer");
      if (!popup) throw new Error("浏览器阻止了登录弹窗");
      const deadline = Math.min(attempt.expires_at * 1000, Date.now() + 10 * 60_000);
      while (Date.now() < deadline) {
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
        const result = await consoleApi.ssoPoll(attempt.attempt_id, attempt.attempt_token);
        if (result.status === "error") throw new Error(result.error_code || "联合登录失败");
        if (result.status === "completed" && result.token && result.account) {
          setToken(result.token);
          popup.close();
          onAuthenticated(result.account);
          return;
        }
      }
      throw new Error("联合登录已超时，请重试");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "联合登录失败");
    } finally {
      popup?.close();
      setSsoBusy("");
    }
  }

  async function submit(values: { name: string; password: string; bootstrap_secret?: string }) {
    setError("");
    try {
      const response = mode === "login"
        ? await consoleApi.login(values.name, values.password)
        : mode === "register"
          ? await consoleApi.register(values.name, values.password)
          : await consoleApi.bootstrapAdmin(values.name, values.password, values.bootstrap_secret || "");
      setToken(response.token);
      onAuthenticated(response.account);
      return true;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "登录失败");
      return false;
    }
  }

  return (
    <main className="login-shell">
      <section className="login-brand">
        <div className="brand-mark brand-mark-large">C</div>
        <Typography.Title level={1}>AgentMate Console</Typography.Title>
        <Typography.Paragraph>
          AgentMate Server 的专业管理控制台
        </Typography.Paragraph>
      </section>
      <Card className="login-card" bordered={false}>
        <LoginForm<{ name: string; password: string; bootstrap_secret?: string }>
          title="欢迎回来"
          subTitle="管理项目、成员与 AgentMate 平台能力"
          submitter={{ searchConfig: { submitText: mode === "login" ? "登录" : mode === "bootstrap" ? "初始化管理员" : "创建账号" } }}
          onFinish={submit}
        >
          <Segmented
            block
            className="login-mode"
            value={mode}
            options={[
              { label: "登录", value: "login" },
              ...(canRegister ? [{ label: "注册", value: "register" }] : []),
              ...(canBootstrap ? [{ label: "初始化", value: "bootstrap" }] : []),
            ]}
            onChange={(value) => {
              setMode(value as "login" | "register" | "bootstrap");
              setError("");
            }}
          />
          {error ? <Alert type="error" showIcon title={error} className="login-error" /> : null}
          <ProFormText
            name="name"
            fieldProps={{ size: "large", prefix: <UserOutlined />, autoComplete: "username" }}
            placeholder="账号名称"
            rules={[{ required: true, message: "请输入账号名称" }]}
          />
          <ProFormText.Password
            name="password"
            fieldProps={{ size: "large", prefix: <LockOutlined />, autoComplete: mode === "login" ? "current-password" : "new-password" }}
            placeholder="密码"
            rules={[
              { required: true, message: "请输入密码" },
              ...(mode !== "login" ? [{ min: minPasswordLength, message: `密码至少 ${minPasswordLength} 个字符` }] : []),
            ]}
          />
          {mode === "bootstrap" ? <ProFormText.Password name="bootstrap_secret" fieldProps={{ size: "large", prefix: <LockOutlined />, autoComplete: "off" }} placeholder="一次性 Bootstrap Secret" rules={[{ required: true, message: "请输入部署时配置的一次性 Secret" }]} /> : null}
          {mode === "login" && providers.length > 0 ? (
            <div className="login-sso">
              <Divider plain>或使用联合登录</Divider>
              <Input
                value={inviteCode}
                onChange={(event) => setInviteCode(event.target.value)}
                placeholder="首次注册邀请码（已有绑定可留空）"
              />
              <Space wrap className="login-sso-actions">
                {providers.map((provider) => (
                  <Button
                    key={provider.id}
                    loading={ssoBusy === provider.id}
                    disabled={Boolean(ssoBusy) && ssoBusy !== provider.id}
                    onClick={() => void startSso(provider.id)}
                  >
                    {provider.label}
                  </Button>
                ))}
              </Space>
            </div>
          ) : null}
        </LoginForm>
      </Card>
    </main>
  );
}
