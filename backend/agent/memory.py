"""用户记忆（WB-148）：长期事实的存取、注入对话、以及从对话自动抽取。

- 已存记忆注入 system prompt → 之后对话「记得」用户（真生效）。
- 开启「生成对话记忆」后，每轮结束跑一次性 LLM 抽取，去重入库（默认关：local-first 尊重 API 花费）。
记忆是纯文本用户事实，绝不放密钥/凭据。
"""
from __future__ import annotations

import json

from agent.llm import stream_chat
from storage import db

# user_settings KV 键：是否从对话自动抽取记忆（"1"=开）。默认关。
MEM_CAPTURE_KEY = "pref.memory_capture"
MAX_PER_TURN = 3  # 每轮最多新增几条，避免一次灌太多


def capture_enabled(owner_id: str) -> bool:
    return (db.get_user_setting(owner_id, MEM_CAPTURE_KEY) or "") == "1"


def set_capture_enabled(owner_id: str, on: bool) -> None:
    db.set_user_setting(owner_id, MEM_CAPTURE_KEY, "1" if on else None)


def build_memory_prompt(owner_id: str) -> str:
    """把已存记忆拼成注入 system prompt 的段；无记忆则空串。"""
    mems = db.list_memories(owner_id)
    if not mems:
        return ""
    lines = "\n".join(f"- {m['content']}" for m in mems)
    return (
        "\n\n# 关于用户的记忆\n"
        "以下是你此前记住的、关于该用户的长期事实。作答时自然地纳入考量，不要生硬复述：\n"
        + lines
    )


_EXTRACT_SYS = (
    "你是一个记忆抽取器。从给定的一轮对话里，提炼关于【用户本人】、且长期有效的稳定事实"
    "（如身份/职业、稳定的偏好与习惯、正在做的项目或目标、重要约束）。\n"
    "规则：只提炼明确、稳定、以后仍然有用的；忽略一次性/临时的、与助手或 AI 有关的、"
    "以及从已有记忆已能推出的。每条一句话、精炼、以用户为主语。最多 %d 条。\n"
    '输出严格的 JSON 数组（例如 ["用户是一名前端工程师"]）；没有可记的就输出 []。除 JSON 外不要输出任何内容。'
) % MAX_PER_TURN


def _parse_facts(text: str) -> list[str]:
    """从模型输出里稳妥地抠出字符串数组（容忍 ```json 包裹或前后废话）。"""
    text = (text or "").strip()
    if "```" in text:
        parts = text.split("```")
        if len(parts) > 1:
            text = parts[1]
        text = text[4:].strip() if text.lstrip().lower().startswith("json") else text.strip()
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end > start:
        text = text[start:end + 1]
    try:
        data = json.loads(text)
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(data, list):
        return []
    return [x.strip()[:300] for x in data if isinstance(x, str) and x.strip()]


async def extract_and_store(
    owner_id: str,
    user_text: str,
    assistant_text: str,
    *,
    model: str | None,
    api_base: str | None,
    api_key: str | None,
    chat_path: str,
) -> list[dict]:
    """一次性抽取本轮记忆 → 去重入库。返回新入库的记忆。best-effort：调用方吞异常。"""
    existing = [m["content"] for m in db.list_memories(owner_id)]
    known = (
        "已有记忆（不要重复、不要与之矛盾）：\n" + "\n".join(f"- {c}" for c in existing)
        if existing else "（暂无已有记忆）"
    )
    user_msg = (
        f"{known}\n\n本轮对话：\n用户：{(user_text or '').strip()[:2000]}\n"
        f"助手：{(assistant_text or '').strip()[:2000]}\n\n请按规则抽取。"
    )
    messages = [
        {"role": "system", "content": _EXTRACT_SYS},
        {"role": "user", "content": user_msg},
    ]
    acc = ""
    async for delta in stream_chat(
        messages, model=model, api_base=api_base, api_key=api_key,
        chat_path=chat_path, temperature=0.2,
    ):
        if delta.content:
            acc += delta.content
    stored: list[dict] = []
    for fact in _parse_facts(acc)[:MAX_PER_TURN]:
        row = db.add_memory(owner_id, fact, source="conversation")
        if row:
            stored.append(row)
    return stored
