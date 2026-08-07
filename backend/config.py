"""Runtime configuration, loaded from backend/.env where deployment needs it.

LLM model credentials are intentionally not part of this configuration. They
are stored per owner in the local database and resolved by the model manager.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent

# WB-192：本次实际读入的 .env 键名。配置文件中的本地凭据会被 load_dotenv 写进
# os.environ，故通用子进程（run_command）一律不给见 —— 见下方 SECRET_ENV_KEYS。
_ENV_FILE_KEYS: set[str] = set()


def _load_env(path: Path) -> None:
    """load_dotenv + 记下这个 .env 里有哪些键（用于 WB-192 的密钥剔除）。"""
    global _ENV_FILE_KEYS
    load_dotenv(path)
    try:
        _ENV_FILE_KEYS |= {k for k in dotenv_values(path) if k}
    except OSError:
        pass  # 读不到就退回下面按名字模式识别的兜底名单

# Frozen (PyInstaller sidecar) awareness: a bundled exe's __file__ lives in a
# temp extraction dir that's wiped on exit, so the DB / workspace must live in a
# persistent per-user data dir instead, and .env is looked up next to the exe.
# In dev (not frozen) everything stays under backend/ exactly as before.
FROZEN = getattr(sys, "frozen", False)


def _user_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    d = base / "AgentMate"
    d.mkdir(parents=True, exist_ok=True)
    return d


if FROZEN:
    EXE_DIR = Path(sys.executable).resolve().parent
    DATA_DIR = _user_data_dir()
    # .env next to the exe wins, else the data dir.
    for _env in (EXE_DIR / ".env", DATA_DIR / ".env"):
        if _env.exists():
            _load_env(_env)
            break
else:
    DATA_DIR = BACKEND_DIR
    _load_env(BACKEND_DIR / ".env")


class Settings:
    # Public compatibility metadata sent to AgentMate Server. It contains no secrets.
    # Release packaging sets AGENTMATE_APP_VERSION to the signed desktop version.
    APP_VERSION: str = os.getenv("AGENTMATE_APP_VERSION", "1.0.0").strip()
    TOOL_CONTRACT_VERSION: str = os.getenv("AGENTMATE_TOOL_CONTRACT_VERSION", "1").strip()
    # 可选 Langfuse LLM 可观测性（WB-230）。默认关闭；即使启用，提示词/回复/工具正文也要
    # LANGFUSE_CAPTURE_CONTENT=1 才上传。密钥只在本地 backend 读取，且下方 SECRET_ENV_KEYS
    # 会把 LANGFUSE_SECRET_KEY 从 run_command 子进程环境剔除。
    LANGFUSE_ENABLED: bool = os.getenv("LANGFUSE_ENABLED", "0").strip().lower() in ("1", "true", "yes")
    LANGFUSE_PUBLIC_KEY: str = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    LANGFUSE_SECRET_KEY: str = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
    LANGFUSE_BASE_URL: str = os.getenv("LANGFUSE_BASE_URL", "").strip().rstrip("/")
    LANGFUSE_TRACING_ENVIRONMENT: str = os.getenv("LANGFUSE_TRACING_ENVIRONMENT", "development").strip()
    LANGFUSE_SAMPLE_RATE: str = os.getenv("LANGFUSE_SAMPLE_RATE", "1.0").strip()
    LANGFUSE_CAPTURE_CONTENT: bool = os.getenv("LANGFUSE_CAPTURE_CONTENT", "0").strip().lower() in ("1", "true", "yes")

    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8101"))

    # 知识库改用自托管 WeKnora（WB-173）：后端当 WeKnora 客户端，X-API-Key 打其 REST /api/v1。
    # 这三个只是**兜底**（WB-188）：连接配置现在按 owner 存 DB（UI 表单填，见 agent/weknora.py
    # 的 conf()：DB 优先、这里兜底），故存量 .env 用户零破坏、新用户不必碰配置文件。
    # 无论存哪，key 都只在后端解析、绝不回前端（铁律#4）；都没配 → 知识库接口 400 引导去表单。
    # WEKNORA_API_KEY = WeKnora :80 注册账号后账号页拿到的租户 API Key（sk-...），非 WeKnora .env 里的那个。
    # 部署见 docs/weknora-部署.md。
    WEKNORA_URL: str = os.getenv("WEKNORA_URL", "http://localhost:8080").strip().rstrip("/")
    WEKNORA_API_KEY: str = os.getenv("WEKNORA_API_KEY", "").strip()
    WEKNORA_EMBEDDING_MODEL_ID: str = os.getenv("WEKNORA_EMBEDDING_MODEL_ID", "").strip()

    # Optional connector credentials. Read straight from os.environ by the MCP
    # client's per-connector secret_env (mcp_client.py); listed here for
    # discoverability. Forwarded ONLY to the owning connector's subprocess.
    GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "").strip()
    # Telegram connector (built-in mcp_servers/telegram.py, read at call time).
    # TELEGRAM_CHAT_ID is an optional default target for send_message.
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    # 助理外部渠道（WB-072）：Telegram 长轮询桥接的开关。默认关——仅有连接器 token 不会
    # 自动起后台桥接；须显式置 1 才让 bot 收到的消息驱动本机 agent（安全 + local-first 零变化）。
    TELEGRAM_ASSISTANT: bool = os.getenv("TELEGRAM_ASSISTANT", "0").strip().lower() in ("1", "true", "yes")
    # 金山文档 connector (built-in mcp_servers/kdocs.py, shells out to kdocs-cli,
    # read at call time). A WPS 云文档 token; the CLI can also use its own keychain.
    KDOCS_TOKEN: str = os.getenv("KDOCS_TOKEN", "").strip()

    # DB + workspace live in DATA_DIR (backend/ in dev, per-user data dir when frozen).
    # AGENTMATE_DB overrides the DB path (isolated tests / running a second instance).
    DB_PATH: Path = Path(os.getenv("AGENTMATE_DB", str(DATA_DIR / "agentmate.db")))
    # Local Agent Core owns only device identity, Server bindings, active leases
    # and unacknowledged event WAL. It must remain usable without the legacy
    # local business database above.
    LOCAL_AGENT_DB_PATH: Path = Path(
        os.getenv("AGENTMATE_LOCAL_AGENT_DB", str(DATA_DIR / "agentmate-local-agent.db"))
    )

    WORKSPACE_ROOT: Path = Path(
        os.getenv("AGENTMATE_WORKSPACE", str(DATA_DIR / "workspace"))
    ).resolve()

    # SkillHub 已安装技能目录（WB-055）。真实安装把 skill 解压到这里，agent 扫描
    # <dir>/*/SKILL.md 加载。与出货版 AgentMate 及 skillhub CLI 的默认约定一致。
    SKILLS_DIR: Path = Path(
        os.getenv("AGENTMATE_SKILLS_DIR", str(Path.home() / ".agentmate" / "skills"))
    ).expanduser().resolve()
    # skillhub CLI（本机脚本，install.sh --cli-only 装到 ~/.skillhub/）。安装技能时
    # 用后端自己的 Python 直接跑它，避免依赖 bash wrapper / PATH。
    SKILLHUB_CLI: Path = Path(
        os.getenv("SKILLHUB_CLI", str(Path.home() / ".skillhub" / "skills_store_cli.py"))
    ).expanduser()

    # Context window used to compute the context-usage ring (approximate).
    # Clamped to >=1 so a misconfigured CONTEXT_WINDOW=0 can't divide-by-zero
    # at the end of a stream (WB-022).
    CONTEXT_WINDOW: int = max(1, int(os.getenv("CONTEXT_WINDOW", "1000000")))
    # Provider/model metadata may override this. Keep the unknown-model fallback
    # conservative: a context window is not the same as one-call output capacity.
    DEFAULT_MAX_OUTPUT_TOKENS: int = max(
        1, int(os.getenv("DEFAULT_MAX_OUTPUT_TOKENS", "8192"))
    )
    # WB-325：历史会话上下文独立预算。超过上限后，旧轮次由真实 LLM 压缩为持久化滚动摘要，
    # 最近轮次保留原文；即使摘要端点失败也只回退到有界最近窗口。
    SESSION_HISTORY_TOKEN_BUDGET: int = max(
        2_000, int(os.getenv("SESSION_HISTORY_TOKEN_BUDGET", "60000"))
    )
    SESSION_RECENT_TOKEN_BUDGET: int = max(
        1_000, int(os.getenv("SESSION_RECENT_TOKEN_BUDGET", "24000"))
    )
    SESSION_SUMMARY_SOURCE_TOKEN_BUDGET: int = max(
        2_000, int(os.getenv("SESSION_SUMMARY_SOURCE_TOKEN_BUDGET", "30000"))
    )
    SESSION_SUMMARY_MAX_TOKENS: int = max(
        500, int(os.getenv("SESSION_SUMMARY_MAX_TOKENS", "3000"))
    )
    SESSION_SUMMARY_TIMEOUT_SECONDS: float = max(
        5.0, float(os.getenv("SESSION_SUMMARY_TIMEOUT_SECONDS", "30"))
    )

    # 统一后台任务 worker（WB-345）：仅控制本地并发、扫描和租约，不改变各领域自己的预算。
    BACKGROUND_JOB_MAX_CONCURRENCY: int = max(
        1, min(16, int(os.getenv("BACKGROUND_JOB_MAX_CONCURRENCY", "4")))
    )
    BACKGROUND_AGENT_MAX_CONCURRENCY: int = max(
        1, min(32, int(os.getenv("BACKGROUND_AGENT_MAX_CONCURRENCY", "4")))
    )
    BACKGROUND_AGENT_PER_OWNER_CONCURRENCY: int = max(
        1, min(BACKGROUND_AGENT_MAX_CONCURRENCY, int(os.getenv("BACKGROUND_AGENT_PER_OWNER_CONCURRENCY", "2")))
    )
    RELAY_MAX_IN_FLIGHT: int = max(
        1, min(32, int(os.getenv("RELAY_MAX_IN_FLIGHT", "4")))
    )
    RELAY_PER_OWNER_MAX_IN_FLIGHT: int = max(
        1, min(RELAY_MAX_IN_FLIGHT, int(os.getenv("RELAY_PER_OWNER_MAX_IN_FLIGHT", "2")))
    )
    BACKGROUND_JOB_SCAN_SECONDS: float = max(
        0.2, float(os.getenv("BACKGROUND_JOB_SCAN_SECONDS", "2"))
    )
    BACKGROUND_JOB_LEASE_SECONDS: float = max(
        5.0, float(os.getenv("BACKGROUND_JOB_LEASE_SECONDS", "30"))
    )
    BACKGROUND_JOB_RETRY_BACKOFF_SECONDS: float = max(
        0.1, float(os.getenv("BACKGROUND_JOB_RETRY_BACKOFF_SECONDS", "2"))
    )

    # 语音输入本地 ASR（WB-139）。faster-whisper 小模型在本机把录音转文字，音频不出本机。
    # ASR_ENABLED=0 彻底关闭端点；模型首次使用会下载到 ASR_MODEL_DIR（需联网一次）。
    # ASR_MODEL：faster-whisper 尺寸（tiny/base/small/medium/large-v3）或本地路径，默认 base（中文够用、CPU 秒级）。
    # ASR_DEVICE/ASR_COMPUTE_TYPE：默认 cpu + int8（无 GPU 也快、内存小）。
    ASR_ENABLED: bool = os.getenv("ASR_ENABLED", "1").strip().lower() in ("1", "true", "yes")
    ASR_MODEL: str = os.getenv("ASR_MODEL", "base").strip()
    ASR_DEVICE: str = os.getenv("ASR_DEVICE", "cpu").strip()
    ASR_COMPUTE_TYPE: str = os.getenv("ASR_COMPUTE_TYPE", "int8").strip()
    ASR_MODEL_DIR: Path = Path(
        os.getenv("ASR_MODEL_DIR", str(DATA_DIR / "models" / "whisper"))
    ).resolve()

    # AgentMate Server（中心控制平面，WB-061/062）。账号只来自 Server；URL 空时仅保留匿名访客的
    # 本地执行能力。本地 backend 持 Server token 调其 /api/auth/verify 等；凭据/工作区文件绝不上云。
    AGENTMATE_SERVER_URL: str = os.getenv("AGENTMATE_SERVER_URL", "").strip().rstrip("/")
    # WB-326：旧版本地缓存没有 expires_at；升级后只保留短兼容窗口。Server 返回的真实
    # expires_at 始终优先，本值仅用于老 Server / 老数据库兼容。
    SERVER_TOKEN_LEGACY_GRACE_SECONDS: int = max(
        1, int(os.getenv("AGENTMATE_SERVER_TOKEN_LEGACY_GRACE_SECONDS", "604800"))
    )
    # A cached Server identity is accepted without introspection only for this
    # short online window. If Server is unreachable, the explicitly bounded
    # offline grace applies; an authoritative 401/403 always revokes immediately.
    SERVER_TOKEN_VALIDATION_TTL_SECONDS: int = max(
        1, int(os.getenv("AGENTMATE_SERVER_TOKEN_VALIDATION_TTL_SECONDS", "30"))
    )
    SERVER_TOKEN_OFFLINE_GRACE_SECONDS: int = max(
        1, int(os.getenv("AGENTMATE_SERVER_TOKEN_OFFLINE_GRACE_SECONDS", "3600"))
    )
    # 团队时间线上报开关（WB-062 Phase 3）。默认关——执行产出默认不上云（隐私，铁律 4）。
    AGENTMATE_SERVER_TIMELINE_UPLOAD: bool = os.getenv("AGENTMATE_SERVER_TIMELINE_UPLOAD", "0").strip().lower() in ("1", "true", "yes")
    # Local Run events are never dropped. Once this durable WAL reaches its cap,
    # the executor must pause before producing another event until Server ACKs free space.
    RUN_EVENT_WAL_MAX_BYTES: int = max(
        1024 * 1024, int(os.getenv("AGENTMATE_RUN_EVENT_WAL_MAX_BYTES", str(256 * 1024 * 1024)))
    )

    @property
    def server_enabled(self) -> bool:
        return bool(self.AGENTMATE_SERVER_URL)

    @property
    def langfuse_configured(self) -> bool:
        return bool(
            self.LANGFUSE_ENABLED
            and self.LANGFUSE_PUBLIC_KEY
            and self.LANGFUSE_SECRET_KEY
            and self.LANGFUSE_BASE_URL
        )

    @property
    def telegram_assistant_enabled(self) -> bool:
        # 需同时有 bot token 且显式开开关，才启动 Telegram 助理桥接（WB-072）。
        return bool(self.TELEGRAM_BOT_TOKEN) and self.TELEGRAM_ASSISTANT


settings = Settings()


# ---- 后端密钥名单（WB-192）---------------------------------------------
#
# 通用子进程（agent 的 run_command）**不该看见后端自己的密钥**：否则模型一句
# `echo $LLM_API_KEY` 就能把它读进上下文 → 随下一轮上传给 LLM 厂商 + 进 trace/前端
# + 进消息持久化与导出，与铁律#4 冲突。WB-011 早已把**连接器**子进程的 env 收成
# 白名单，run_command 这条一直没收口 —— 本名单就是给它用的。
#
# 名单 = ① 本次 .env 实际读入的所有键（load_dotenv 把它们塞进了 os.environ；
# 非密钥项一并剔除也无害，子命令不需要它们）
# ∪ ② Settings 上按名字模式识别出的密钥字段（兜住「用真实环境变量而非 .env 配」的情况，
# 也让将来新增密钥不必记得回来改这里）。
#
# 为何这里用「剔除」而不是 mcp_client 那种「白名单」：run_command 要跑用户的真实命令
# （npm/git/python/代理…），白名单会误伤（连接器那条路能用白名单，是因为它只跑已知的
# MCP server）。本名单只保证「后端不主动把自己的密钥递给通用 shell」——
# 它**不把 run_command 变成沙箱**（WB-014 的「非真沙箱」结论依然成立）。
_SECRET_NAME_HINTS = ("_KEY", "_TOKEN", "_SECRET", "_PASSWORD", "_PASSWD", "_CREDENTIAL")


def _declared_secret_fields() -> set[str]:
    return {
        name for name, val in vars(Settings).items()
        if name.isupper() and isinstance(val, str) and name.upper().endswith(_SECRET_NAME_HINTS)
    }


SECRET_ENV_KEYS: set[str] = {k.upper() for k in _ENV_FILE_KEYS} | _declared_secret_fields()


def scrubbed_env() -> dict[str, str]:
    """给通用子进程用的环境：os.environ 去掉后端密钥（WB-192）。

    保留 PATH/SYSTEMROOT/代理等一切正常变量 —— 只摘密钥，故不影响真实命令。"""
    return {k: v for k, v in os.environ.items() if k.upper() not in SECRET_ENV_KEYS}


# Ensure the sandbox workspace exists.
settings.WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
