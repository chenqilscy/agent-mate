"""Model menu (spec 5.1 GET /api/models).

Drives the model picker (multiplier / level / custom group). The names mirror the
prototype menu; the *effective* model that actually runs is `LLM_MODEL` from .env
— the picker is a UI affordance until multi-routing (litellm) lands in M2+.
"""
from __future__ import annotations

from fastapi import APIRouter

from config import settings

router = APIRouter(prefix="/api", tags=["models"])

# [icon, color, name, level, mult, off]
_BUILTIN = [
    ["A", "#3B4048", "Auto", "High", "", ""],
    ["H", "#1B74E4", "Hy3 preview", "High", "0.04x", "限时折扣"],
    ["Z", "#17181C", "GLM-5.2", "Medium", "0.79x", ""],
    ["Z", "#17181C", "GLM-5.1", "Medium", "0.79x", ""],
    ["M", "#E5484D", "MiniMax-M3", "Medium", "0.25x", ""],
    ["K", "#17181C", "Kimi-K2.7-Code", "Medium", "0.57x", ""],
    ["🐋", "", "Deepseek-V4-Flash", "High", "0.06x", ""],
    ["🐋", "", "Deepseek-V4-Pro", "High", "0.16x", ""],
]

_CUSTOM = [
    ["🐋", "", "DeepSeek-V4 Flash:deepseek-v4-flash", "High", "", ""],
    ["🐋", "", "DeepSeek-V4 Pro:deepseek-v4-pro", "High", "", ""],
]


def _pack(rows: list[list[str]], group: str) -> list[dict]:
    return [
        {
            "icon": r[0],
            "color": r[1],
            "name": r[2],
            "level": r[3],
            "mult": r[4],
            "off": r[5],
            "group": group,
        }
        for r in rows
    ]


@router.get("/models")
def list_models() -> dict:
    models = _pack(_BUILTIN, "builtin") + _pack(_CUSTOM, "custom")
    # Default the picker to whichever entry resolves to the configured .env model
    # (so what's shown = what runs); fall back to the raw model id otherwise.
    default = next(
        (m["name"] for m in models if m["name"].endswith(":" + settings.LLM_MODEL)),
        settings.LLM_MODEL,
    )
    return {"default": default, "effective": settings.LLM_MODEL, "models": models}
