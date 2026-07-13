"""知识库路由（WB-142）—— 本地 backend 作 GLM 知识库的执行面。

真调 GLM（智谱）知识库 API：建库 / 传档 / 文档管理 / 检索 / 全模态 / 用量。
key 只在本地：用 `db.get_provider_key(owner_id, "zhipu")`，**绝不回传前端**（铁律#4）；
没配 key → 400 可读提示，引导去「模型管理」配置。glm_kb 是同步客户端，统一经
`run_in_threadpool` 跑，不占事件循环（WB-002）。
"""
from __future__ import annotations

from typing import Any, Optional

import mimetypes

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from agent import glm_kb
from agent.glm_kb import GlmKbError
from auth.deps import current_user
from storage import db

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

_PROVIDER = "zhipu"
MAX_UPLOAD = 50 * 1024 * 1024  # 50 MB/文件，与 files 路由一致


def _key() -> str:
    """当前 owner 的智谱 key；没配则 400 引导去配置。"""
    key = db.get_provider_key(current_user().id, _PROVIDER)
    if not key:
        raise HTTPException(400, "请先在「模型管理」给「智谱 AI·GLM」配置 API Key，才能使用知识库。")
    return key


async def _run(fn, *args, **kw):
    """在线程池里跑同步 glm_kb 调用，并把 GlmKbError 转成可读的 4xx/5xx。"""
    try:
        return await run_in_threadpool(fn, *args, **kw)
    except GlmKbError as e:
        raise HTTPException(502, str(e)) from e


# ── 知识库 ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_kb(page: int = 1, size: int = 50) -> dict:
    return await _run(glm_kb.list_kb, _key(), page=page, size=size)


class CreateKbBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    embedding_id: int = 11
    description: str = Field(default="", max_length=500)
    contextual: int = 0  # 1 = 开启上下文增强
    icon: str = "book"
    background: str = "blue"


@router.post("")
async def create_kb(body: CreateKbBody) -> dict:
    kid = await _run(
        glm_kb.create_kb, _key(),
        name=body.name, embedding_id=body.embedding_id, description=body.description,
        contextual=body.contextual, icon=body.icon, background=body.background,
    )
    return {"id": kid}


@router.get("/capacity")
async def capacity() -> dict:
    return await _run(glm_kb.capacity, _key())


@router.get("/{kb_id}")
async def get_kb(kb_id: str) -> dict:
    return await _run(glm_kb.get_kb, _key(), kb_id)


class UpdateKbBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    contextual: Optional[int] = None
    icon: Optional[str] = None
    background: Optional[str] = None
    embedding_id: Optional[int] = None


@router.patch("/{kb_id}")
async def update_kb(kb_id: str, body: UpdateKbBody) -> dict:
    await _run(glm_kb.update_kb, _key(), kb_id, **body.model_dump(exclude_none=True))
    return {"ok": True}


@router.delete("/{kb_id}")
async def delete_kb(kb_id: str) -> dict:
    await _run(glm_kb.delete_kb, _key(), kb_id)
    return {"ok": True}


# ── 文档 ───────────────────────────────────────────────────────────────────

@router.get("/{kb_id}/documents")
async def list_docs(kb_id: str, page: int = 1, size: int = 100, word: str = "") -> dict:
    return await _run(glm_kb.list_docs, _key(), kb_id, page=page, size=size, word=word)


@router.post("/{kb_id}/documents")
async def upload_document(
    kb_id: str,
    request: Request,
    filename: str,
    knowledge_type: Optional[int] = None,
    sentence_size: Optional[int] = None,
    parse_image: bool = False,
) -> dict:
    """传单文件。仿 files 路由：原始 body 流式（不引 python-multipart），文件名走 query。"""
    # 先查 key（WB-151 M4）：没配 key 时立刻 400，别白缓冲最多 50MB body 进内存。
    key = _key()
    # 扩展名校验（WB-151 M2）：用「有没有点」判断，rsplit 对无点文件名不会给空串。
    ext = filename.rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""
    if ext and ext not in glm_kb.SUPPORTED_EXTS:
        raise HTTPException(400, f"不支持的文件类型：.{ext}（支持 {', '.join(sorted(glm_kb.SUPPORTED_EXTS))}）")
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
    return await _run(
        glm_kb.upload_file, key, kb_id,
        filename=filename or "document", content=bytes(buf), content_type=content_type,
        knowledge_type=knowledge_type, sentence_size=sentence_size, parse_image=parse_image,
    )


class UploadUrlBody(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=20)
    knowledge_type: int = 5
    sentence_size: int = 300


@router.post("/{kb_id}/documents/url")
async def upload_document_url(kb_id: str, body: UploadUrlBody) -> dict:
    return await _run(
        glm_kb.upload_url, _key(), kb_id,
        urls=body.urls, knowledge_type=body.knowledge_type, sentence_size=body.sentence_size,
    )


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str) -> dict:
    await _run(glm_kb.delete_doc, _key(), doc_id)
    return {"ok": True}


# ── 检索 ───────────────────────────────────────────────────────────────────

class RetrieveBody(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    knowledge_ids: list[str] = Field(min_length=1, max_length=20)
    top_k: int = 8
    recall_method: str = "mixed"
    rerank_status: int = 1
    rerank_model: str = "rerank"
    fractional_threshold: Optional[float] = None
    document_ids: Optional[list[str]] = None


@router.post("/retrieve")
async def retrieve(body: RetrieveBody) -> dict:
    data = await _run(
        glm_kb.retrieve, _key(),
        query=body.query, knowledge_ids=body.knowledge_ids, top_k=body.top_k,
        recall_method=body.recall_method, rerank_status=body.rerank_status,
        rerank_model=body.rerank_model, fractional_threshold=body.fractional_threshold,
        document_ids=body.document_ids,
    )
    return {"data": data}


class RetrieveMmBody(BaseModel):
    query: str = Field(default="", max_length=1000)
    knowledge_ids: list[str] = Field(min_length=1, max_length=20)
    image_urls: Optional[list[str]] = None
    top_k: int = 8
    enable_rerank: bool = True
    enable_rewrite: bool = False


@router.post("/retrieve/multimodal")
async def retrieve_multimodal(body: RetrieveMmBody) -> dict:
    data = await _run(
        glm_kb.retrieve_multimodal, _key(),
        query=body.query, knowledge_ids=body.knowledge_ids, image_urls=body.image_urls,
        top_k=body.top_k, enable_rerank=body.enable_rerank, enable_rewrite=body.enable_rewrite,
    )
    return {"data": data}
