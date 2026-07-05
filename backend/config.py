"""Runtime configuration, loaded from backend/.env.

The API key lives here and only here — it is never sent to the frontend
(engineering hard-line: "API Key 只存后端 .env，前端永不接触").
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent

# Load backend/.env if present (falls back to real env vars otherwise).
load_dotenv(BACKEND_DIR / ".env")


class Settings:
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "").strip()
    LLM_API_BASE: str = os.getenv("LLM_API_BASE", "https://api.deepseek.com/v1").strip().rstrip("/")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "deepseek-chat").strip()

    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))

    DB_PATH: Path = BACKEND_DIR / "workbuddy.db"

    WORKSPACE_ROOT: Path = Path(
        os.getenv("WORKBUDDY_WORKSPACE", str(BACKEND_DIR / "workspace"))
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
