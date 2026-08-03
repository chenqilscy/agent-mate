"""AgentMate Server 配置（WB-061）—— 独立于 backend/config.py。

Server 是中心控制平面服务（账号/组织/项目/成员/邀请的权威源）。可自托管的单体：
默认 SQLite（server.db），规模上来可换 Postgres。绝不承载 LLM 凭据（那永远只在本地）。
WB-290 起它同时是项目级知识库的安全网关：WeKnora 服务凭据只存在 Server 进程环境，
AgentMate/Console 仅持 Server token。旧 WB-171 文档字节只用于显式迁移与回滚，不是 agent 沙箱同步。
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
    ENVIRONMENT: str = os.getenv("AGENTMATE_ENVIRONMENT", "development").strip().lower()
    SSO_SECRET_ENCRYPTION_KEY: str = os.getenv(
        "AGENTMATE_SSO_SECRET_ENCRYPTION_KEY", ""
    ).strip()
    SSO_LOCAL_KEY_PATH: str = os.getenv(
        "AGENTMATE_SSO_LOCAL_KEY_PATH", ""
    ).strip()
    # pbkdf2 迭代次数（与 backend 一致的口令散列强度）。
    PBKDF2_ITERS: int = int(os.getenv("AGENTMATE_SERVER_PBKDF2_ITERS", "600000"))
    AUTH_RATE_LIMIT_PER_MINUTE: int = max(
        1, int(os.getenv("AGENTMATE_AUTH_RATE_LIMIT_PER_MINUTE", "10"))
    )
    SSO_PUBLIC_BASE_URL: str = os.getenv(
        "AGENTMATE_SSO_PUBLIC_BASE_URL", f"http://127.0.0.1:{PORT}"
    ).strip().rstrip("/")
    SSO_STATE_TTL_SECONDS: int = max(
        60, int(os.getenv("AGENTMATE_SSO_STATE_TTL_SECONDS", "600"))
    )
    SSO_REGISTRATION_POLICY: str = os.getenv(
        "AGENTMATE_SSO_REGISTRATION_POLICY", "invite_only"
    ).strip().lower()
    BOOTSTRAP_ADMIN_SECRET: str = os.getenv(
        "AGENTMATE_BOOTSTRAP_ADMIN_SECRET", ""
    ).strip()
    MIN_PASSWORD_LENGTH: int = max(
        12, int(os.getenv("AGENTMATE_MIN_PASSWORD_LENGTH", "12"))
    )
    # Server Bearer token 有界生命周期（WB-326）。默认 30 天；存量无 expires_at 的 token
    # 升级后仅保留 7 天兼容窗口，避免无限续用，同时不强制所有在线用户立即掉线。
    TOKEN_TTL_SECONDS: int = max(
        1, int(os.getenv("AGENTMATE_SERVER_TOKEN_TTL_SECONDS", "2592000"))
    )
    TOKEN_LEGACY_GRACE_SECONDS: int = max(
        1, int(os.getenv("AGENTMATE_SERVER_TOKEN_LEGACY_GRACE_SECONDS", "604800"))
    )
    RELAY_RATE_LIMIT_PER_MINUTE: int = max(
        1, int(os.getenv("AGENTMATE_RELAY_RATE_LIMIT_PER_MINUTE", "60"))
    )
    RELAY_LEASE_SECONDS: int = max(
        10, int(os.getenv("AGENTMATE_RELAY_LEASE_SECONDS", "120"))
    )
    RELAY_MAX_ATTEMPTS: int = max(
        1, int(os.getenv("AGENTMATE_RELAY_MAX_ATTEMPTS", "5"))
    )
    RELAY_PAYLOAD_RETENTION_SECONDS: int = max(
        60, int(os.getenv("AGENTMATE_RELAY_PAYLOAD_RETENTION_SECONDS", "86400"))
    )
    RELAY_TERMINAL_RETENTION_SECONDS: int = max(
        RELAY_PAYLOAD_RETENTION_SECONDS,
        int(os.getenv("AGENTMATE_RELAY_TERMINAL_RETENTION_SECONDS", "2592000")),
    )
    RELAY_MAX_TERMINAL_ROWS_PER_OWNER: int = max(
        100, int(os.getenv("AGENTMATE_RELAY_MAX_TERMINAL_ROWS_PER_OWNER", "50000"))
    )
    RELAY_CLEANUP_INTERVAL_SECONDS: int = max(
        60, int(os.getenv("AGENTMATE_RELAY_CLEANUP_INTERVAL_SECONDS", "3600"))
    )
    # Public desktop update telemetry is best-effort operational data, never an
    # unbounded audit log. Dedupe retries and enforce both age and row caps.
    UPDATE_EVENT_DEDUPE_SECONDS: int = max(
        1, int(os.getenv("AGENTMATE_UPDATE_EVENT_DEDUPE_SECONDS", "60"))
    )
    UPDATE_EVENT_RETENTION_SECONDS: int = max(
        3600, int(os.getenv("AGENTMATE_UPDATE_EVENT_RETENTION_SECONDS", "7776000"))
    )
    UPDATE_EVENT_MAX_ROWS: int = max(
        1000, int(os.getenv("AGENTMATE_UPDATE_EVENT_MAX_ROWS", "100000"))
    )
    # 邀请码有效期（秒）；默认 7 天，避免久留可被反复利用的活码（WB-156，配合单次使用）。
    # 显式设 AGENTMATE_SERVER_INVITE_TTL=0 可回到永不过期（部署自担风险）。
    INVITE_TTL: int = int(os.getenv("AGENTMATE_SERVER_INVITE_TTL", "604800"))
    # 中央项目知识库（WB-290）。使用专用变量，避免误读本地 backend 的 owner 级 WEKNORA_*。
    # API Key 是 WeKnora 租户服务凭据：只在 Server 进程内使用，任何 API 都不得回传。
    WEKNORA_URL: str = os.getenv("AGENTMATE_SERVER_WEKNORA_URL", "http://localhost:8080").strip().rstrip("/")
    WEKNORA_API_KEY: str = os.getenv("AGENTMATE_SERVER_WEKNORA_API_KEY", "").strip()
    WEKNORA_EMBEDDING_MODEL_ID: str = os.getenv(
        "AGENTMATE_SERVER_WEKNORA_EMBEDDING_MODEL_ID", ""
    ).strip()

settings = Settings()
