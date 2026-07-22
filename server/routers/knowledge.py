"""Project-scoped central WeKnora gateway (WB-290).

The Server owns authorization and the tenant credential. Public KB ids are stable
Server ids; provider ids never act as authorization. Legacy WB-171 rows stay
``legacy_pending`` until an Admin/Owner explicitly migrates their stored bytes.
"""
from __future__ import annotations

import mimetypes
import shutil
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import db
import weknora
from auth import CurrentAccount
from config import settings
from models import Account, Role, can_manage, can_write

router = APIRouter(prefix="/api", tags=["knowledge"])

MAX_UPLOAD = 50 * 1024 * 1024
SUPPORTED_EXTS = {
    "txt", "doc", "docx", "pdf", "md", "markdown", "ppt", "pptx", "xls", "xlsx", "csv",
    "html", "htm", "png", "jpg", "jpeg", "gif", "bmp", "webp",
}


def _access(project_id: str, account: Account) -> Role:
    role = db.project_access_role(project_id, account.id)
    if role is None:
        raise HTTPException(404, "project not found")
    return role


def _require_write(project_id: str, account: Account) -> Role:
    role = _access(project_id, account)
    if not can_write(role):
        raise HTTPException(403, "Viewer is read-only")
    return role


def _require_manage(project_id: str, account: Account) -> Role:
    role = _access(project_id, account)
    if not can_manage(role):
        raise HTTPException(403, "requires Admin/Owner")
    return role


def _kb_or_404(project_id: str, kb_id: str) -> dict[str, Any]:
    kb = db.get_kb(kb_id)
    if not kb or kb["project_id"] != project_id:
        raise HTTPException(404, "knowledge base not found")
    return kb


def _provider_id(kb: dict[str, Any]) -> str:
    provider_id = str(kb.get("provider_id") or "")
    if kb.get("provider") != "weknora" or not provider_id or kb.get("provider_status") != "ready":
        detail = kb.get("provider_error") or "旧知识库尚未迁移到中央 WeKnora。"
        raise HTTPException(409, detail)
    return provider_id


def _weknora_error(exc: weknora.WeKnoraError) -> HTTPException:
    return HTTPException(502, str(exc))


def _remote_id(payload: Any) -> str:
    if isinstance(payload, dict):
        if payload.get("id"):
            return str(payload["id"])
        data = payload.get("data")
        if isinstance(data, dict) and data.get("id"):
            return str(data["id"])
        if isinstance(data, list) and data and isinstance(data[0], dict) and data[0].get("id"):
            return str(data[0]["id"])
    return ""


def _parse_status(row: dict[str, Any]) -> tuple[int, str]:
    raw = str(row.get("parse_status") or row.get("status") or "").lower()
    if raw in ("completed", "success", "ready", "done"):
        return 1, "completed"
    if raw in ("failed", "error"):
        return 2, "failed"
    return 0, raw or "processing"


def _present_doc(row: dict[str, Any], *, size: int = 0) -> dict[str, Any]:
    vector_status, parse_status = _parse_status(row)
    filename = str(
        row.get("file_name") or row.get("filename") or row.get("name")
        or row.get("title") or "document"
    )
    return {
        "id": str(row.get("id") or row.get("knowledge_id") or ""),
        "filename": filename,
        "size": int(row.get("file_size") or row.get("size") or size or 0),
        "doc_type": str(row.get("type") or (filename.rsplit(".", 1)[-1] if "." in filename else "")),
        "vector_status": vector_status,
        "parse_status": parse_status,
        "fail_msg": str(row.get("error_message") or row.get("fail_msg") or ""),
        "created_at": row.get("created_at"),
    }


def _present_legacy_doc(row: dict[str, Any]) -> dict[str, Any]:
    """Expose legacy document metadata without leaking server-local paths/provider ids."""
    filename = str(row.get("filename") or "document")
    return {
        "id": str(row.get("id") or ""),
        "filename": filename,
        "size": int(row.get("size") or 0),
        "doc_type": filename.rsplit(".", 1)[-1] if "." in filename else "",
        "vector_status": int(row.get("vector_status") or 0),
        "parse_status": "legacy_pending",
        "fail_msg": str(row.get("fail_msg") or ""),
        "created_at": row.get("created_at"),
    }


def _present_kb(kb: dict[str, Any], *, doc_count: Optional[int] = None) -> dict[str, Any]:
    return {
        "id": kb["id"],
        "name": kb["name"],
        "description": kb.get("description") or "",
        "icon": kb.get("icon") or "📚",
        "tags": kb.get("tags") or [],
        "provider": kb.get("provider") or "legacy",
        "provider_status": kb.get("provider_status") or "legacy_pending",
        "provider_error": kb.get("provider_error") or "",
        "doc_count": int(kb.get("doc_count") if doc_count is None else doc_count),
        "created_at": kb.get("created_at"),
        "updated_at": kb.get("updated_at"),
    }


class CreateKbBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)
    icon: str = Field(default="📚", max_length=8)
    tags: list[str] = Field(default_factory=list)
    chunk_size: int = Field(default=1000, ge=100, le=4000)
    chunk_overlap: int = Field(default=200, ge=0, le=1000)


class UpdateKbBody(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=1000)
    icon: Optional[str] = Field(default=None, max_length=8)
    tags: Optional[list[str]] = None


class SearchBody(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    knowledge_ids: list[str] = Field(default_factory=list, max_length=20)
    top_k: int = Field(default=8, ge=1, le=20)


class UrlImportBody(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


@router.get("/knowledge/config")
def knowledge_config(account: Account = CurrentAccount) -> dict[str, Any]:
    _ = account
    return weknora.public_config()


@router.post("/knowledge/config/test")
def test_knowledge_config(account: Account = CurrentAccount) -> dict[str, Any]:
    if not account.is_platform_admin:
        raise HTTPException(403, "requires platform admin")
    try:
        models = weknora.list_models()
    except weknora.WeKnoraError as exc:
        raise _weknora_error(exc) from exc
    return {"ok": True, "embedding_models": sum(
        1 for model in models if str(model.get("type", "")).lower() == "embedding"
    )}


@router.get("/projects/{project_id}/knowledge-bases")
def list_kbs(
    project_id: str, account: Account = CurrentAccount, include_counts: bool = True,
) -> dict[str, Any]:
    _access(project_id, account)
    items = []
    for kb in db.list_kbs(project_id):
        if include_counts and kb.get("provider") == "weknora" and kb.get("provider_status") == "ready":
            try:
                remote = weknora.list_docs(str(kb["provider_id"]), page_size=1)
                items.append(_present_kb(kb, doc_count=int(remote["total"])))
            except weknora.WeKnoraError as exc:
                item = _present_kb(kb)
                item["provider_status"] = "unavailable"
                item["provider_error"] = str(exc)
                items.append(item)
        else:
            items.append(_present_kb(kb))
    return {"items": items, "configured": weknora.configured()}


@router.post("/projects/{project_id}/knowledge-bases")
def create_kb(project_id: str, body: CreateKbBody, account: Account = CurrentAccount) -> dict[str, Any]:
    _require_manage(project_id, account)
    name = body.name.strip()
    try:
        remote = weknora.create_kb(
            name=name, description=body.description.strip(),
            chunk_size=body.chunk_size, chunk_overlap=body.chunk_overlap,
        )
    except weknora.WeKnoraError as exc:
        raise _weknora_error(exc) from exc
    provider_id = _remote_id(remote)
    if not provider_id:
        raise HTTPException(502, "WeKnora 建库响应缺少 id。")
    try:
        kb = db.create_kb(
            project_id=project_id, name=name, description=body.description.strip(),
            icon=body.icon or "📚", tags=[tag.strip() for tag in body.tags if tag.strip()],
            provider="weknora", provider_id=provider_id, provider_status="ready",
        )
        db.touch_project(project_id)
    except Exception:
        try:
            weknora.delete_kb(provider_id)
        except weknora.WeKnoraError:
            pass
        raise
    return _present_kb(kb, doc_count=0)


@router.get("/projects/{project_id}/knowledge-bases/{kb_id}")
def get_kb(project_id: str, kb_id: str, account: Account = CurrentAccount) -> dict[str, Any]:
    _access(project_id, account)
    return _present_kb(_kb_or_404(project_id, kb_id))


@router.patch("/projects/{project_id}/knowledge-bases/{kb_id}")
def update_kb(project_id: str, kb_id: str, body: UpdateKbBody, account: Account = CurrentAccount) -> dict[str, Any]:
    _require_manage(project_id, account)
    kb = _kb_or_404(project_id, kb_id)
    provider_id = _provider_id(kb)
    fields = body.model_dump(exclude_unset=True, exclude_none=True)
    remote_fields = {key: fields[key] for key in ("name", "description") if key in fields}
    try:
        if remote_fields:
            weknora.update_kb(provider_id, **remote_fields)
    except weknora.WeKnoraError as exc:
        raise _weknora_error(exc) from exc
    if "name" in fields:
        fields["name"] = fields["name"].strip()
    if "tags" in fields:
        fields["tags"] = [tag.strip() for tag in fields["tags"] if tag.strip()]
    updated = db.update_kb(kb_id, **fields)
    db.touch_project(project_id)
    return _present_kb(updated or kb)


@router.delete("/projects/{project_id}/knowledge-bases/{kb_id}")
def delete_kb(project_id: str, kb_id: str, account: Account = CurrentAccount) -> dict[str, Any]:
    _require_manage(project_id, account)
    kb = _kb_or_404(project_id, kb_id)
    provider_id = str(kb.get("provider_id") or "")
    if provider_id:
        try:
            weknora.delete_kb(provider_id)
        except weknora.WeKnoraError as exc:
            raise _weknora_error(exc) from exc
    paths = db.delete_kb(kb_id)
    for path in paths:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass
    shutil.rmtree(settings.STORAGE_DIR / "kb" / kb_id, ignore_errors=True)
    db.touch_project(project_id)
    return {"ok": True}


@router.post("/projects/{project_id}/knowledge-bases/{kb_id}/migrate")
def migrate_legacy_kb(project_id: str, kb_id: str, account: Account = CurrentAccount) -> dict[str, Any]:
    _require_manage(project_id, account)
    kb = _kb_or_404(project_id, kb_id)
    if kb.get("provider") == "weknora" and kb.get("provider_status") == "ready":
        return _present_kb(kb)
    db.update_kb(kb_id, provider_status="migrating", provider_error="")
    provider_id = ""
    try:
        remote = weknora.create_kb(name=kb["name"], description=kb.get("description") or "")
        provider_id = _remote_id(remote)
        if not provider_id:
            raise weknora.WeKnoraError("WeKnora 建库响应缺少 id。")
        for doc in db.list_kb_documents(kb_id):
            path = Path(doc.get("storage_path") or "")
            if not path.is_file():
                raise weknora.WeKnoraError(f"旧文档文件已丢失：{doc.get('filename') or doc['id']}")
            uploaded = weknora.upload_file(
                provider_id,
                filename=doc.get("filename") or path.name,
                content=path.read_bytes(),
                content_type=doc.get("content_type") or "application/octet-stream",
            )
            db.update_kb_document_provider(doc["id"], _remote_id(uploaded))
        kb = db.update_kb(
            kb_id, provider="weknora", provider_id=provider_id,
            provider_status="ready", provider_error="",
        ) or kb
        db.touch_project(project_id)
        return _present_kb(kb)
    except weknora.WeKnoraError as exc:
        if provider_id:
            try:
                weknora.delete_kb(provider_id)
            except weknora.WeKnoraError:
                pass
        db.update_kb(kb_id, provider_status="legacy_pending", provider_error=str(exc))
        raise _weknora_error(exc) from exc


@router.get("/projects/{project_id}/knowledge-bases/{kb_id}/documents")
def list_documents(project_id: str, kb_id: str, account: Account = CurrentAccount) -> dict[str, Any]:
    _access(project_id, account)
    kb = _kb_or_404(project_id, kb_id)
    if kb.get("provider_status") != "ready":
        return {"items": [_present_legacy_doc(doc) for doc in db.list_kb_documents(kb_id)]}
    try:
        remote = weknora.list_docs(_provider_id(kb))
    except weknora.WeKnoraError as exc:
        raise _weknora_error(exc) from exc
    return {"items": [_present_doc(row) for row in remote["items"]]}


@router.post("/projects/{project_id}/knowledge-bases/{kb_id}/documents")
async def upload_document(
    project_id: str, kb_id: str, request: Request, filename: str,
    account: Account = CurrentAccount,
) -> dict[str, Any]:
    _require_write(project_id, account)
    kb = _kb_or_404(project_id, kb_id)
    provider_id = _provider_id(kb)
    name = (filename or "").strip() or "document"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext and ext not in SUPPORTED_EXTS:
        raise HTTPException(400, f"不支持的文件类型：.{ext}")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_UPLOAD:
        raise HTTPException(413, "单文件超过 50MB 上限。")
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > MAX_UPLOAD:
            raise HTTPException(413, "单文件超过 50MB 上限。")
    if not content:
        raise HTTPException(400, "空文件。")
    try:
        remote = weknora.upload_file(
            provider_id, filename=name, content=bytes(content),
            content_type=mimetypes.guess_type(name)[0] or "application/octet-stream",
        )
    except weknora.WeKnoraError as exc:
        raise _weknora_error(exc) from exc
    return _present_doc(remote, size=len(content))


@router.post("/projects/{project_id}/knowledge-bases/{kb_id}/documents/url")
def import_url(
    project_id: str, kb_id: str, body: UrlImportBody, account: Account = CurrentAccount,
) -> dict[str, Any]:
    _require_write(project_id, account)
    kb = _kb_or_404(project_id, kb_id)
    try:
        remote = weknora.create_from_url(_provider_id(kb), url=body.url)
    except weknora.WeKnoraError as exc:
        raise _weknora_error(exc) from exc
    return _present_doc(remote)


@router.get("/projects/{project_id}/knowledge-bases/{kb_id}/documents/{doc_id}/download")
def download_legacy_document(
    project_id: str, kb_id: str, doc_id: str, account: Account = CurrentAccount,
):
    _access(project_id, account)
    kb = _kb_or_404(project_id, kb_id)
    if kb.get("provider_status") == "ready":
        raise HTTPException(409, "中央 WeKnora 文档不在 Server 本地保存。")
    doc = db.get_kb_document(doc_id)
    if not doc or doc["kb_id"] != kb_id or doc["project_id"] != project_id:
        raise HTTPException(404, "document not found")
    path = Path(doc.get("storage_path") or "")
    if not path.is_file():
        raise HTTPException(404, "文件已丢失。")
    return FileResponse(str(path), filename=doc.get("filename") or "document",
                        media_type=doc.get("content_type") or "application/octet-stream")


@router.delete("/projects/{project_id}/knowledge-bases/{kb_id}/documents/{doc_id}")
def delete_document(
    project_id: str, kb_id: str, doc_id: str, account: Account = CurrentAccount,
) -> dict[str, Any]:
    _require_write(project_id, account)
    kb = _kb_or_404(project_id, kb_id)
    if kb.get("provider_status") != "ready":
        doc = db.get_kb_document(doc_id)
        if not doc or doc["kb_id"] != kb_id or doc["project_id"] != project_id:
            raise HTTPException(404, "document not found")
        path = db.delete_kb_document(doc_id)
        if path:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass
        return {"ok": True}
    try:
        remote = weknora.list_docs(_provider_id(kb), page_size=500)
        if doc_id not in {str(row.get("id") or row.get("knowledge_id") or "") for row in remote["items"]}:
            raise HTTPException(404, "document not found")
        weknora.delete_doc(doc_id)
    except weknora.WeKnoraError as exc:
        raise _weknora_error(exc) from exc
    return {"ok": True}


@router.post("/projects/{project_id}/knowledge-search")
def search_project_knowledge(
    project_id: str, body: SearchBody, account: Account = CurrentAccount,
) -> dict[str, Any]:
    _access(project_id, account)
    requested = list(dict.fromkeys(body.knowledge_ids))
    if not requested:
        return {"hits": []}
    provider_ids = []
    for kb_id in requested:
        kb = _kb_or_404(project_id, kb_id)
        provider_ids.append(_provider_id(kb))
    try:
        hits = weknora.search(query=body.query, provider_ids=provider_ids, top_k=body.top_k)
    except weknora.WeKnoraError as exc:
        raise _weknora_error(exc) from exc
    return {"hits": hits}
