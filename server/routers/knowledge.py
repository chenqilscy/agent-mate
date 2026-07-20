"""真·知识库 + 文档（WB-171）—— 项目级团队知识库的 Server 权威源。

Console 只**管理**知识库及其文档（元数据 + 文档字节落盘），**绝不算向量**：文档 `vector_status`
恒从 0（未向量化）起，Server 永不置 1——向量化是执行面（App/本地 backend）将来的事：**只调 GLM 的
嵌入模型接口（/embeddings）自算并自存向量，不使用 GLM 的知识库/RAG 功能**（用户 2026-07-14 定向），
届时回写状态（对齐 WB-091「不假成功」）。字节存 `settings.STORAGE_DIR/kb/<kb_id>/<doc_id>`。

access-gated（照 work_items）：owner OR 成员可读，Member+ 可写，Viewer 只读。
"""
from __future__ import annotations

import mimetypes
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import db
from auth import CurrentAccount
from config import settings
from models import Account, Role, can_write

router = APIRouter(prefix="/api", tags=["knowledge"])

MAX_UPLOAD = 50 * 1024 * 1024  # 50 MB/文件（与 backend files/knowledge 路由一致）
# GLM 支持的文档后缀（无 url——Server 只收真文件字节）。
SUPPORTED_EXTS = {"txt", "doc", "docx", "pdf", "md", "ppt", "pptx", "xls", "xlsx", "csv"}
_EMBEDDINGS = {3, 11, 12}          # 3=Embedding-2 · 11=Embedding-3 · 12=Embedding-3-pro
_KNOWLEDGE_TYPES = {1, 2, 3, 5, 6, 7}  # GLM 切片方式；仅 5=自定义切片 用 sentence_size


def _access(project_id: str, account: Account) -> Role:
    role = db.project_access_role(project_id, account.id)
    if role is None:
        raise HTTPException(404, "project not found")
    return role


def _require_write(project_id: str, account: Account) -> None:
    if not can_write(_access(project_id, account)):
        raise HTTPException(403, "Viewer is read-only")


def _kb_or_404(project_id: str, kb_id: str) -> dict:
    kb = db.get_kb(kb_id)
    if not kb or kb["project_id"] != project_id:
        raise HTTPException(404, "knowledge base not found")
    return kb


def _doc_or_404(project_id: str, kb_id: str, doc_id: str) -> dict:
    doc = db.get_kb_document(doc_id)
    if not doc or doc["kb_id"] != kb_id or doc["project_id"] != project_id:
        raise HTTPException(404, "document not found")
    return doc


def _kb_dir(kb_id: str) -> Path:
    return settings.STORAGE_DIR / "kb" / kb_id


def _clamp_ss(v: int) -> int:
    return max(20, min(2000, int(v or 300)))


# ── 知识库 CRUD ──────────────────────────────────────────────────────────────

class CreateKbBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)
    icon: str = Field(default="📚", max_length=8)
    embedding_id: int = 11
    knowledge_type: int = 5
    sentence_size: int = 300
    contextual: int = 0
    tags: list[str] = Field(default_factory=list)


class UpdateKbBody(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = Field(default=None, max_length=1000)
    icon: Optional[str] = Field(default=None, max_length=8)
    embedding_id: Optional[int] = None
    knowledge_type: Optional[int] = None
    sentence_size: Optional[int] = None
    contextual: Optional[int] = None
    tags: Optional[list[str]] = None
    sort: Optional[int] = None


@router.get("/projects/{project_id}/knowledge-bases")
def list_kbs(project_id: str, account: Account = CurrentAccount) -> dict:
    _access(project_id, account)
    return {"items": db.list_kbs(project_id)}


@router.post("/projects/{project_id}/knowledge-bases")
def create_kb(project_id: str, body: CreateKbBody, account: Account = CurrentAccount) -> dict:
    _require_write(project_id, account)
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "名称必填")
    eid = body.embedding_id if body.embedding_id in _EMBEDDINGS else 11
    kt = body.knowledge_type if body.knowledge_type in _KNOWLEDGE_TYPES else 5
    kb = db.create_kb(
        project_id=project_id, name=name, description=body.description.strip(),
        icon=(body.icon or "📚"), embedding_id=eid, knowledge_type=kt,
        sentence_size=_clamp_ss(body.sentence_size), contextual=body.contextual,
        tags=[t.strip() for t in body.tags if t.strip()],
    )
    return kb


@router.get("/projects/{project_id}/knowledge-bases/{kb_id}")
def get_kb(project_id: str, kb_id: str, account: Account = CurrentAccount) -> dict:
    _access(project_id, account)
    return _kb_or_404(project_id, kb_id)


@router.patch("/projects/{project_id}/knowledge-bases/{kb_id}")
def update_kb(project_id: str, kb_id: str, body: UpdateKbBody, account: Account = CurrentAccount) -> dict:
    _require_write(project_id, account)
    kb = _kb_or_404(project_id, kb_id)
    fields = body.model_dump(exclude_unset=True, exclude_none=True)
    # 需求#1 的锁：库里已有文档时，向量维度（= embedding 模型）不可更改。
    if "embedding_id" in fields and int(fields["embedding_id"]) != int(kb["embedding_id"]):
        if db.count_kb_documents(kb_id) > 0:
            raise HTTPException(400, "知识库已有文档，向量维度不可更改。")
        if fields["embedding_id"] not in _EMBEDDINGS:
            fields.pop("embedding_id")
    if "knowledge_type" in fields and fields["knowledge_type"] not in _KNOWLEDGE_TYPES:
        fields.pop("knowledge_type")
    if "sentence_size" in fields:
        fields["sentence_size"] = _clamp_ss(fields["sentence_size"])
    if "name" in fields:
        fields["name"] = (fields["name"] or "").strip() or kb["name"]
    if "tags" in fields and isinstance(fields["tags"], list):
        fields["tags"] = [t.strip() for t in fields["tags"] if t.strip()]
    updated = db.update_kb(kb_id, **fields)
    if not updated:
        raise HTTPException(404, "knowledge base not found")
    return updated


@router.delete("/projects/{project_id}/knowledge-bases/{kb_id}")
def delete_kb(project_id: str, kb_id: str, account: Account = CurrentAccount) -> dict:
    _require_write(project_id, account)
    _kb_or_404(project_id, kb_id)
    db.delete_kb(kb_id)  # 级联删文档行；返回的 storage_path 忽略，整目录一并清。
    shutil.rmtree(_kb_dir(kb_id), ignore_errors=True)
    return {"ok": True}


# ── 文档 ─────────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/knowledge-bases/{kb_id}/documents")
def list_documents(project_id: str, kb_id: str, account: Account = CurrentAccount) -> dict:
    _access(project_id, account)
    _kb_or_404(project_id, kb_id)
    return {"items": db.list_kb_documents(kb_id)}


@router.post("/projects/{project_id}/knowledge-bases/{kb_id}/documents")
async def upload_document(
    project_id: str, kb_id: str, request: Request, filename: str,
    account: Account = CurrentAccount,
) -> dict:
    """传单文件。仿 backend/routers/knowledge.py：原始 body 流式（不引 python-multipart），文件名走 query。
    Server 只落盘字节 + 记元数据（vector_status=0），绝不算向量。"""
    _require_write(project_id, account)
    _kb_or_404(project_id, kb_id)
    fname = (filename or "").strip() or "document"
    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
    if ext and ext not in SUPPORTED_EXTS:
        raise HTTPException(400, f"不支持的文件类型：.{ext}（支持 {', '.join(sorted(SUPPORTED_EXTS))}）")
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
    did = db.new_uuid()
    kb_dir = _kb_dir(kb_id)
    kb_dir.mkdir(parents=True, exist_ok=True)
    path = kb_dir / did
    path.write_bytes(bytes(buf))
    content_type = mimetypes.guess_type(fname)[0] or "application/octet-stream"
    return db.create_kb_document(
        kb_id=kb_id, project_id=project_id, filename=fname, size=len(buf),
        content_type=content_type, doc_type=ext, storage_path=str(path), doc_id=did,
    )


@router.get("/projects/{project_id}/knowledge-bases/{kb_id}/documents/{doc_id}/download")
def download_document(project_id: str, kb_id: str, doc_id: str, account: Account = CurrentAccount):
    _access(project_id, account)
    doc = _doc_or_404(project_id, kb_id, doc_id)
    p = Path(doc["storage_path"] or "")
    if not p.is_file():
        raise HTTPException(404, "文件已丢失。")
    return FileResponse(str(p), filename=doc["filename"] or "document",
                        media_type=doc["content_type"] or "application/octet-stream")


@router.delete("/projects/{project_id}/knowledge-bases/{kb_id}/documents/{doc_id}")
def delete_document(project_id: str, kb_id: str, doc_id: str, account: Account = CurrentAccount) -> dict:
    _require_write(project_id, account)
    _doc_or_404(project_id, kb_id, doc_id)
    path = db.delete_kb_document(doc_id)
    if path:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass
    return {"ok": True}
