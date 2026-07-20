# Langfuse 可观测性

AgentMate 在本机 backend 内直接向 Langfuse 上报 LLM 可观测数据，不经过前端或 AgentMate Server。
接入默认关闭；开启追踪后也默认只发送模型、轮次、耗时、token、工具名和匿名标识，不发送对话或文件正文。

## 配置

先在 Langfuse 项目设置中创建 API Keys，然后在 `backend/.env` 加入：

```env
LANGFUSE_ENABLED=1
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=http://localhost:3000
LANGFUSE_TRACING_ENVIRONMENT=development
LANGFUSE_SAMPLE_RATE=1.0
LANGFUSE_CAPTURE_CONTENT=0
```

修改后硬重启 backend。`GET /api/health` 的 `langfuse_configured: true` 只表示配置完整，
不会返回 URL 或 Key。Langfuse 网络或鉴权失败只影响观测数据，不会中断 SSE、工具调用或消息持久化。

若确实需要在私有 Langfuse 中调试提示词和结果，可显式设置 `LANGFUSE_CAPTURE_CONTENT=1`。
即使开启正文，后端仍会遮盖常见的 Authorization、API Key、token、secret、password、cookie，
并截断超过 8000 字符的单段文本；系统提示词、refs 和 reasoning 没有单独作为字段主动上报，
但 generation 输入会包含发送给模型的消息，因此开启前必须确认数据边界。

## Trace 结构

每次 `POST /api/chat` 建立一个 `agentmate.chat` agent observation：

```text
agentmate.chat
├─ llm.chat.round-1       generation
├─ <builtin tool>         tool / retriever
├─ <MCP tool>             tool
└─ llm.chat.round-N       generation
```

- Langfuse `session_id` 使用本地会话 UUID，跨多轮聚合同一对话。
- `user_id` 使用本地用户 ID 的 SHA-256 截断值，不上传姓名或邮箱。
- generation 记录模型、temperature、首 token 时间和 input/output token。
- `knowledge_retrieve` 记为 retriever，其他真实工具与 MCP 调用记为 tool。
- 用户停止、LLM 错误、工具异常和 SSE 取消都会关闭当前 observation。

## 验证

```powershell
cd backend
.\.venv\Scripts\python.exe -m unittest tests.regression.test_langfuse_telemetry -v
.\.venv\Scripts\python.exe -m py_compile agent\telemetry.py agent\runtime.py config.py main.py
```

完成一次包含工具调用的真实聊天后，在 Langfuse Traces 中检查：

1. 一个 `agentmate.chat` 根记录；
2. 至少一条 generation，工具场景下有 tool/retriever 子记录；
3. session、model、TTFT 与 token usage 正确；
4. `LANGFUSE_CAPTURE_CONTENT=0` 时 input/output 只有类型、字段名和长度摘要。

应用退出时 `main.py` 会调用 Langfuse `shutdown()`，等待后台批次完成。
