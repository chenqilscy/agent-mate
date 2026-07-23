import { LockOutlined, UserOutlined } from "@ant-design/icons";
import { LoginForm, ProFormText } from "@ant-design/pro-components";
import { Alert, Card, Segmented, Typography } from "antd";
import { useState } from "react";
import { consoleApi, setToken } from "./api";
import type { Account } from "./types";

interface LoginPageProps {
  onAuthenticated: (account: Account) => void;
}

export default function LoginPage({ onAuthenticated }: LoginPageProps) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [error, setError] = useState("");

  async function submit(values: { name: string; password: string }) {
    setError("");
    try {
      const response = mode === "login"
        ? await consoleApi.login(values.name, values.password)
        : await consoleApi.register(values.name, values.password);
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
        <LoginForm<{ name: string; password: string }>
          title="欢迎回来"
          subTitle="管理项目、成员与 AgentMate 能力目录"
          submitter={{ searchConfig: { submitText: mode === "login" ? "登录" : "创建账号" } }}
          onFinish={submit}
        >
          <Segmented
            block
            className="login-mode"
            value={mode}
            options={[
              { label: "登录", value: "login" },
              { label: "注册", value: "register" },
            ]}
            onChange={(value) => {
              setMode(value as "login" | "register");
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
              { min: 4, message: "密码至少 4 个字符" },
            ]}
          />
        </LoginForm>
      </Card>
    </main>
  );
}
