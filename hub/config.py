"""WorkBuddy Hub 配置（WB-061）—— 独立于 backend/config.py。

Hub 是中心控制平面服务（账号/组织/项目/成员/邀请的权威源）。可自托管的单体：
默认 SQLite（hub.db），规模上来可换 Postgres。绝不承载 LLM 凭据 / 沙箱文件（那些永远只在本地）。
"""
from __future__ import annotations

import os
from pathlib import Path

HUB_DIR = Path(__file__).resolve().parent


class Settings:
    # HUB_DB 覆盖库路径（隔离测试 / 第二实例）。
    DB_PATH: Path = Path(os.getenv("HUB_DB", str(HUB_DIR / "hub.db")))
    HOST: str = os.getenv("HUB_HOST", "127.0.0.1")
    PORT: int = int(os.getenv("HUB_PORT", "8100"))
    # pbkdf2 迭代次数（与 backend 一致的口令散列强度）。
    PBKDF2_ITERS: int = int(os.getenv("HUB_PBKDF2_ITERS", "100000"))
    # 邀请码有效期（秒）；0 = 永不过期。
    INVITE_TTL: int = int(os.getenv("HUB_INVITE_TTL", "0"))


settings = Settings()
