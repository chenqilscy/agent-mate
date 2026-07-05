"""Chat — the M1 core. POST /api/chat returns a real SSE stream from the LLM."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent import events, runtime
from auth.deps import current_user
from storage import db

router = APIRouter(prefix="/api", tags=["chat"])


class ChatBody(BaseModel):
    text: str
    session_id: str | None = None
    title: str | None = None
    space: str | None = None
    model: str | None = None
    plan: bool = False
    project_id: str | None = None


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
        session = db.get_session(body.session_id)
        if not session:
            raise HTTPException(404, "session not found")
    else:
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
        async for chunk in runtime.run_chat(session, user, text, model=body.model, plan=body.plan):
            yield chunk

    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers=SSE_HEADERS
    )


@router.post("/chat/{session_id}/stop")
def stop(session_id: str) -> dict:
    stopped = runtime.request_stop(session_id)
    return {"stopped": stopped}


class AnswerBody(BaseModel):
    answers: list[str]


@router.post("/chat/{session_id}/answer")
async def answer(session_id: str, body: AnswerBody) -> dict:
    # Deliver the ask_user answers and wake the suspended agent (same SSE stream).
    # Async so submit_answers runs on the event loop (asyncio.Event.set()).
    ok = runtime.submit_answers(session_id, body.answers)
    return {"ok": ok}
