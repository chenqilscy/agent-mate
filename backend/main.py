"""WorkBuddy backend entrypoint (FastAPI + SSE).

Local-first: this runs on the user's machine as a localhost service. The browser
(Vite dev server, or the Tauri shell in M5) is just the display. All routes pass
through the auth dependency which, in M1, injects the fixed local user.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from routers import chat, files, me, models, projects, sessions, work_items
from storage import db

app = FastAPI(title="WorkBuddy API", version="0.1.0")

# During M0–M4 the UI is served by Vite on :5173 and proxies /api. CORS stays
# permissive for localhost so direct-origin dev (no proxy) also works.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    db.init_db()


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "llm_configured": settings.llm_configured}


app.include_router(me.router)
app.include_router(models.router)
app.include_router(sessions.router)
app.include_router(chat.router)
app.include_router(files.router)
app.include_router(projects.router)
app.include_router(work_items.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=True)
