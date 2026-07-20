# WeKnora 私有化部署 + 接入 AgentMate（WB-173）

AgentMate 知识库改用**自托管 WeKnora**（腾讯开源 RAG）做解析/切片/嵌入/向量库/检索。WeKnora 自己跑一套
Docker 服务，AgentMate 后端只当它的**客户端**（`X-API-Key` 打 `http://localhost:8080/api/v1`）。嵌入用
**GLM `embedding-3` 的 OpenAI 兼容接口**（复用你的智谱 key，只调嵌入、不碰 GLM 知识库）。

跟着这份跑一遍，最后把 **3 个值**填进 `backend/.env` 就接通了。跑不通把报错贴我。

> ✅ **本机现状（2026-07-16 已接入并实测）**：WeKnora 实例跑在 **`http://localhost:37200`**（非本指南默认的 :8080，
> 端口以你的部署为准）；已注册 GLM `embedding-3` 嵌入模型。`backend/.env` 现有值：
> `WEKNORA_URL=http://localhost:37200`、`WEKNORA_API_KEY=sk-…`（租户 key，只在后端）、
> `WEKNORA_EMBEDDING_MODEL_ID=668e2596-…`。下面 :8080 的示例把端口换成 **37200** 即与本机一致。
> 改了 `backend/.env` 后**须硬重启 backend(:8000)**——`reload=True` 不会重读 .env，历史上还有「serving stale code」。

---

## 0. 前置

- **启动 Docker Desktop**（本机已装 Docker 29 + Compose v5，但守护进程当前没开——先把 Docker Desktop 打开、等它变绿）。
- 一个**智谱 API Key**（open.bigmodel.cn，用于 WeKnora 侧算嵌入向量）。
- 约 8GB 空闲内存、几 GB 磁盘（postgres/redis/docreader 镜像）。

## 1. 拉取 + 配置 .env

```bash
git clone https://github.com/Tencent/WeKnora.git
cd WeKnora
cp .env.example .env
```

编辑 `.env`，**只需改/确认这几项**（其余保持默认；默认向量库就是自带的 postgres/pgvector，无需额外服务）：

```dotenv
# —— 向量库 & 存储：默认即可（自带 postgres 向量库 + 本地文件存储）——
RETRIEVE_DRIVER=postgres
STORAGE_TYPE=local

# —— 嵌入模型：指向 GLM embedding-3 的 OpenAI 兼容端点 ——
EMBEDDING_PROVIDER=openai
EMBEDDING_BASE_URL=https://open.bigmodel.cn/api/paas/v4
EMBEDDING_MODEL_NAME=embedding-3
EMBEDDING_API_KEY=<你的智谱 API Key>

# —— 安全密钥：把默认值改成你自己的随机串（SYSTEM_AES_KEY 必须正好 32 字节）——
SYSTEM_AES_KEY=<32 字节随机串，例如 openssl rand -hex 16 的 32 位十六进制>
TENANT_AES_KEY=<随机串>
JWT_SECRET=<随机串>
WEKNORA_API_KEY=<随机串>        # 这是 WeKnora 内部 MCP 用的，不是下面给 AgentMate 的那个

# —— 想用 Swagger 在线看接口就把 release 改成 debug（可选）——
# GIN_MODE=debug
```

> ⚠️ **两个「API Key」别搞混**：`.env` 里的 `WEKNORA_API_KEY` 是 WeKnora **内部 MCP** 用的；
> 给 AgentMate 用的是第 3 步注册账号后拿到的**租户 API Key（`sk-...`）**。

生成随机串（Git Bash）：`openssl rand -hex 16`（32 位十六进制 = 恰好 32 字节，给 `SYSTEM_AES_KEY`）。

## 2. 起服务

```bash
docker compose up -d
```

起来 5 个核心服务：`frontend(:80)`、`app(API :8080)`、`docreader(:50051, 文档解析)`、`postgres(:5432)`、`redis(:6379)`。
首次拉镜像稍慢。查状态：`docker compose ps`；看日志：`docker compose logs -f app`。

## 3. 注册账号，拿**租户 API Key**

- 浏览器开 `http://localhost` （FRONTEND_PORT=80）。
- 注册一个账号并登录（`.env` 默认 `DISABLE_REGISTRATION=false`，允许注册）。
- 进**账号/个人信息页**，复制 **API Key（形如 `sk-xxxxxxxx`）**。**这个就是要给 AgentMate 的 `WEKNORA_API_KEY`。**

## 4. 注册嵌入模型，拿 `embedding_model_id`

建知识库时要指定用哪个嵌入模型的 id。用刚拿到的租户 key 调注册接口（把 `sk-...` 和智谱 key 换成你的）：

```bash
curl -s -X POST http://localhost:8080/api/v1/models \
  -H "X-API-Key: sk-你的租户key" -H "Content-Type: application/json" \
  -d '{
    "name": "embedding-3",
    "type": "Embedding",
    "source": "remote",
    "description": "GLM embedding-3 (OpenAI 兼容)",
    "parameters": {
      "base_url": "https://open.bigmodel.cn/api/paas/v4",
      "api_key": "你的智谱key",
      "provider": "openai",
      "embedding_parameters": { "dimension": 2048 }
    }
  }'
```

返回体里的 `id` 就是 **`embedding_model_id`**。（也可在 WeKnora 的 Web 界面「模型/设置」里配，等价。）
列出确认：`curl -s http://localhost:8080/api/v1/models -H "X-API-Key: sk-你的租户key"`。

## 5. 冒烟验证

```bash
# 能列知识库（空列表也算通）就说明 API + 鉴权 OK
curl -s http://localhost:8080/api/v1/knowledge-bases -H "X-API-Key: sk-你的租户key"
```

想看全部接口：把 `.env` 的 `GIN_MODE=debug` 后 `docker compose up -d` 重启，开
`http://localhost:8080/swagger/index.html`。

## 6. 接进 AgentMate

把 3 个值填进 **`backend/.env`**（只存后端、绝不进前端）：

```dotenv
WEKNORA_URL=http://localhost:8080
WEKNORA_API_KEY=sk-你的租户key          # 第 3 步的租户 API Key
WEKNORA_EMBEDDING_MODEL_ID=第4步返回的id
```

填好告诉我，我把后端客户端接上、跑端到端实测（建库→传 pdf/md→解析完成→挂载对话检索）。

---

## 排障

- **`docker compose` 报连不上守护进程**：Docker Desktop 没开或没就绪，等它变绿再来。
- **80 端口被占**：改 `.env` 的 `FRONTEND_PORT`（如 8081），`docker compose up -d` 重启，前端就走新端口（`:8080` API 端口不变）。
- **传文档一直 processing**：`docreader` 在解析大/复杂文件，看 `docker compose logs -f docreader`；嵌入失败常是
  `EMBEDDING_API_KEY`/`EMBEDDING_BASE_URL` 配错或智谱余额问题。
- **停服务**：`docker compose down`（保留数据卷）；**连数据一起清**：`docker compose down -v`。

> 接口路径/字段以 WeKnora 官方仓库与其 Swagger 为准（本指南据其 `docs/api/*` 与 `.env.example` 编写，版本更新可能微调）。
