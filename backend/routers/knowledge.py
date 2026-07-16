"""知识库路由（WB-173）—— 本地 backend 作自托管 WeKnora 的执行面。

真调 WeKnora（腾讯开源 RAG）REST `/api/v1`：建库 / 传档 / 文档管理 / 检索。
WeKnora 自己做解析/切片/嵌入/向量库/检索——本后端只当它的**客户端**。
API Key 只存后端（`settings.WEKNORA_API_KEY`，来自 backend/.env，铁律#4），**绝不回前端**；
未配置 → 400 可读提示，引导去 `docs/weknora-部署.md`。weknora 是同步客户端，统一经
`run_in_threadpool` 跑，不占事件循环（WB-002）。

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

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

MAX_UPLOAD = 50 * 1024 * 1024  # 50 MB/文件，与 files 路由一致


def _require() -> None:
    """未配置 WeKnora → 400 引导（key 只在后端 .env）。"""
    if not weknora.configured():
        raise HTTPException(
            400,
            "尚未接入知识库：请在 backend/.env 配置 WEKNORA_URL / WEKNORA_API_KEY"
            "（自托管 WeKnora，见 docs/weknora-部署.md）。",
        )


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


# ── 知识库 ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_kb(page: int = 1, size: int = 50) -> dict:
    _require()
    kbs = await _run(weknora.list_kb)
    return {"list": [_kb_out(k) for k in kbs], "total": len(kbs)}


class CreateKbBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    # 兼容旧前端/模板可能带的字段（WeKnora 侧不需要，忽略）。
    icon: str = "book"


@router.post("")
async def create_kb(body: CreateKbBody) -> dict:
    _require()
    emb = await _run(weknora.default_embedding_model_id)
    kb = await _run(
        weknora.create_kb,
        name=body.name, embedding_model_id=emb, description=body.description,
    )
    return {"id": kb.get("id")}


@router.get("/{kb_id}")
async def get_kb(kb_id: str) -> dict:
    _require()
    return _kb_out(await _run(weknora.get_kb, kb_id))


class UpdateKbBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


@router.patch("/{kb_id}")
async def update_kb(kb_id: str, body: UpdateKbBody) -> dict:
    _require()
    await _run(weknora.update_kb, kb_id, **body.model_dump(exclude_none=True))
    return {"ok": True}


@router.delete("/{kb_id}")
async def delete_kb(kb_id: str) -> dict:
    _require()
    await _run(weknora.delete_kb, kb_id)
    return {"ok": True}


# ── 文档 ───────────────────────────────────────────────────────────────────

@router.get("/{kb_id}/documents")
async def list_docs(kb_id: str, page: int = 1, size: int = 100, word: str = "") -> dict:
    _require()
    data = await _run(weknora.list_docs, kb_id, page=page, page_size=size)
    return {"list": [_doc_out(d) for d in data.get("list", [])], "total": data.get("total", 0)}


@router.post("/{kb_id}/documents")
async def upload_document(kb_id: str, request: Request, filename: str) -> dict:
    """传单文件。仿 files 路由：原始 body 流式（不引 python-multipart），文件名走 query。
    WeKnora 收到后异步解析（parse_status=pending），前端轮询到 completed。"""
    _require()
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
        weknora.upload_file, kb_id,
        filename=filename or "document", content=bytes(buf), content_type=content_type,
    )
    # 保持旧上传返回形状（前端不消费其字段，只判 HTTP 成功）。
    return {
        "successInfos": [{"documentId": doc.get("id"), "fileName": doc.get("file_name") or filename}],
        "failedInfos": [],
    }


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str) -> dict:
    _require()
    await _run(weknora.delete_doc, doc_id)
    return {"ok": True}


# ── 检索 ───────────────────────────────────────────────────────────────────

class RetrieveBody(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    knowledge_ids: list[str] = Field(min_length=1, max_length=20)
    top_k: int = 8


@router.post("/retrieve")
async def retrieve(body: RetrieveBody) -> dict:
    _require()
    data = await _run(
        weknora.search,
        query=body.query, knowledge_ids=body.knowledge_ids, top_k=body.top_k,
    )
    return {"data": data}
