"""Chat — the M1 core. POST /api/chat returns a real SSE stream from the LLM."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import server_sync
import server_client
import run_transport
from agent import events, runtime
from auth.deps import current_user
from storage import db
from storage.models import Message, Project, Role, User

router = APIRouter(prefix="/api", tags=["chat"])


class ChatBody(BaseModel):
    # Field caps bound the payload at validation time (WB-010); the runtime further
    # truncates ref bodies. Over-limit requests get a 422 rather than bloating the
    # context or memory.
    text: str = Field(max_length=200_000)
    session_id: str | None = None
    title: str | None = Field(default=None, max_length=200)
    space: str | None = None
    model: str | None = None
    plan: bool = False
    ask: bool = False
    project_id: str | None = None
    # Per-message loadout picked from the composer ＋ menu (merged with the
    # project's own experts/skills/connectors when the session belongs to one).
    experts: list[str] = Field(default=[], max_length=50)
    skills: list[str] = Field(default=[], max_length=50)
    skill_bundles: list[str] = Field(default=[], max_length=20)
    connectors: list[str] = Field(default=[], max_length=50)
    # 挂载的 GLM 知识库 id（WB-143）：本轮 agent 可用 knowledge_retrieve 检索。
    knowledge_ids: list[str] = Field(default=[], max_length=20)
    # Attached / referenced files: injected into this turn's context only.
    refs: list[dict] = Field(default=[], max_length=50)
    # Client-generated key makes reconnect/retry safe: the same owner/key reuses
    # the original Run without persisting or executing the turn twice (WB-242).
    idempotency_key: str | None = Field(default=None, max_length=200)
    retry_of: str | None = None
    # Server-authoritative history snapshot for a Desktop that has no local
    # execution-session cache (new/reinstalled device). It is context input only;
    # the local compatibility adapter never becomes the durable message source.
    history: list[dict[str, str]] = Field(default=[], max_length=200)


class LocalRunInputBody(BaseModel):
    request_key: str = Field(min_length=8, max_length=200, pattern=r"^[A-Za-z0-9._:-]+$")
    refs: list[dict] = Field(default=[], max_length=50)


@router.get("/device-runtime-status")
def device_runtime_status() -> dict:
    """Non-secret browser-dev view of the loopback Local Agent status."""
    import local_agent_core

    return local_agent_core._status()


@router.put("/local-run-inputs")
def stage_local_run_input(body: LocalRunInputBody) -> dict:
    """Browser-dev bridge; AuthMiddleware binds and scopes the local input."""
    import local_agent_store

    user = current_user()
    user_token = local_agent_store.get_server_identity(user.id)
    if not user_token or not run_transport.ensure_device(user.id, user_token):
        raise HTTPException(503, "Local Agent device registration is unavailable")
    try:
        local_agent_store.stage_run_input(user.id, body.request_key, {"refs": body.refs})
    except ValueError as exc:
        raise HTTPException(413, str(exc)) from exc
    return {
        "staged": True, "request_key": body.request_key,
        "device_id": run_transport.device_id(user.id),
    }


SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    # Defeat proxy buffering so each event flushes immediately.
    "X-Accel-Buffering": "no",
}


async def _load_server_project(user: User, project_id: str) -> Project:
    """Resolve project execution context without writing a local business mirror."""
    token = db.get_server_identity(user.id) or ""
    remote = await asyncio.to_thread(server_client.get_project, token, project_id)
    if remote is None:
        raise HTTPException(503, "Server project is unavailable to Local Agent")
    if str(remote.get("role") or "").lower() == "viewer":
        raise HTTPException(403, "只读成员不能在此项目中执行")
    return Project(
        id=str(remote["id"]), name=str(remote.get("name") or ""),
        owner_id=str(remote.get("owner_id") or user.id),
        instruction=str(remote.get("instruction") or ""),
        connectors=[str(value) for value in remote.get("connectors") or []],
        experts=[str(value) for value in remote.get("experts") or []],
        skills=[str(value) for value in remote.get("skills") or []],
        knowledge_ids=[str(value) for value in remote.get("knowledge_ids") or []],
        created_at=float(remote.get("created_at") or 0),
        updated_at=float(remote.get("updated_at") or 0),
        origin="server", org_id=str(remote.get("org_id") or "") or None,
    )


@router.post("/chat")
async def chat(body: ChatBody):
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(400, "empty message")

    user = current_user()

    retry_run = None
    project_override: Project | None = None
    existing_run = (
        db.get_run_by_idempotency(user.id, body.idempotency_key)
        if body.idempotency_key and body.idempotency_key.strip() else None
    )
    if existing_run:
        if body.session_id and body.session_id != existing_run.session_id:
            raise HTTPException(409, "idempotency key belongs to another session")
        session = db.get_session(existing_run.session_id, owner_id=user.id)
        if not session:
            raise HTTPException(409, "idempotent run session no longer exists")
    elif body.retry_of:
        original = db.get_run(body.retry_of)
        if not original or original.owner_id != user.id:
            raise HTTPException(404, "retry run not found")
        if original.status not in {"failed", "cancelled", "paused"}:
            raise HTTPException(409, "only failed, cancelled or paused runs can be retried")
        if body.session_id and body.session_id != original.session_id:
            raise HTTPException(409, "retry run belongs to another session")
        session = db.get_session(original.session_id, owner_id=user.id)
        if not session:
            raise HTTPException(409, "retry run session no longer exists")
        retry_run = original

    if existing_run or retry_run:
        pass
    elif body.session_id:
        # owner-scoped so a guessed session id can't be driven by another user (WB-013).
        session = db.get_session(body.session_id, owner_id=user.id)
        if not session:
            raise HTTPException(404, "session not found")
    else:
        # New session: if it targets a project, the caller must have access to it,
        # else a stranger could drive a run inside that project's workspace sandbox
        # (WB-050). Mirrors the owner-scoping of the session_id branch above. A Viewer
        # is read-only (M7 C2): a project run executes write_file/run_command in the
        # project sandbox, which a Viewer must not do (WB-153).
        if body.project_id:
            role = db.project_access_role(body.project_id, user.id)
            if role is None:
                project_override = await _load_server_project(user, body.project_id)
            elif role == Role.VIEWER:
                raise HTTPException(403, "只读成员不能在此项目中执行")
        title = (body.title or text)[:26]
        session = db.create_session(
            owner_id=user.id,
            title=title,
            kind="projexec" if body.project_id else "chat",
            space=body.space,
            project_id=body.project_id,
        )

    # A mapped local execution session survives across turns, while the durable
    # project remains Server-only. Re-resolve its transient context on every turn
    # instead of depending on the retired local project mirror.
    if session.project_id and project_override is None and db.get_project(session.project_id) is None:
        project_override = await _load_server_project(user, session.project_id)

    # A todo ref is a request to link this execution to a real WorkItem. Validate
    # before opening the SSE response so a forged/stale item id cannot crash the
    # generator or attach a Run across project boundaries (WB-242).
    for ref in body.refs:
        if ref.get("kind") != "todo" or not ref.get("itemId"):
            continue
        item = db.get_work_item(str(ref["itemId"]))
        if not item or not session.project_id or item.project_id != session.project_id:
            if not project_override or not session.project_id:
                raise HTTPException(400, "invalid work item reference")
            token = db.get_server_identity(user.id) or ""
            remote_items = await asyncio.to_thread(
                server_client.list_work_items, token, session.project_id,
            )
            if remote_items is None:
                raise HTTPException(503, "Server work items are unavailable to Local Agent")
            if not any(str(candidate.get("id")) == str(ref["itemId"]) for candidate in remote_items):
                raise HTTPException(400, "invalid work item reference")

    async def event_stream():
        # First frame tells the client which session this stream belongs to
        # (essential when the session was just created).
        yield events.sse("session", {"id": session.id, "title": session.title})
        async for chunk in runtime.run_chat(
            session, user, text,
            model=body.model, plan=body.plan, ask=body.ask,
            experts=body.experts, skills=body.skills, connectors=body.connectors,
            bundle_ids=body.skill_bundles,
            knowledge_ids=body.knowledge_ids,
            refs=body.refs,
            idempotency_key=body.idempotency_key,
            retry_of=body.retry_of,
            history_override=[
                Message(
                    id=f"server-history-{index}", session_id=session.id,
                    role=str(item.get("role") or ""), content=str(item.get("content") or "")[:1_000_000],
                    actor=str(item.get("role") or "server"),
                )
                for index, item in enumerate(body.history)
                if item.get("role") in {"user", "assistant"} and item.get("content")
            ],
            project_override=project_override,
        ):
            yield chunk
        # WB-062 Phase 3: 项目会话完成 → 入 outbox 回传团队时间线（guarded：仅 Server 镜像项目 +
        # 开了上报开关才入队；非致命，绝不影响本次回复）。
        try:
            server_sync.enqueue_timeline_event(session=session, actor_id=user.id, actor_name=user.name)
        except Exception:  # noqa: BLE001
            pass

    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers=SSE_HEADERS
    )


@router.post("/chat/{session_id}/stop")
def stop(session_id: str) -> dict:
    # Owner-scoped: a teammate who can READ a session id (M7 C3) must not be able to
    # abort someone else's in-flight run (WB-153).
    if not db.get_session(session_id, owner_id=current_user().id):
        raise HTTPException(404, "session not found")
    stopped = runtime.request_stop(session_id)
    return {"stopped": stopped}


class AnswerBody(BaseModel):
    answers: list[str]


@router.post("/chat/{session_id}/answer")
async def answer(session_id: str, body: AnswerBody) -> dict:
    # Deliver the ask_user answers and wake the suspended agent (same SSE stream).
    # Async so submit_answers runs on the event loop (asyncio.Event.set()).
    # Owner-scoped so a teammate can't inject text into another user's suspended
    # ask_user turn (WB-153).
    if not db.get_session(session_id, owner_id=current_user().id):
        raise HTTPException(404, "session not found")
    ok = runtime.submit_answers(session_id, body.answers)
    return {"ok": ok}
