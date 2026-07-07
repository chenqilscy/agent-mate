"""WorkBuddy Hub —— 中心控制平面服务入口（WB-061）。

独立于本地 backend：账号/组织/项目/成员/邀请的权威源 + 鉴权签发。可自托管的单体，
默认 SQLite。绝不承载 LLM 凭据 / 沙箱文件（那些永远只在本地）。

运行：`cd hub && python main.py`（默认 127.0.0.1:8100；HUB_DB/HUB_PORT 可覆盖）。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 扁平 import（同 backend）：无论从何处启动，都把 hub/ 放进模块搜索路径。
sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

import db  # noqa: E402
from config import settings  # noqa: E402
from routers import auth, catalog, invites, orgs, projects, timeline  # noqa: E402

db.init_db()

app = FastAPI(title="WorkBuddy Hub API", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=False,
    allow_methods=["*"], allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "service": "hub"}


app.include_router(auth.router)
app.include_router(orgs.router)
app.include_router(projects.router)
app.include_router(invites.router)
app.include_router(catalog.router)
app.include_router(timeline.router)


if __name__ == "__main__":
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
