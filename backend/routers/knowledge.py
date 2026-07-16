"""知识库路由（WB-173）—— 本地 backend 作自托管 WeKnora 的执行面。

真调 WeKnora（腾讯开源 RAG）REST `/api/v1`：建库 / 传档 / 文档管理 / 检索 / 连接配置。
WeKnora 自己做解析/切片/嵌入/向量库/检索——本后端只当它的**客户端**。
weknora 是同步客户端，统一经 `run_in_threadpool` 跑，不占事件循环（WB-002）。

连接配置按 owner（WB-188）：用户在 UI 表单里填 → 存本机 DB（key 在 provider_keys 表），
没填过则回退 backend/.env 的 `WEKNORA_*`。API Key 只存后端、**绝不回前端**（铁律#4）——
`GET /config` 只给 `has_key` 布尔（同厂商 Key 的 `list_provider_keys` 脱敏做法）。
未配置 → 400 可读提示，引导去表单。

响应形状与旧 GLM 版保持一致，前端（KnowledgeView/store）几乎零改：
- 知识库 → {id, name, description, icon, document_size}
- 文档 → {id, name, embedding_stat(0 处理中/1 成功/2 失败), failInfo}
  （WeKnora `parse_status`: pending/processing/… → 0 · completed → 1 · failed → 2）
"""
from __future__ import annotations

from typing import Any, Optional

import mimetypes

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from agent import weknora
from agent.weknora import WeKnoraError
from auth.deps import current_user
from storage import db

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

MAX_UPLOAD = 50 * 1024 * 1024  # 50 MB/文件，与 files 路由一致


def _owner() -> str:
    """当前请求的 owner —— 连接配置/知识库都按他解析（WB-188）。"""
    return current_user().id


def _require() -> str:
    """未接入 → 400 引导去 UI 表单；已接入 → 返回 owner id。"""
    owner = _owner()
    if not weknora.configured(owner):
        raise HTTPException(400, weknora.NOT_CONFIGURED)
    return owner


async def _run(fn, *args, **kw):
    """在线程池里跑同步 weknora 调用，并把 WeKnoraError 转成可读的 502。"""
    try:
        return await run_in_threadpool(fn, *args, **kw)
    except WeKnoraError as e:
        raise HTTPException(502, str(e)) from e


def _kb_out(kb: dict) -> dict:
    """WeKnora 知识库 → 前端 KnowledgeBase 形状。WeKnora 无图标概念，前端统一给书本图标。"""
    return {
        "id": kb.get("id"),
        "name": kb.get("name") or "",
        "description": kb.get("description") or "",
        "icon": "book",
        "document_size": kb.get("knowledge_count") or 0,
    }


def _doc_out(d: dict) -> dict:
    """WeKnora 文档 → 前端 KbDocument 形状。parse_status → embedding_stat（前端 4s 轮询天然复用）。"""
    ps = str(d.get("parse_status") or "").lower()
    stat = 1 if ps == "completed" else (2 if ps == "failed" else 0)
    out: dict[str, Any] = {
        "id": d.get("id"),
        "name": d.get("file_name") or d.get("title") or "未命名文档",
        "embedding_stat": stat,
    }
    if stat == 2 and d.get("error_message"):
        out["failInfo"] = {"embedding_msg": str(d["error_message"])}
    return out


# ── 连接配置（WB-188）───────────────────────────────────────────────────────
#
# 表单取代「改 .env + 重启」。key 只写不回读：GET 只给 has_key（用户拍板的语义，
# 同厂商 Key 的 list_provider_keys 脱敏做法）。

@router.get("/config")
def get_config() -> dict:
    """本 owner 生效的连接配置。**不含 api_key** —— 只给 has_key 布尔。
    source 标明每个字段来自 UI 表单（db）还是 backend/.env（env），供前端如实提示。"""
    c = weknora.conf(_owner())
    return {
        "configured": bool(c.api_key),
        "url": c.url,
        "has_key": bool(c.api_key),
        "embedding_model_id": c.embedding_model_id,
        "key_source": c.key_source,
        "url_source": c.url_source,
    }


class ConfigBody(BaseModel):
    """每个字段：不传 = 不改；'' = 清除（回退 .env/默认）；非空 = 覆盖。"""
    url: Optional[str] = Field(default=None, max_length=500)
    api_key: Optional[str] = Field(default=None, max_length=500)
    embedding_model_id: Optional[str] = Field(default=None, max_length=200)


@router.put("/config")
def put_config(body: ConfigBody) -> dict:
    fields = body.model_dump(exclude_unset=True)  # 未传的键不进 DB 写入（区分「不改」与「清空」）
    if not fields:
        raise HTTPException(400, "没有要保存的配置项。")
    db.set_weknora_conf(_owner(), **fields)
    return get_config()


@router.post("/config/test")
async def test_config() -> dict:
    """真打一次 WeKnora（列库）验证地址与 Key。成功失败都 200：错误进 error 字段由前端原样提示
    （照 models.py 的 fetch_provider_models 约定，连不通不是本接口的 5xx）。"""
    owner = _owner()
    c = weknora.conf(owner)
    if not c.api_key:
        return {"ok": False, "error": weknora.NOT_CONFIGURED}
    try:
        kbs = await run_in_threadpool(weknora.list_kb, owner)
    except WeKnoraError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "url": c.url, "kb_count": len(kbs)}


# ── 知识库 ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_kb(page: int = 1, size: int = 50) -> dict:
    owner = _require()
    kbs = await _run(weknora.list_kb, owner)
    return {"list": [_kb_out(k) for k in kbs], "total": len(kbs)}


class CreateKbBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    # 兼容旧前端/模板可能带的字段（WeKnora 侧不需要，忽略）。
    icon: str = "book"


@router.post("")
async def create_kb(body: CreateKbBody) -> dict:
    owner = _require()
    emb = await _run(weknora.default_embedding_model_id, owner)
    kb = await _run(
        weknora.create_kb, owner,
        name=body.name, embedding_model_id=emb, description=body.description,
    )
    return {"id": kb.get("id")}


@router.get("/{kb_id}")
async def get_kb(kb_id: str) -> dict:
    owner = _require()
    return _kb_out(await _run(weknora.get_kb, owner, kb_id))


class UpdateKbBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


@router.patch("/{kb_id}")
async def update_kb(kb_id: str, body: UpdateKbBody) -> dict:
    owner = _require()
    await _run(weknora.update_kb, owner, kb_id, **body.model_dump(exclude_none=True))
    return {"ok": True}


@router.delete("/{kb_id}")
async def delete_kb(kb_id: str) -> dict:
    owner = _require()
    await _run(weknora.delete_kb, owner, kb_id)
    return {"ok": True}


# ── 文档 ───────────────────────────────────────────────────────────────────

@router.get("/{kb_id}/documents")
async def list_docs(kb_id: str, page: int = 1, size: int = 100, word: str = "") -> dict:
    owner = _require()
    data = await _run(weknora.list_docs, owner, kb_id, page=page, page_size=size)
    return {"list": [_doc_out(d) for d in data.get("list", [])], "total": data.get("total", 0)}


@router.post("/{kb_id}/documents")
async def upload_document(kb_id: str, request: Request, filename: str) -> dict:
    """传单文件。仿 files 路由：原始 body 流式（不引 python-multipart），文件名走 query。
    WeKnora 收到后异步解析（parse_status=pending），前端轮询到 completed。"""
    owner = _require()
    # 扩展名软校验（未知放行，交 WeKnora 判）。rsplit 对无点文件名不会给空串。
    ext = filename.rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""
    if ext and ext not in weknora.SUPPORTED_EXTS:
        raise HTTPException(400, f"不支持的文件类型：.{ext}（支持 {', '.join(sorted(weknora.SUPPORTED_EXTS))}）")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_UPLOAD:
        raise HTTPException(413, "单文件超过 50MB 上限。")
    buf = bytearray()
    async for chunk in request.stream():
        buf.extend(chunk)
        if len(buf) > MAX_UPLOAD:
            raise HTTPException(413, "单文件超过 50MB 上限。")
    if not buf:
        raise HTTPException(400, "空文件。")
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    doc = await _run(
        weknora.upload_file, owner, kb_id,
        filename=filename or "document", content=bytes(buf), content_type=content_type,
    )
    # 保持旧上传返回形状（前端不消费其字段，只判 HTTP 成功）。
    return {
        "successInfos": [{"documentId": doc.get("id"), "fileName": doc.get("file_name") or filename}],
        "failedInfos": [],
    }


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str) -> dict:
    owner = _require()
    await _run(weknora.delete_doc, owner, doc_id)
    return {"ok": True}


# ── 检索 ───────────────────────────────────────────────────────────────────

class RetrieveBody(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    knowledge_ids: list[str] = Field(min_length=1, max_length=20)
    top_k: int = 8


@router.post("/retrieve")
async def retrieve(body: RetrieveBody) -> dict:
    owner = _require()
    data = await _run(
        weknora.search, owner,
        query=body.query, knowledge_ids=body.knowledge_ids, top_k=body.top_k,
    )
    return {"data": data}
