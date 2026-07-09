"""WorkBuddy Hub —— 中心控制平面服务入口（WB-061）。

独立于本地 backend：账号/组织/项目/成员/邀请的权威源 + 鉴权签发。可自托管的单体，
默认 SQLite。绝不承载 LLM 凭据 / 沙箱文件（那些永远只在本地）。

运行：`cd hub && python main.py`（默认 127.0.0.1:8100；HUB_DB/HUB_PORT 可覆盖）。
"""
from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# 扁平 import（同 backend）：无论从何处启动，都把 hub/ 放进模块搜索路径。
sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402

_CONSOLE = Path(__file__).resolve().parent / "web" / "console.html"

import db  # noqa: E402
import skillhub_client  # noqa: E402
import skillhub_sync  # noqa: E402
from config import settings  # noqa: E402
from routers import auth, catalog, comments, invites, milestones, notifications, orgs, projects, settings as settings_router, timeline, work_items  # noqa: E402

db.init_db()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动后台 SkillHub 目录镜像同步循环（WB-069）；无 CLI / 间隔=0 时不启。"""
    task = None
    if settings.SKILLHUB_SYNC_INTERVAL > 0 and skillhub_client.cli_available():
        task = asyncio.create_task(skillhub_sync.run_periodic())
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


app = FastAPI(title="WorkBuddy Hub API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=False,
    allow_methods=["*"], allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
def console() -> str:
    """WorkBuddy Manager —— Hub 自带的 web 管理端（原 BuddyWebMgr，WB-068/078/112）：单文件、同源调 /api，无构建管线。"""
    try:
        return _CONSOLE.read_text(encoding="utf-8")
    except OSError:
        return "<h1>WorkBuddy Manager</h1><p>console.html missing</p>"


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "service": "hub"}


app.include_router(auth.router)
app.include_router(orgs.router)
app.include_router(projects.router)
app.include_router(invites.router)
app.include_router(catalog.router)
app.include_router(timeline.router)
app.include_router(comments.router)
app.include_router(notifications.router)
app.include_router(work_items.router)
app.include_router(milestones.router)
app.include_router(settings_router.router)


if __name__ == "__main__":
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
