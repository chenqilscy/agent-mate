"""智能体行为设置（WB-150）：工具循环步数上限 + 回复发散度(temperature)。

按 owner 存 user_settings KV，run_chat 每轮真读真用。把原来写死的 MAX_ROUNDS/temperature
变成用户可调（真持久化 + 真生效）。只放行为参数，不含任何凭据。
"""
from __future__ import annotations

from storage import db

KEY_MAX_ROUNDS = "agent.max_rounds"
KEY_TEMPERATURE = "agent.temperature"

DEFAULT_MAX_ROUNDS = 12   # 与历史写死值一致
DEFAULT_TEMPERATURE = 0.6
MIN_ROUNDS, MAX_ROUNDS_CAP = 1, 50
MIN_TEMP, MAX_TEMP = 0.0, 2.0


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def get_max_rounds(owner_id: str) -> int:
    v = db.get_user_setting(owner_id, KEY_MAX_ROUNDS)
    if not v:
        return DEFAULT_MAX_ROUNDS
    try:
        return int(_clamp(int(v), MIN_ROUNDS, MAX_ROUNDS_CAP))
    except (ValueError, TypeError):
        return DEFAULT_MAX_ROUNDS


def get_temperature(owner_id: str) -> float:
    v = db.get_user_setting(owner_id, KEY_TEMPERATURE)
    if v is None or v == "":
        return DEFAULT_TEMPERATURE
    try:
        return _clamp(float(v), MIN_TEMP, MAX_TEMP)
    except (ValueError, TypeError):
        return DEFAULT_TEMPERATURE


def get_settings(owner_id: str) -> dict:
    return {
        "max_rounds": get_max_rounds(owner_id),
        "temperature": get_temperature(owner_id),
        "defaults": {"max_rounds": DEFAULT_MAX_ROUNDS, "temperature": DEFAULT_TEMPERATURE},
        "limits": {"max_rounds": [MIN_ROUNDS, MAX_ROUNDS_CAP], "temperature": [MIN_TEMP, MAX_TEMP]},
    }


def set_settings(owner_id: str, *, max_rounds=None, temperature=None) -> None:
    if max_rounds is not None:
        try:
            r = int(_clamp(int(max_rounds), MIN_ROUNDS, MAX_ROUNDS_CAP))
            db.set_user_setting(owner_id, KEY_MAX_ROUNDS, str(r))
        except (ValueError, TypeError):
            pass
    if temperature is not None:
        try:
            t = _clamp(float(temperature), MIN_TEMP, MAX_TEMP)
            db.set_user_setting(owner_id, KEY_TEMPERATURE, str(t))
        except (ValueError, TypeError):
            pass
