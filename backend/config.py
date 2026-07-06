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

    # Optional connector credentials. Read straight from os.environ by the MCP
    # client's per-connector secret_env (mcp_client.py); listed here for
    # discoverability. Forwarded ONLY to the owning connector's subprocess.
    GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "").strip()
    # Telegram connector (built-in mcp_servers/telegram.py, read at call time).
    # TELEGRAM_CHAT_ID is an optional default target for send_message.
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    # 金山文档 connector (built-in mcp_servers/kdocs.py, shells out to kdocs-cli,
    # read at call time). A WPS 云文档 token; the CLI can also use its own keychain.
    KDOCS_TOKEN: str = os.getenv("KDOCS_TOKEN", "").strip()

    # DB + workspace live in DATA_DIR (backend/ in dev, per-user data dir when frozen).
    # WORKBUDDY_DB overrides the DB path (isolated tests / running a second instance).
    DB_PATH: Path = Path(os.getenv("WORKBUDDY_DB", str(DATA_DIR / "workbuddy.db")))

    WORKSPACE_ROOT: Path = Path(
        os.getenv("WORKBUDDY_WORKSPACE", str(DATA_DIR / "workspace"))
    ).resolve()

    # Context window used to compute the context-usage ring (approximate).
    # Clamped to >=1 so a misconfigured CONTEXT_WINDOW=0 can't divide-by-zero
    # at the end of a stream (WB-022).
    CONTEXT_WINDOW: int = max(1, int(os.getenv("CONTEXT_WINDOW", "1000000")))

    @property
    def llm_configured(self) -> bool:
        return bool(self.LLM_API_KEY)


settings = Settings()

# Ensure the sandbox workspace exists.
settings.WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
