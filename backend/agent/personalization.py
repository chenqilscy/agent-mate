"""个性化偏好（WB-147）：回复风格预设 + 自定义指令。

存 `user_settings` KV（按 owner），在 `run_chat` 组装系统提示时注入 → 真生效于所有对话
（对齐高保真原型「设置 · 个性化」）。密钥/凭据类绝不进这里，只放纯偏好文本。
"""
from __future__ import annotations

from storage import db

# user_settings 表里的键
PREF_STYLE = "pref.style"
PREF_CUSTOM = "pref.custom_instructions"

# 自定义指令长度上限（防止把超长文本塞进每轮系统提示）
CUSTOM_MAX = 2000

# 回复风格预设：key -> 展示信息(label/desc) + 注入提示(prompt)。对齐原型「基本风格和语调」8 档。
# 'default' 不注入任何风格（prompt 空）。
STYLE_PRESETS: list[dict] = [
    {"key": "default", "label": "默认", "desc": "不设定特定风格", "prompt": ""},
    {"key": "professional", "label": "专业严谨", "desc": "清晰、准确、值得信赖",
     "prompt": "以专业严谨的口吻作答：表达清晰准确、用词稳重、结论可靠可信赖。"},
    {"key": "friendly", "label": "亲和友善", "desc": "温暖、平易近人、鼓励支持",
     "prompt": "以亲和友善的口吻作答：温暖、平易近人，适时给予鼓励与支持。"},
    {"key": "blunt", "label": "直言不讳", "desc": "简明扼要、不废话、直击要点",
     "prompt": "直言不讳：简明扼要、不说废话、直击要点。"},
    {"key": "imaginative", "label": "天马行空", "desc": "富有想象力、善用比喻类比",
     "prompt": "回答富有想象力，善用比喻和类比，把抽象的东西讲得生动。"},
    {"key": "efficient", "label": "高效务实", "desc": "最少文字、最大信息量",
     "prompt": "高效务实：用最少的文字给出最大信息量，优先给可执行的结论。"},
    {"key": "snarky", "label": "毒舌吐槽", "desc": "犀利吐槽、但绝不伤人",
     "prompt": "语气犀利、带点吐槽和幽默，但对事不对人，绝不冒犯或伤害用户。"},
    {"key": "socratic", "label": "启发引导", "desc": "用提问引导思考、授人以渔",
     "prompt": "多用启发式提问引导用户自己思考，授人以渔；但用户明确要结论时照常直接给。"},
]
_PRESET_BY_KEY = {p["key"]: p for p in STYLE_PRESETS}
PRESET_KEYS = set(_PRESET_BY_KEY)


def get_personalization(owner_id: str) -> dict:
    """当前偏好（供 GET /api/settings 回显；不含任何密钥）。"""
    return {
        "style": db.get_user_setting(owner_id, PREF_STYLE) or "default",
        "custom_instructions": db.get_user_setting(owner_id, PREF_CUSTOM) or "",
    }


def build_personalization_prompt(owner_id: str) -> str:
    """拼出注入 system prompt 的「# 个性化偏好」段；无任何偏好则返回空串。"""
    parts: list[str] = []
    style = db.get_user_setting(owner_id, PREF_STYLE) or "default"
    sp = _PRESET_BY_KEY.get(style, {}).get("prompt", "")
    if sp:
        parts.append("## 回复风格\n" + sp)
    custom = (db.get_user_setting(owner_id, PREF_CUSTOM) or "").strip()
    if custom:
        parts.append("## 用户自定义指令（始终遵循，除非与安全或事实冲突）\n" + custom)
    if not parts:
        return ""
    return "\n\n# 个性化偏好\n" + "\n\n".join(parts)
