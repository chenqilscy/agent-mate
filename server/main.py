"""AgentMate Server —— 中心控制平面服务入口（WB-061）。

独立于本地 backend：账号/组织/项目/成员/邀请的权威源 + 鉴权签发。可自托管的单体，
默认 SQLite。绝不承载 LLM 凭据 / 沙箱文件（那些永远只在本地）。

运行：`cd server && python main.py`（默认 127.0.0.1:8100；AGENTMATE_SERVER_DB/AGENTMATE_SERVER_PORT 可覆盖）。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 扁平 import（同 backend）：无论从何处启动，都把 server/ 放进模块搜索路径。
sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn  # noqa: E402
from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

_CONSOLE_DIST = Path(__file__).resolve().parent / "web" / "console-dist"
_CONSOLE_NEXT = _CONSOLE_DIST / "index.html"

import db  # noqa: E402
from config import settings  # noqa: E402
from routers import accounts, auth, catalog, comments, desktop_updates, invites, knowledge, milestones, notifications, orgs, pm, projects, timeline, work_items  # noqa: E402

db.init_db()


app = FastAPI(title="AgentMate Server API", version="1.0.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=False,
    allow_methods=["*"], allow_headers=["*"],
)
if _CONSOLE_DIST.is_dir():
    # Vite index 使用 /console-assets/assets/*；挂载构建根而不是 assets 子目录。
    app.mount("/console-assets", StaticFiles(directory=_CONSOLE_DIST), name="console-assets")


def _console_next_html() -> str:
    """React + Ant Design Console；生产部署必须包含构建产物。"""
    try:
        return _CONSOLE_NEXT.read_text(encoding="utf-8")
    except OSError:
        return "<h1>AgentMate Console</h1><p>Console build missing. Run pnpm build:console.</p>"


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def console() -> str:
    """AgentMate Console —— React + Ant Design，同源调用 /api。"""
    return _console_next_html()


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "service": "server"}


app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(orgs.router)
app.include_router(projects.router)
app.include_router(invites.router)
app.include_router(catalog.router)
app.include_router(timeline.router)
app.include_router(comments.router)
app.include_router(notifications.router)
app.include_router(work_items.router)
app.include_router(milestones.router)
app.include_router(pm.router)
app.include_router(knowledge.router)
app.include_router(desktop_updates.router)


@app.get("/{console_path:path}", response_class=HTMLResponse, include_in_schema=False)
def console_page(console_path: str) -> str:
    """Console History API 深链回退；未知 API 不能被 HTML 入口伪装成成功。"""
    if console_path == "api" or console_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not Found")
    return _console_next_html()


if __name__ == "__main__":
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
