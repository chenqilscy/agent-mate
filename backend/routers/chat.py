"""Chat — the M1 core. POST /api/chat returns a real SSE stream from the LLM."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import server_sync
from agent import events, runtime
from auth.deps import current_user
from storage import db
from storage.models import Role

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
    connectors: list[str] = Field(default=[], max_length=50)
    # 挂载的 GLM 知识库 id（WB-143）：本轮 agent 可用 knowledge_retrieve 检索。
    knowledge_ids: list[str] = Field(default=[], max_length=20)
    # Attached / referenced files: injected into this turn's context only.
    refs: list[dict] = Field(default=[], max_length=50)


SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    # Defeat proxy buffering so each event flushes immediately.
    "X-Accel-Buffering": "no",
}


@router.post("/chat")
async def chat(body: ChatBody):
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(400, "empty message")

    user = current_user()

    if body.session_id:
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
                raise HTTPException(404, "project not found")
            if role == Role.VIEWER:
                raise HTTPException(403, "只读成员不能在此项目中执行")
        title = (body.title or text)[:26]
        session = db.create_session(
            owner_id=user.id,
            title=title,
            kind="projexec" if body.project_id else "chat",
            space=body.space,
            project_id=body.project_id,
        )

    async def event_stream():
        # First frame tells the client which session this stream belongs to
        # (essential when the session was just created).
        yield events.sse("session", {"id": session.id, "title": session.title})
        async for chunk in runtime.run_chat(
            session, user, text,
            model=body.model, plan=body.plan, ask=body.ask,
            experts=body.experts, skills=body.skills, connectors=body.connectors,
            knowledge_ids=body.knowledge_ids,
            refs=body.refs,
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
