"""自托管 WeKnora（腾讯开源 RAG）REST 客户端（WB-173）。

WorkBuddy 后端当 WeKnora 的客户端：`X-API-Key` 打 `{WEKNORA_URL}/api/v1`（默认 http://localhost:8080）。
WeKnora 自己做解析/切片/嵌入/向量库/检索——本后端只建库/传档/列删/检索，**不再用 GLM 托管 KB**。
嵌入 provider 在 WeKnora 侧配置（本项目定为 GLM embedding-3 的 OpenAI 兼容接口，见 docs/weknora-部署.md）。

同步 httpx 客户端（照 `glm_kb.py`/`hub_client.py` 写法）——调用方必须在工作线程里跑
（路由 `run_in_threadpool` / 工具 `asyncio.to_thread`），别占事件循环（WB-002）。

⚠️ 首版按 WeKnora `docs/api/*` 编写；接口 envelope / 字段以其运行实例（Swagger）为准，接通后按真响应校准。
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

from config import settings

# 建库/检索快；传文件走 docreader 异步解析，上传本身也应很快返回（parse_status=pending）。
_TIMEOUT = 60.0

# WeKnora（docreader）能解析的文件类型。上传前软校验（未知扩展名放行，交 WeKnora 判）。
SUPPORTED_EXTS = {
    "pdf", "doc", "docx", "txt", "md", "markdown", "html", "htm",
    "csv", "xls", "xlsx", "ppt", "pptx",
    "png", "jpg", "jpeg", "gif", "bmp", "webp",
}


class WeKnoraError(Exception):
    """WeKnora 返回非成功，或网络/解析出错。message 面向用户可读。"""


def configured() -> bool:
    return bool(settings.WEKNORA_API_KEY)


def _headers(extra: Optional[dict] = None) -> dict[str, str]:
    h = {"X-API-Key": settings.WEKNORA_API_KEY}
    if extra:
        h.update(extra)
    return h


def _api(path: str) -> str:
    return f"{settings.WEKNORA_URL}/api/v1{path}"


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
        raise WeKnoraError("WeKnora 鉴权失败：请检查 WEKNORA_API_KEY（租户 API Key）。")
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


def _request(method: str, path: str, **kw: Any) -> Any:
    if not configured():
        raise WeKnoraError("未配置 WeKnora：请在 backend/.env 设 WEKNORA_API_KEY（见 docs/weknora-部署.md）。")
    try:
        r = httpx.request(method, _api(path), headers=_headers(kw.pop("_headers", None)),
                          timeout=_TIMEOUT, **kw)
    except httpx.HTTPError as e:
        raise WeKnoraError(f"连接 WeKnora 失败（{settings.WEKNORA_URL}）：{e}") from e
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

def create_kb(*, name: str, embedding_model_id: str, description: str = "",
              chunk_size: int = 1000, chunk_overlap: int = 200) -> dict:
    body: dict[str, Any] = {
        "name": name,
        "type": "document",
        "embedding_model_id": embedding_model_id,
        "chunking_config": {"chunk_size": int(chunk_size), "chunk_overlap": int(chunk_overlap)},
    }
    if description:
        body["description"] = description
    data = _request("POST", "/knowledge-bases", json=body)
    return data if isinstance(data, dict) else {"id": data}


def list_kb() -> list[dict]:
    return _as_list(_request("GET", "/knowledge-bases"))


def get_kb(kb_id: str) -> dict:
    d = _request("GET", f"/knowledge-bases/{kb_id}")
    return d if isinstance(d, dict) else {}


def update_kb(kb_id: str, **fields: Any) -> None:
    body = {k: v for k, v in fields.items() if v is not None}
    _request("PUT", f"/knowledge-bases/{kb_id}", json=body)


def delete_kb(kb_id: str) -> None:
    _request("DELETE", f"/knowledge-bases/{kb_id}")


# ── 文档 ─────────────────────────────────────────────────────────────────────

def upload_file(kb_id: str, *, filename: str, content: bytes,
                content_type: str = "application/octet-stream") -> dict:
    """传单文件 → WeKnora 异步解析（返回含 id + parse_status=processing）。multipart 字段名 `file`。"""
    d = _request(
        "POST", f"/knowledge-bases/{kb_id}/knowledge/file",
        files={"file": (filename, content, content_type)},
    )
    return d if isinstance(d, dict) else {"id": d}


def list_docs(kb_id: str, *, page: int = 1, page_size: int = 100) -> dict:
    """列文档 → {list:[{id, file_name, parse_status, ...}], total}。parse_status:
    pending/processing/finalizing → 处理中 · completed → 完成 · failed → 失败。"""
    data = _request("GET", f"/knowledge-bases/{kb_id}/knowledge",
                    params={"page": page, "page_size": page_size})
    items = _as_list(data)
    total = data.get("total", len(items)) if isinstance(data, dict) else len(items)
    return {"list": items, "total": total}


def delete_doc(doc_id: str) -> None:
    _request("DELETE", f"/knowledge/{doc_id}")


# ── 检索 ─────────────────────────────────────────────────────────────────────

def search(*, query: str, knowledge_ids: list[str], top_k: int = 8) -> list[dict]:
    """知识检索 → 归一成 [{text, score, metadata:{doc_name, doc_id}}]（与旧 glm_kb.retrieve 同形状，
    故 agent 工具与前端零改）。WeKnora 命中字段：content / score / knowledge_filename / knowledge_id。"""
    body = {"query": query[:1000], "knowledge_base_ids": knowledge_ids, "top_k": max(1, min(top_k, 20))}
    data = _request("POST", "/knowledge-search", json=body)
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

def list_models() -> list[dict]:
    """列 WeKnora 已注册模型（找 embedding 模型 id 用；部署/排障辅助）。"""
    return _as_list(_request("GET", "/models"))


def default_embedding_model_id() -> str:
    """建库要指定嵌入模型 id：优先 settings.WEKNORA_EMBEDDING_MODEL_ID（.env 配置），
    未配则向 WeKnora 现取第一个 Embedding 模型（部署里已注册 GLM embedding-3）。都没有则报错引导。"""
    if settings.WEKNORA_EMBEDDING_MODEL_ID:
        return settings.WEKNORA_EMBEDDING_MODEL_ID
    for m in list_models():
        if isinstance(m, dict) and str(m.get("type", "")).lower() == "embedding" and m.get("id"):
            return str(m["id"])
    raise WeKnoraError(
        "WeKnora 未注册任何嵌入模型：请在 WeKnora 控制台注册一个 Embedding 模型，"
        "或在 backend/.env 设 WEKNORA_EMBEDDING_MODEL_ID（见 docs/weknora-部署.md）。"
    )
