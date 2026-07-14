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
    # 邀请码有效期（秒）；默认 7 天，避免久留可被反复利用的活码（WB-156，配合单次使用）。
    # 显式设 HUB_INVITE_TTL=0 可回到永不过期（部署自担风险）。
    INVITE_TTL: int = int(os.getenv("HUB_INVITE_TTL", "604800"))

    # SkillHub 目录镜像（WB-069）：Hub 复用本机 skillhub CLI 抓取，定时同步进 catalog。
    SKILLHUB_CLI: Path = Path(
        os.getenv("SKILLHUB_CLI", str(Path.home() / ".skillhub" / "skills_store_cli.py"))
    )
    # CLI 子进程 cwd（search/rankings 不落盘，仅需一个可写目录，放仓库外避免污染）。
    SKILLHUB_WORK_DIR: Path = Path(
        os.getenv("SKILLHUB_WORK_DIR", str(Path.home() / ".workbuddy" / "hub-skillhub"))
    )
    # 定时同步间隔（秒）；0 = 关闭后台循环（仍可管理员手动触发）。默认 12h。
    SKILLHUB_SYNC_INTERVAL: int = int(os.getenv("SKILLHUB_SYNC_INTERVAL", str(12 * 3600)))


settings = Settings()
