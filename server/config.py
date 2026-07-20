"""AgentMate Server 配置（WB-061）—— 独立于 backend/config.py。

Server 是中心控制平面服务（账号/组织/项目/成员/邀请的权威源）。可自托管的单体：
默认 SQLite（server.db），规模上来可换 Postgres。绝不承载 LLM 凭据（那永远只在本地）。
唯一落盘的用户内容是知识库文档（WB-171，STORAGE_DIR）——那是用户**显式**放入共享控制面的
团队资料（类比 WB-093 把连接器 token 存 Server），不同于绝不上云的 agent 沙箱工作区文件。
"""
from __future__ import annotations

import os
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent


class Settings:
    # AGENTMATE_SERVER_DB 覆盖库路径（隔离测试 / 第二实例）。
    DB_PATH: Path = Path(os.getenv("AGENTMATE_SERVER_DB", str(SERVER_DIR / "server.db")))
    # 知识库文档字节的落盘根（WB-171）；AGENTMATE_SERVER_STORAGE 覆盖（隔离测试 / 第二实例）。已 .gitignore。
    STORAGE_DIR: Path = Path(os.getenv("AGENTMATE_SERVER_STORAGE", str(SERVER_DIR / "storage")))
    HOST: str = os.getenv("AGENTMATE_SERVER_HOST", "127.0.0.1")
    PORT: int = int(os.getenv("AGENTMATE_SERVER_PORT", "8100"))
    # pbkdf2 迭代次数（与 backend 一致的口令散列强度）。
    PBKDF2_ITERS: int = int(os.getenv("AGENTMATE_SERVER_PBKDF2_ITERS", "100000"))
    # 邀请码有效期（秒）；默认 7 天，避免久留可被反复利用的活码（WB-156，配合单次使用）。
    # 显式设 AGENTMATE_SERVER_INVITE_TTL=0 可回到永不过期（部署自担风险）。
    INVITE_TTL: int = int(os.getenv("AGENTMATE_SERVER_INVITE_TTL", "604800"))

settings = Settings()
