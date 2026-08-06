"""Local-only project idea inbox (WB-422).

Ideas are private App data. They never sync to AgentMate Server; only an explicit
settlement can promote a confirmed snapshot into an existing collaborative work
item/decision or local curated project memory.
"""
from __future__ import annotations

import hashlib
import threading

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from agent import workspace_memory
from auth.deps import current_user
from routers import governance, work_items
from storage import db
from storage.models import Role

router = APIRouter(prefix="/api/ideas", tags=["ideas"])

STATUSES = {"inbox", "active", "settled", "archived"}
RELATIONS = {"related", "derived", "duplicate"}
SETTLEMENTS = {"work_item", "decision", "memory"}
_settle_lock = threading.Lock()


class CreateBody(BaseModel):
    title: str = Field(default="", max_length=200)
    content: str = Field(min_length=1, max_length=20_000)
    project_id: str | None = None
    tags: list[str] = []
    source_type: str = Field(default="manual", max_length=40)
    source_session_id: str | None = Field(default=None, max_length=100)
    source_message_id: str | None = Field(default=None, max_length=100)


class UpdateBody(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    content: str | None = Field(default=None, max_length=20_000)
    project_id: str | None = None
    status: str | None = None
    tags: list[str] | None = None
    processing_session_id: str | None = Field(default=None, max_length=100)


class RelationBody(BaseModel):
    target_idea_id: str
    relation: str


class SettleBody(BaseModel):
    kind: str
    memory_base_sha256: str = Field(default="", max_length=64)


def _clean_tags(values: list[str] | None) -> list[str]:
    result: list[str] = []
    for raw in (values or [])[:20]:
        value = " ".join(str(raw).split())[:40]
        if value and value not in result:
            result.append(value)
    return result


def _project_role(project_id: str, *, write: bool = False) -> Role:
    role = db.project_access_role(project_id, current_user().id)
    if role is None:
        raise HTTPException(404, "项目不存在或无权访问")
    if write and role == Role.VIEWER:
        raise HTTPException(403, "Viewer 只能查看项目想法")
    return role


def _require_idea(idea_id: str, *, write: bool = False) -> dict:
    idea = db.get_idea(idea_id)
    user = current_user()
    if not idea or idea["owner_id"] != user.id:
        raise HTTPException(404, "想法不存在")
    if idea.get("project_id"):
        _project_role(idea["project_id"], write=write)
    return idea


def _view(idea: dict) -> dict:
    role = db.project_access_role(idea["project_id"], current_user().id) if idea.get("project_id") else None
    return {
        **idea,
        "can_write": not idea.get("project_id") or role not in {None, Role.VIEWER},
    }


def _detail(idea: dict) -> dict:
    return {
        **_view(idea),
        "relations": [
            {**relation, "related": _view(relation["related"])}
            for relation in db.list_idea_relations(idea["id"])
        ],
    }


def _title(title: str, content: str) -> str:
    value = " ".join((title or "").split())
    if not value:
        value = " ".join(content.splitlines()[0].split()) if content.splitlines() else ""
    return (value or "未命名想法")[:200]


def _source(body: CreateBody) -> tuple[str, str | None, str | None, str]:
    session_id = body.source_session_id or None
    message_id = body.source_message_id or None
    content = body.content.strip()
    if message_id:
        message = db.get_message(message_id)
        if not message:
            raise HTTPException(404, "来源消息不存在")
        session = db.get_session_for(message.session_id, current_user().id)
        if not session:
            raise HTTPException(404, "来源会话不存在或无权访问")
        if session_id and session_id != message.session_id:
            raise HTTPException(400, "来源消息不属于指定会话")
        return "message", session.id, message.id, message.content.strip()
    if session_id and not db.get_session_for(session_id, current_user().id):
        raise HTTPException(404, "来源会话不存在或无权访问")
    return body.source_type or "manual", session_id, None, content


@router.get("")
def list_ideas(project_id: str | None = None, status: str | None = None, q: str = "") -> dict:
    user = current_user()
    if project_id:
        _project_role(project_id)
    needle = q.strip().casefold()
    items = []
    for idea in db.list_ideas(user.id):
        if idea.get("project_id") and db.project_access_role(idea["project_id"], user.id) is None:
            continue
        if project_id is not None and idea.get("project_id") != project_id:
            continue
        if status in STATUSES and idea["status"] != status:
            continue
        haystack = f"{idea['title']} {idea['content']} {idea.get('processed_content') or ''} {' '.join(idea['tags'])}".casefold()
        if needle and needle not in haystack:
            continue
        items.append(_view(idea))
    return {"ideas": items}


@router.post("")
def create_idea(body: CreateBody) -> dict:
    user = current_user()
    if body.project_id:
        _project_role(body.project_id, write=True)
    source_type, session_id, message_id, content = _source(body)
    if not content:
        raise HTTPException(400, "想法内容不能为空")
    idea, created = db.create_idea(
        owner_id=user.id, project_id=body.project_id,
        title=_title(body.title, content), content=content,
        tags=_clean_tags(body.tags), source_type=source_type,
        source_session_id=session_id, source_message_id=message_id,
    )
    return {"idea": _view(idea), "created": created}


@router.get("/{idea_id}")
def get_idea(idea_id: str) -> dict:
    return _detail(_require_idea(idea_id))


@router.patch("/{idea_id}")
def update_idea(idea_id: str, body: UpdateBody) -> dict:
    idea = _require_idea(idea_id, write=True)
    fields = body.model_fields_set
    changes: dict = {}
    if "title" in fields:
        changes["title"] = _title(body.title or "", idea["content"])
    if "content" in fields:
        content = (body.content or "").strip()
        if not content:
            raise HTTPException(400, "想法内容不能为空")
        changes["content"] = content
    if "tags" in fields:
        changes["tags"] = _clean_tags(body.tags)
    if "project_id" in fields:
        if body.project_id:
            _project_role(body.project_id, write=True)
        if body.project_id != idea.get("project_id"):
            db.clear_idea_relations(idea_id)
        changes["project_id"] = body.project_id
        if idea["status"] not in {"settled", "archived"}:
            changes["status"] = "active" if body.project_id else "inbox"
    if "status" in fields:
        if body.status not in STATUSES - {"settled"}:
            raise HTTPException(400, "无效想法状态")
        changes["status"] = body.status
    if "processing_session_id" in fields:
        session_id = body.processing_session_id or None
        if session_id:
            session = db.get_session(session_id, owner_id=current_user().id)
            if not session:
                raise HTTPException(404, "加工会话不存在")
            if not idea.get("project_id") or session.project_id != idea["project_id"]:
                raise HTTPException(400, "加工会话必须属于同一项目")
        changes["processing_session_id"] = session_id
    updated = db.update_idea(idea_id, **changes)
    return _detail(updated)  # type: ignore[arg-type]


@router.post("/{idea_id}/relations")
def add_relation(idea_id: str, body: RelationBody) -> dict:
    idea = _require_idea(idea_id, write=True)
    target = _require_idea(body.target_idea_id, write=True)
    if body.relation not in RELATIONS:
        raise HTTPException(400, "无效想法关系")
    if idea_id == body.target_idea_id:
        raise HTTPException(400, "不能关联想法自身")
    if idea.get("project_id") != target.get("project_id"):
        raise HTTPException(400, "只能关联同一项目或同一收集箱中的想法")
    db.add_idea_relation(idea_id, body.target_idea_id, body.relation)
    return _detail(_require_idea(idea_id))


@router.delete("/{idea_id}/relations/{target_idea_id}/{relation}")
def remove_relation(idea_id: str, target_idea_id: str, relation: str) -> dict:
    _require_idea(idea_id, write=True)
    _require_idea(target_idea_id, write=True)
    if relation not in RELATIONS:
        raise HTTPException(400, "无效想法关系")
    db.remove_idea_relation(idea_id, target_idea_id, relation)
    return _detail(_require_idea(idea_id))


@router.post("/{idea_id}/apply-processing")
def apply_processing(idea_id: str) -> dict:
    idea = _require_idea(idea_id, write=True)
    session_id = idea.get("processing_session_id")
    session = db.get_session(session_id, owner_id=current_user().id) if session_id else None
    if not session or session.project_id != idea.get("project_id"):
        raise HTTPException(409, "想法还没有可应用的加工会话")
    messages = [
        message for message in db.list_messages(session.id)
        if message.role == "assistant" and message.content.strip() and not message.error
    ]
    if not messages:
        raise HTTPException(409, "加工会话还没有完成的 Agent 回复")
    updated = db.update_idea(
        idea_id, processed_content=messages[-1].content.strip(),
        status="active" if idea.get("project_id") else "inbox",
    )
    return _detail(updated)  # type: ignore[arg-type]


def _memory_addition(idea: dict) -> str:
    body = (idea.get("processed_content") or idea["content"]).strip()
    return f"<!-- agentmate-idea:{idea['id']} -->\n## 想法：{idea['title']}\n\n{body}"


@router.get("/{idea_id}/memory-preview")
def memory_preview(idea_id: str) -> dict:
    idea = _require_idea(idea_id, write=True)
    if not idea.get("project_id"):
        raise HTTPException(400, "请先把想法归入项目")
    current = workspace_memory.read_curated(idea["project_id"])
    addition = _memory_addition(idea)
    proposed = current if f"agentmate-idea:{idea_id}" in current else "\n\n".join(filter(None, (current, addition)))
    return {
        "current": current,
        "addition": addition,
        "proposed": proposed,
        "base_sha256": hashlib.sha256(current.encode("utf-8")).hexdigest(),
        "would_exceed": len(proposed) > workspace_memory.CURATED_MAX_CHARS,
    }


def _existing_work_item(idea_id: str, project_id: str):
    return next((
        item for item in db.list_work_items(project_id)
        if str((item.custom_fields or {}).get("idea_id") or "") == idea_id
    ), None)


def _existing_decision(idea_id: str, project_id: str) -> dict | None:
    marker = f"idea:{idea_id}"
    return next((
        item for item in db.list_project_governance(project_id)
        if item.get("record_type") == "decision" and item.get("evidence_label") == marker
    ), None)


@router.post("/{idea_id}/settle")
def settle_idea(idea_id: str, body: SettleBody, authorization: str = Header(default="")) -> dict:
    if body.kind not in SETTLEMENTS:
        raise HTTPException(400, "无效沉淀类型")
    with _settle_lock:
        idea = _require_idea(idea_id, write=True)
        project_id = idea.get("project_id")
        if not project_id:
            raise HTTPException(400, "请先把想法归入项目")
        if idea["status"] == "archived":
            raise HTTPException(409, "已归档想法不能沉淀")
        if idea.get("settled_type"):
            if idea["settled_type"] != body.kind:
                raise HTTPException(409, "想法已经沉淀到其他目标")
            return {"idea": _detail(idea), "target": {"type": body.kind, "id": idea["settled_id"]}, "created": False}

        content = (idea.get("processed_content") or idea["content"]).strip()
        created = False
        if body.kind == "work_item":
            existing = _existing_work_item(idea_id, project_id)
            if existing:
                target_id = existing.id
            else:
                target = work_items.create_item(work_items.CreateWorkItemBody(
                    project_id=project_id, title=idea["title"], description=content,
                    source="想法收集箱", labels=["idea"], custom_fields={"idea_id": idea_id},
                ), authorization)
                target_id = str(target["id"])
                created = True
        elif body.kind == "decision":
            existing_decision = _existing_decision(idea_id, project_id)
            if existing_decision:
                target_id = str(existing_decision["id"])
            else:
                target = governance.create_record(governance.CreateBody(
                    project_id=project_id, record_type="decision", title=idea["title"],
                    description=content, rationale="由想法收集箱经用户确认沉淀",
                    evidence_label=f"idea:{idea_id}",
                ), authorization)
                target_id = str(target["id"])
                created = True
        else:
            current = workspace_memory.read_curated(project_id)
            current_hash = hashlib.sha256(current.encode("utf-8")).hexdigest()
            if body.memory_base_sha256 != current_hash:
                raise HTTPException(409, "项目知识已变化，请重新预览后确认")
            marker = f"agentmate-idea:{idea_id}"
            if marker not in current:
                proposed = "\n\n".join(filter(None, (current, _memory_addition(idea))))
                try:
                    workspace_memory.write_curated(project_id, proposed)
                except ValueError as exc:
                    raise HTTPException(400, str(exc)) from exc
                created = True
            target_id = f"MEMORY.md#idea-{idea_id}"

        updated = db.update_idea(
            idea_id, status="settled", settled_type=body.kind, settled_id=target_id,
        )
        return {
            "idea": _detail(updated),  # type: ignore[arg-type]
            "target": {"type": body.kind, "id": target_id},
            "created": created,
        }
