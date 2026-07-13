"""GLM（智谱 / bigmodel）知识库 REST 客户端（WB-142）。

薄 httpx 封装，参照 `backend/hub_client.py` 的同步写法——**同步阻塞**调用，调用方
（路由 / agent 工具）必须在工作线程里跑（路由用 `run_in_threadpool`，工具由
`runtime.py` 的 `asyncio.to_thread` 兜住），别占事件循环（WB-002 教训）。

鉴权：`Authorization: Bearer {zhipu_key}`——key 由调用方传入（路由用
`db.get_provider_key(owner_id, "zhipu")` 取，**绝不回传前端**，铁律#4）。

覆盖：建库 / 列库 / 详情 / 编辑 / 删库 / 用量 / 传文件 / 传URL / 文档列表 /
删文档 / 文本检索 / 全模态检索（上下文增强 = 建库时 contextual=1）。
API 参考：https://docs.bigmodel.cn/api-reference/知识库-api/
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

# 知识库服务的固定 host（与 chat 的 /api/paas/v4 不同域，故不复用 provider base）。
GLM_APP_BASE = "https://open.bigmodel.cn/api/llm-application/open"
GLM_ZRAG_BASE = "https://open.bigmodel.cn/api/zrag"

# 建库/检索快；传文件/向量化触发可能慢些，给足超时。
_TIMEOUT = 30.0

# embedding_id → 名称（建库/编辑用）。3=Embedding-2, 11=Embedding-3, 12=Embedding-3-pro。
EMBEDDINGS = {3: "Embedding-2", 11: "Embedding-3", 12: "Embedding-3-pro"}
# 支持的上传文件后缀（GLM 文档）。
SUPPORTED_EXTS = {"txt", "doc", "docx", "pdf", "md", "ppt", "pptx", "xls", "xlsx", "csv", "url"}


class GlmKbError(Exception):
    """GLM 知识库 API 返回非成功码，或网络/解析出错。message 面向用户可读。"""


def _headers(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def _unwrap(r: httpx.Response) -> Any:
    """解析 `{code,data,message}`：code==200 → data；否则抛 GlmKbError(message)。"""
    if r.status_code == 401 or r.status_code == 403:
        raise GlmKbError("智谱鉴权失败：请检查『模型管理』里『智谱 AI·GLM』的 API Key。")
    # 2xx 且空 body / 204（如某些 DELETE/PUT）→ 当成功，返回 None，别误判失败（WB-151 M3）。
    if 200 <= r.status_code < 300 and not (r.content or b"").strip():
        return None
    try:
        body = r.json()
    except Exception as e:  # noqa: BLE001
        raise GlmKbError(f"GLM 知识库返回无法解析（HTTP {r.status_code}）：{r.text[:200]}") from e
    code = body.get("code")
    # 智谱 code 有时是字符串，统一按 int 比较。
    try:
        ok = int(code) == 200
    except (TypeError, ValueError):
        ok = False
    if not ok:
        raise GlmKbError(str(body.get("message") or f"GLM 知识库错误（code={code}）"))
    return body.get("data")


def _request(method: str, url: str, key: str, **kw: Any) -> Any:
    try:
        r = httpx.request(method, url, headers=_headers(key), timeout=_TIMEOUT, **kw)
    except httpx.HTTPError as e:
        raise GlmKbError(f"连接 GLM 知识库失败：{e}") from e
    return _unwrap(r)


# ── 知识库 CRUD ────────────────────────────────────────────────────────────

def create_kb(
    key: str,
    *,
    name: str,
    embedding_id: int = 11,
    description: str = "",
    contextual: int = 0,
    icon: str = "book",
    background: str = "blue",
) -> str:
    """建库 → 返回 knowledge_id。contextual=1 开启上下文增强。"""
    data = _request(
        "POST", f"{GLM_APP_BASE}/knowledge", key,
        json={
            "embedding_id": embedding_id,
            "name": name,
            "description": description,
            "contextual": contextual,
            "icon": icon,
            "background": background,
        },
    )
    kid = (data or {}).get("id")
    if not kid:
        raise GlmKbError("建库成功但未返回 knowledge_id。")
    return str(kid)


def list_kb(key: str, *, page: int = 1, size: int = 50) -> dict[str, Any]:
    """列库 → {list:[...], total}。"""
    return _request("GET", f"{GLM_APP_BASE}/knowledge", key,
                    params={"page": page, "size": size}) or {"list": [], "total": 0}


def get_kb(key: str, kb_id: str) -> dict[str, Any]:
    return _request("GET", f"{GLM_APP_BASE}/knowledge/{kb_id}", key) or {}


def update_kb(key: str, kb_id: str, **fields: Any) -> None:
    """编辑库（name/description/contextual/icon/background/embedding_id 任意子集）。"""
    body = {k: v for k, v in fields.items() if v is not None}
    _request("PUT", f"{GLM_APP_BASE}/knowledge/{kb_id}", key, json=body)


def delete_kb(key: str, kb_id: str) -> None:
    _request("DELETE", f"{GLM_APP_BASE}/knowledge/{kb_id}", key)


def capacity(key: str) -> dict[str, Any]:
    """账号知识库总用量 → {used:{word_num,length}, total:{word_num,length}}。"""
    return _request("GET", f"{GLM_APP_BASE}/knowledge/capacity", key) or {}


# ── 文档 ───────────────────────────────────────────────────────────────────

# 上传默认切片方式。实测：不传 knowledge_type（GLM「动态解析」）会让向量化报
# 「文档损坏」word_num=0（WB-141 真机验证），故默认用 5=自定义切片 + sentence_size，
# 中英文 txt/md 都能正常向量化并检索。
DEFAULT_KNOWLEDGE_TYPE = 5
DEFAULT_SENTENCE_SIZE = 300


def upload_file(
    key: str,
    kb_id: str,
    *,
    filename: str,
    content: bytes,
    content_type: str = "application/octet-stream",
    knowledge_type: Optional[int] = None,
    sentence_size: Optional[int] = None,
    parse_image: bool = False,
) -> dict[str, Any]:
    """传单文件到库 → {successInfos:[{documentId,fileName}], failedInfos:[...]}。
    knowledge_type 默认 5（自定义切片）——GLM 动态解析在部分账号会报「文档损坏」。"""
    kt = knowledge_type if knowledge_type is not None else DEFAULT_KNOWLEDGE_TYPE
    ss = sentence_size if sentence_size is not None else DEFAULT_SENTENCE_SIZE
    form: dict[str, Any] = {"knowledge_type": str(kt)}
    if kt == 5:
        form["sentence_size"] = str(ss)
    if parse_image:
        form["parse_image"] = "true"
    return _request(
        "POST", f"{GLM_APP_BASE}/document/upload_document/{kb_id}", key,
        files={"files": (filename, content, content_type)},
        data=form or None,
    ) or {}


def upload_url(
    key: str,
    kb_id: str,
    *,
    urls: list[str],
    knowledge_type: int = 5,
    sentence_size: int = 300,
) -> dict[str, Any]:
    """按 URL 抓取入库。upload_detail 每项需 url + knowledge_type。"""
    detail = [{"url": u, "knowledge_type": knowledge_type, "sentence_size": sentence_size}
              for u in urls if u.strip()]
    return _request(
        "POST", f"{GLM_APP_BASE}/document/upload_url", key,
        json={"knowledge_id": kb_id, "upload_detail": detail},
    ) or {}


def list_docs(key: str, kb_id: str, *, page: int = 1, size: int = 100, word: str = "") -> dict[str, Any]:
    """列文档 → {list:[{id,name,word_num,embedding_stat,failInfo?}], total}。
    embedding_stat：向量化状态（用于 UI 显示「向量化中/完成/失败」）。"""
    params: dict[str, Any] = {"knowledge_id": kb_id, "page": page, "size": size}
    if word:
        params["word"] = word
    return _request("GET", f"{GLM_APP_BASE}/document", key, params=params) or {"list": [], "total": 0}


def delete_doc(key: str, doc_id: str) -> None:
    _request("DELETE", f"{GLM_APP_BASE}/document/{doc_id}", key)


# ── 检索 ───────────────────────────────────────────────────────────────────

def retrieve(
    key: str,
    *,
    query: str,
    knowledge_ids: list[str],
    top_k: int = 8,
    top_n: Optional[int] = None,
    recall_method: str = "mixed",
    rerank_status: int = 1,
    rerank_model: str = "rerank",
    fractional_threshold: Optional[float] = None,
    document_ids: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """文本检索 → [{text, score, metadata:{doc_name, doc_id, ...}}]。"""
    body: dict[str, Any] = {
        "query": query[:1000],
        "knowledge_ids": knowledge_ids,
        "top_k": top_k,
        "recall_method": recall_method,
        "rerank_status": rerank_status,
        "rerank_model": rerank_model,
    }
    if top_n is not None:
        body["top_n"] = top_n
    if fractional_threshold is not None:
        body["fractional_threshold"] = fractional_threshold
    if document_ids:
        body["document_ids"] = document_ids
    data = _request("POST", f"{GLM_APP_BASE}/knowledge/retrieve", key, json=body)
    return data if isinstance(data, list) else []


def retrieve_multimodal(
    key: str,
    *,
    query: str = "",
    knowledge_ids: list[str],
    image_urls: Optional[list[str]] = None,
    top_k: int = 8,
    recall_method: str = "mixed",
    enable_rerank: bool = True,
    enable_rewrite: bool = False,
) -> dict[str, Any]:
    """全模态检索（文本 + 可选图像）→ {contents:[...], rewritten_query?}。走 /api/zrag。"""
    if not query.strip() and not (image_urls or []):
        raise GlmKbError("全模态检索需至少提供文本或图像。")
    body: dict[str, Any] = {
        "multimodal": True,
        "knows": [{"id": k} for k in knowledge_ids],
        "top_k": top_k,
        "recall_method": recall_method,
        "enable_rerank": enable_rerank,
        "enable_rewrite": enable_rewrite,
    }
    if query.strip():
        body["query"] = query
    if image_urls:
        body["multimodal_parts"] = [{"type": "image_url", "image_url": {"url": u}} for u in image_urls]
    return _request("POST", f"{GLM_ZRAG_BASE}/retrieval/retrieve", key, json=body) or {}
