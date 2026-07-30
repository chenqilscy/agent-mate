"""自托管 WeKnora（腾讯开源 RAG）REST 客户端（WB-173）。

AgentMate 后端当 WeKnora 的客户端：`X-API-Key` 打 `{url}/api/v1`（默认 http://localhost:8080）。
WeKnora 自己做解析/切片/嵌入/向量库/检索——本后端只建库/传档/列删/检索，**不再用 GLM 托管 KB**。
嵌入 provider 在 WeKnora 侧配置（本项目定为 GLM embedding-3 的 OpenAI 兼容接口，见 docs/weknora-部署.md）。

配置按 owner 解析（WB-188）：**DB 优先、backend/.env 兜底**——用户在 UI 表单里填的连接配置
存本机 DB（`db.get_weknora_conf`，api_key 在 provider_keys 表），没填过则回退 `settings.WEKNORA_*`
（存量 .env 用户零破坏）。故所有公开函数都要 `owner_id`：地址/密钥是每个 owner 各自的。
api_key 只在后端用，绝不回前端（铁律#4）。

同步 httpx 客户端（照 `glm_kb.py`/`server_client.py` 写法）——调用方必须在工作线程里跑
（路由 `run_in_threadpool` / 工具 `asyncio.to_thread`），别占事件循环（WB-002）。

⚠️ 首版按 WeKnora `docs/api/*` 编写；接口 envelope / 字段以其运行实例（Swagger）为准，接通后按真响应校准。
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, NamedTuple, Optional
from urllib.parse import urlsplit

import httpx

from config import settings

# 建库/检索快；传文件走 docreader 异步解析，上传本身也应很快返回（parse_status=pending）。
_TIMEOUT = 60.0

# WeKnora <=0.2.11 的 URL 入库曾存在重定向 SSRF 绕过。AgentMate 无法从调用侧
# 约束远端 WeKnora 最终怎样下载，故每次 URL 入库都从服务本身读取版本并 fail-closed。
# 不缓存：若管理员把服务降级，下一次调用必须立即停止。
MIN_SAFE_URL_IMPORT_VERSION = (0, 2, 12)

# 未接入的统一文案（WB-188）：引导去 UI 表单，而不是让用户改配置文件。
NOT_CONFIGURED = (
    "尚未接入知识库：请在「连接器 → WeKnora知识库」里填写服务地址与 API Key（也可继续用 backend/.env 配置）。"
    "部署见 docs/weknora-部署.md。"
)

# WeKnora（docreader）能解析的文件类型。上传前软校验（未知扩展名放行，交 WeKnora 判）。
SUPPORTED_EXTS = {
    "pdf", "doc", "docx", "txt", "md", "markdown", "html", "htm",
    "csv", "xls", "xlsx", "ppt", "pptx",
    "png", "jpg", "jpeg", "gif", "bmp", "webp",
}


class WeKnoraError(Exception):
    """WeKnora 返回非成功，或网络/解析出错。message 面向用户可读。"""


class Conf(NamedTuple):
    """某 owner 生效的 WeKnora 连接配置 + 每个字段的来源（'db' / 'env' / ''=未配）。"""
    url: str
    api_key: str
    embedding_model_id: str
    key_source: str
    url_source: str


def conf(owner_id: Optional[str]) -> Conf:
    """解析本 owner 生效的配置：DB 优先，.env 兜底（WB-188）。owner_id=None → 只看 .env。

    延迟导入 db：weknora 被 agent.tools 延迟导入，这里再反向 import storage.db 若放模块顶层
    会与加载顺序耦合（照 tools.py 的做法）。"""
    row = {"url": "", "api_key": "", "embedding_model_id": ""}
    if owner_id:
        from storage import db  # 局部导入，避免加载顺序耦合

        row = db.get_weknora_conf(owner_id)
    url = (row["url"] or settings.WEKNORA_URL or "").rstrip("/")
    return Conf(
        url=url,
        api_key=row["api_key"] or settings.WEKNORA_API_KEY,
        embedding_model_id=row["embedding_model_id"] or settings.WEKNORA_EMBEDDING_MODEL_ID,
        key_source="db" if row["api_key"] else ("env" if settings.WEKNORA_API_KEY else ""),
        url_source="db" if row["url"] else ("env" if settings.WEKNORA_URL else ""),
    )


def configured(owner_id: Optional[str]) -> bool:
    """本 owner 是否已接入（有 key 即可；url 有默认值）。"""
    c = conf(owner_id)
    return bool(c.api_key) and _claim_connection(owner_id, c)


def _connection_scope(c: Conf) -> str:
    """Stable, secret-free identifier for one WeKnora tenant connection."""
    material = f"{c.url}\0{c.api_key}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _claim_connection(owner_id: Optional[str], c: Conf) -> bool:
    if not owner_id:
        return True
    from storage import db

    return db.claim_weknora_connection(_connection_scope(c), owner_id)


def _headers(c: Conf, extra: Optional[dict] = None) -> dict[str, str]:
    h = {"X-API-Key": c.api_key}
    if extra:
        h.update(extra)
    return h


def _api(c: Conf, path: str) -> str:
    return f"{c.url}/api/v1{path}"


def _err_msg(body: Any) -> Optional[str]:
    """WeKnora 错误体的可读 message：顶层 {message}，或嵌套 {error:{message|details}}。
    真实实例返回形如 {"error":{"code":1000,"details":"EOF","message":"..."},"success":false}。"""
    if not isinstance(body, dict):
        return None
    if body.get("message"):
        return str(body["message"])
    err = body.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or err.get("details") or "") or None
    if isinstance(err, str) and err:
        return err
    return None


def _unwrap(r: httpx.Response) -> Any:
    """解析 WeKnora 响应。约定：2xx 且 body 形如 {data, success} → data；{code,message,data} 按 code 判。
    非 2xx / success=false / code!=0(200) → WeKnoraError(message)。空 body 的 2xx（如 DELETE）→ None。"""
    if r.status_code in (401, 403):
        raise WeKnoraError("WeKnora 鉴权失败：API Key 无效或已失效，请在「连接器 → WeKnora知识库」里重填租户 API Key。")
    if 200 <= r.status_code < 300 and not (r.content or b"").strip():
        return None
    try:
        body = r.json()
    except Exception as e:  # noqa: BLE001
        raise WeKnoraError(f"WeKnora 返回无法解析（HTTP {r.status_code}）：{r.text[:200]}") from e
    if not (200 <= r.status_code < 300):
        raise WeKnoraError(_err_msg(body) or f"WeKnora 错误（HTTP {r.status_code}）")
    if isinstance(body, dict):
        if body.get("success") is False:
            raise WeKnoraError(_err_msg(body) or "WeKnora 请求失败。")
        code = body.get("code")
        if code is not None:
            try:
                if int(code) not in (0, 200):
                    raise WeKnoraError(str(body.get("message") or f"WeKnora 错误（code={code}）"))
            except (TypeError, ValueError):
                pass
        return body.get("data", body)
    return body


def _request(owner_id: Optional[str], method: str, path: str, **kw: Any) -> Any:
    c = conf(owner_id)
    if not c.api_key:
        raise WeKnoraError(NOT_CONFIGURED)
    if not _claim_connection(owner_id, c):
        raise WeKnoraError(
            "当前 WeKnora 连接已绑定到此设备上的另一个账号。"
            "请为当前账号配置独立的 WeKnora 租户/API Key；团队知识请使用 Server 项目知识库。"
        )
    try:
        r = httpx.request(method, _api(c, path), headers=_headers(c, kw.pop("_headers", None)),
                          timeout=_TIMEOUT, **kw)
    except httpx.HTTPError as e:
        raise WeKnoraError(f"连接 WeKnora 失败（{c.url}）：{e}") from e
    return _unwrap(r)


def _as_list(data: Any) -> list[dict]:
    """WeKnora 列表响应可能是 [...] 或 {data:[...],total} 或 {list:[...]}。归一成 list。"""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("data", "list", "items"):
            v = data.get(k)
            if isinstance(v, list):
                return v
    return []


# ── 知识库 CRUD ──────────────────────────────────────────────────────────────

def create_kb(owner_id: Optional[str], *, name: str, embedding_model_id: str, description: str = "",
              chunk_size: int = 1000, chunk_overlap: int = 200) -> dict:
    body: dict[str, Any] = {
        "name": name,
        "type": "document",
        "embedding_model_id": embedding_model_id,
        "chunking_config": {"chunk_size": int(chunk_size), "chunk_overlap": int(chunk_overlap)},
    }
    if description:
        body["description"] = description
    data = _request(owner_id, "POST", "/knowledge-bases", json=body)
    return data if isinstance(data, dict) else {"id": data}


def list_kb(owner_id: Optional[str]) -> list[dict]:
    return _as_list(_request(owner_id, "GET", "/knowledge-bases"))


def get_kb(owner_id: Optional[str], kb_id: str) -> dict:
    d = _request(owner_id, "GET", f"/knowledge-bases/{kb_id}")
    return d if isinstance(d, dict) else {}


def update_kb(owner_id: Optional[str], kb_id: str, **fields: Any) -> None:
    body = {k: v for k, v in fields.items() if v is not None}
    _request(owner_id, "PUT", f"/knowledge-bases/{kb_id}", json=body)


def delete_kb(owner_id: Optional[str], kb_id: str) -> None:
    _request(owner_id, "DELETE", f"/knowledge-bases/{kb_id}")


# ── 文档 ─────────────────────────────────────────────────────────────────────

def upload_file(owner_id: Optional[str], kb_id: str, *, filename: str, content: bytes,
                content_type: str = "application/octet-stream") -> dict:
    """传单文件 → WeKnora 异步解析（返回含 id + parse_status=processing）。multipart 字段名 `file`。"""
    d = _request(
        owner_id, "POST", f"/knowledge-bases/{kb_id}/knowledge/file",
        files={"file": (filename, content, content_type)},
    )
    return d if isinstance(d, dict) else {"id": d}


def system_info(owner_id: Optional[str]) -> dict:
    """读取 WeKnora 自报的构建信息；URL 入库用其中 version 做安全门禁。"""
    d = _request(owner_id, "GET", "/system/info")
    return d if isinstance(d, dict) else {}


def _stable_version(raw: Any) -> tuple[int, int, int] | None:
    """只接受明确的稳定 semver；未知/预发布版本不能作为安全证明。"""
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:\+[0-9A-Za-z.-]+)?", str(raw or "").strip())
    return tuple(map(int, m.groups())) if m else None


def require_safe_url_import(owner_id: Optional[str]) -> str:
    """确认 WeKnora URL 下载端已包含重定向 SSRF 修复；无法证明时保守拒绝。"""
    minimum = ".".join(map(str, MIN_SAFE_URL_IMPORT_VERSION))
    try:
        info = system_info(owner_id)
    except WeKnoraError as e:
        raise WeKnoraError(
            "为安全起见未执行 URL 入库：无法通过 WeKnora /api/v1/system/info 确认服务版本。"
            f"请升级到稳定版 >= {minimum} 并确保租户 API Key 可读取 system/info；工作区 path 文件入库仍可用。"
            f"原始错误：{e}"
        ) from e
    raw = str(info.get("version") or "").strip()
    parsed = _stable_version(raw)
    if parsed is None:
        shown = raw or "未返回"
        raise WeKnoraError(
            f"为安全起见未执行 URL 入库：WeKnora 版本无法可靠识别（{shown}）。"
            f"需要稳定版 >= {minimum}；工作区 path 文件入库仍可用。"
        )
    if parsed < MIN_SAFE_URL_IMPORT_VERSION:
        raise WeKnoraError(
            f"为安全起见未执行 URL 入库：当前 WeKnora {raw} 低于安全最低版本 {minimum}，"
            "存在 URL 重定向 SSRF 风险。请先升级；工作区 path 文件入库仍可用。"
        )
    return raw


def validate_import_url(raw: str) -> str:
    url = str(raw or "").strip()
    if not url or len(url) > 2048:
        raise WeKnoraError("URL 格式非法：请提供不超过 2048 字符的 http(s) URL。")
    try:
        parsed = urlsplit(url)
        port = parsed.port  # 触发非法端口校验
    except ValueError as e:
        raise WeKnoraError(f"URL 格式非法：{e}") from e
    if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
        raise WeKnoraError("URL 格式非法：仅支持包含主机名的 http(s) URL。")
    if parsed.username is not None or parsed.password is not None:
        raise WeKnoraError("URL 格式非法：不允许在 URL 中携带用户名或密码。")
    _ = port
    return url


def _looks_like_ssrf_rejection(message: str) -> bool:
    text = message.lower()
    return any(marker in text for marker in (
        "ssrf", "whitelist", "private", "loopback", "link-local",
        "白名单", "内网", "回环", "invalid url", "unsafe url",
    ))


def create_from_url(owner_id: Optional[str], kb_id: str, *, url: str) -> dict:
    """从网页/远程文件 URL 创建知识；仅允许已证明包含 SSRF 修复的 WeKnora。"""
    target = validate_import_url(url)
    require_safe_url_import(owner_id)
    try:
        d = _request(
            owner_id, "POST", f"/knowledge-bases/{kb_id}/knowledge/url",
            json={"url": target},
        )
    except WeKnoraError as e:
        if _looks_like_ssrf_rejection(str(e)):
            raise WeKnoraError(
                "WeKnora 拒绝该 URL（SSRF 安全策略）。请在 WeKnora 管理端「系统设置 → SSRF 白名单」"
                "只添加确实可信的目标域名；旧版部署可设置 SSRF_WHITELIST_EXTRA 后重启。"
                "不要为不受信任的域名或整段私网放宽规则。"
                f"原始错误：{e}"
            ) from e
        raise
    return d if isinstance(d, dict) else {"id": d}


def list_docs(owner_id: Optional[str], kb_id: str, *, page: int = 1, page_size: int = 100) -> dict:
    """列文档 → {list:[{id, file_name, parse_status, ...}], total}。parse_status:
    pending/processing/finalizing → 处理中 · completed → 完成 · failed → 失败。"""
    data = _request(owner_id, "GET", f"/knowledge-bases/{kb_id}/knowledge",
                    params={"page": page, "page_size": page_size})
    items = _as_list(data)
    total = data.get("total", len(items)) if isinstance(data, dict) else len(items)
    return {"list": items, "total": total}


def delete_doc(owner_id: Optional[str], doc_id: str) -> None:
    _request(owner_id, "DELETE", f"/knowledge/{doc_id}")


# ── 检索 ─────────────────────────────────────────────────────────────────────

def search(owner_id: Optional[str], *, query: str, knowledge_ids: list[str], top_k: int = 8) -> list[dict]:
    """知识检索 → 归一成 [{text, score, metadata:{doc_name, doc_id}}]（与旧 glm_kb.retrieve 同形状，
    故 agent 工具与前端零改）。WeKnora 命中字段：content / score / knowledge_filename / knowledge_id。"""
    body = {"query": query[:1000], "knowledge_base_ids": knowledge_ids, "top_k": max(1, min(top_k, 20))}
    data = _request(owner_id, "POST", "/knowledge-search", json=body)
    out = []
    for h in _as_list(data):
        if not isinstance(h, dict):
            continue
        out.append({
            "text": str(h.get("content") or h.get("text") or "").strip(),
            "score": h.get("score"),
            "metadata": {
                "doc_name": h.get("knowledge_filename") or h.get("knowledge_title") or "",
                "doc_id": h.get("knowledge_id") or h.get("id") or "",
            },
        })
    return out


# ── 诊断 ─────────────────────────────────────────────────────────────────────

def list_models(owner_id: Optional[str]) -> list[dict]:
    """列 WeKnora 已注册模型（找 embedding 模型 id 用；部署/排障辅助）。"""
    return _as_list(_request(owner_id, "GET", "/models"))


def default_embedding_model_id(owner_id: Optional[str]) -> str:
    """建库要指定嵌入模型 id：优先本 owner 配的（UI 表单 → DB，或 .env 兜底），
    未配则向 WeKnora 现取第一个 Embedding 模型（部署里已注册 GLM embedding-3）。都没有则报错引导。"""
    want = conf(owner_id).embedding_model_id
    if want:
        return want
    for m in list_models(owner_id):
        if isinstance(m, dict) and str(m.get("type", "")).lower() == "embedding" and m.get("id"):
            return str(m["id"])
    raise WeKnoraError(
        "WeKnora 未注册任何嵌入模型：请在 WeKnora 控制台注册一个 Embedding 模型，"
        "或在「连接器 → WeKnora知识库」里指定嵌入模型 id（见 docs/weknora-部署.md）。"
    )
