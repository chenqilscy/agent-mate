"""Runtime configuration, loaded from backend/.env.

The API key lives here and only here — it is never sent to the frontend
(engineering hard-line: "API Key 只存后端 .env，前端永不接触").
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent

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
    d = base / "WorkBuddy"
    d.mkdir(parents=True, exist_ok=True)
    return d


if FROZEN:
    EXE_DIR = Path(sys.executable).resolve().parent
    DATA_DIR = _user_data_dir()
    # .env next to the exe wins, else the data dir.
    for _env in (EXE_DIR / ".env", DATA_DIR / ".env"):
        if _env.exists():
            load_dotenv(_env)
            break
else:
    DATA_DIR = BACKEND_DIR
    load_dotenv(BACKEND_DIR / ".env")


class Settings:
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "").strip()
    LLM_API_BASE: str = os.getenv("LLM_API_BASE", "https://api.deepseek.com/v1").strip().rstrip("/")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "deepseek-chat").strip()

    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))

    # 知识库改用自托管 WeKnora（WB-173）：后端当 WeKnora 客户端，X-API-Key 打其 REST /api/v1。
    # 只存后端 .env，绝不回前端（铁律#4）。未配 WEKNORA_API_KEY → 知识库接口 400 引导去配置。
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
    # WORKBUDDY_DB overrides the DB path (isolated tests / running a second instance).
    DB_PATH: Path = Path(os.getenv("WORKBUDDY_DB", str(DATA_DIR / "workbuddy.db")))

    WORKSPACE_ROOT: Path = Path(
        os.getenv("WORKBUDDY_WORKSPACE", str(DATA_DIR / "workspace"))
    ).resolve()

    # SkillHub 已安装技能目录（WB-055）。真实安装把 skill 解压到这里，agent 扫描
    # <dir>/*/SKILL.md 加载。与出货版 WorkBuddy 及 skillhub CLI 的默认约定一致。
    SKILLS_DIR: Path = Path(
        os.getenv("WORKBUDDY_SKILLS_DIR", str(Path.home() / ".workbuddy" / "skills"))
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

    # WorkBuddy Hub（中心控制平面，WB-061/062）。HUB_URL 空 = 未接 Hub = 纯本地（离线优先）：
    # 本地 backend 作为 Hub 客户端持 Hub token 调其 /api/auth/verify 等。凭据/工作区文件绝不上云。
    HUB_URL: str = os.getenv("HUB_URL", "").strip().rstrip("/")
    # 团队时间线上报开关（WB-062 Phase 3）。默认关——执行产出默认不上云（隐私，铁律 4）。
    HUB_TIMELINE_UPLOAD: bool = os.getenv("HUB_TIMELINE_UPLOAD", "0").strip().lower() in ("1", "true", "yes")

    @property
    def llm_configured(self) -> bool:
        return bool(self.LLM_API_KEY)

    @property
    def hub_enabled(self) -> bool:
        return bool(self.HUB_URL)

    @property
    def telegram_assistant_enabled(self) -> bool:
        # 需同时有 bot token 且显式开开关，才启动 Telegram 助理桥接（WB-072）。
        return bool(self.TELEGRAM_BOT_TOKEN) and self.TELEGRAM_ASSISTANT


settings = Settings()

# Ensure the sandbox workspace exists.
settings.WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
