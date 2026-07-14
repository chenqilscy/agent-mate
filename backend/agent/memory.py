"""用户记忆（WB-148；机制优化 WB-162）：长期事实的存取、注入对话、以及从对话自动抽取。

- 已存记忆注入 system prompt → 之后对话「记得」用户（真生效）。注入**按预算**取（手动优先+最近优先），
  避免随记忆数无界膨胀（WB-162）。
- 开启「生成对话记忆」后，每轮结束跑一次性 LLM 抽取，产出**结构化操作**（add 新增 / update 更替过时·矛盾的
  某条既有记忆），去重入库（默认关：local-first 尊重 API 花费）。回喂抽取器的「已有记忆」上下文也按预算截断。
记忆是纯文本用户事实，绝不放密钥/凭据。
"""
from __future__ import annotations

import json

from agent.llm import stream_chat
from storage import db

# user_settings KV 键：是否从对话自动抽取记忆（"1"=开）。默认关。
MEM_CAPTURE_KEY = "pref.memory_capture"
MAX_PER_TURN = 3        # 每轮最多几个操作，避免一次灌太多
INJECT_CHAR_BUDGET = 1500   # 注入 system prompt 的记忆总字符预算，防随库增长无界膨胀（WB-162）
EXTRACT_CTX_BUDGET = 1500   # 回喂抽取器的「已有记忆」上下文字符预算（同理，抽取输入也不该无界）


def capture_enabled(owner_id: str) -> bool:
    return (db.get_user_setting(owner_id, MEM_CAPTURE_KEY) or "") == "1"


def set_capture_enabled(owner_id: str, on: bool) -> None:
    db.set_user_setting(owner_id, MEM_CAPTURE_KEY, "1" if on else None)


def _prioritize(mems: list[dict]) -> list[dict]:
    """注入/回喂优先级：手动记忆优先，其次按最近（mems 已按 created_at DESC）。稳定、无随机。"""
    manual = [m for m in mems if m.get("source") == "manual"]
    convo = [m for m in mems if m.get("source") != "manual"]
    return manual + convo


def _within_budget(mems: list[dict], budget: int) -> tuple[list[dict], int]:
    """按字符预算贪心取前若干条（保证至少取 1 条，除非其自身空）。返回 (选中, 省略条数)。"""
    picked: list[dict] = []
    used = 0
    for m in mems:
        c = (m.get("content") or "").strip()
        if not c:
            continue
        cost = len(c) + 3  # "- " 前缀 + 换行的粗略计入
        if picked and used + cost > budget:
            break
        picked.append(m)
        used += cost
    return picked, len(mems) - len(picked)


def build_memory_prompt(owner_id: str) -> str:
    """把已存记忆拼成注入 system prompt 的段；无记忆则空串。按预算取（手动优先+最近优先），超预算截断并注明。"""
    mems = db.list_memories(owner_id)
    if not mems:
        return ""
    picked, omitted = _within_budget(_prioritize(mems), INJECT_CHAR_BUDGET)
    if not picked:
        return ""
    lines = "\n".join(f"- {(m['content'] or '').strip()}" for m in picked)
    tail = f"\n（另有 {omitted} 条较早记忆已省略）" if omitted > 0 else ""
    return (
        "\n\n# 关于用户的记忆\n"
        "以下是你此前记住的、关于该用户的长期事实。作答时自然地纳入考量，不要生硬复述：\n"
        + lines + tail
    )


_EXTRACT_SYS = (
    "你是一个记忆抽取器。从给定的一轮对话里，提炼关于【用户本人】、且长期有效的稳定事实"
    "（如身份/职业、稳定的偏好与习惯、正在做的项目或目标、重要约束）。\n"
    "你会看到一份带序号的【已有记忆】。请输出对记忆库的操作数组，规则：\n"
    '- 全新的稳定事实 → {"op":"add","content":"…"}\n'
    "- 若本轮更新/纠正/更替了某条已有记忆（如项目、职业、偏好变了，或把旧表述说得更准确）→ "
    '{"op":"update","ref":<该条序号>,"content":"<更替后的新表述>"}；ref 必须是已有记忆里真实存在的序号。\n'
    "- 只提炼明确、稳定、以后仍有用的；忽略一次性/临时的、与助手或 AI 有关的、以及已有记忆已能推出的（不要重复 add）。\n"
    "- 每条 content 一句话、精炼、以用户为主语。最多 %d 个操作。\n"
    '输出严格的 JSON 数组，例如 [{"op":"add","content":"用户是一名前端工程师"}]；'
    "没有可记的就输出 []。除 JSON 外不要输出任何内容。"
) % MAX_PER_TURN


def _parse_ops(text: str) -> list[dict]:
    """从模型输出稳妥抠出操作数组 [{op:'add'|'update', ref?:int, content:str}]（容忍 ```json 包裹或前后废话、
    容忍模型偷懒直接给字符串数组 → 当 add）。"""
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
    ops: list[dict] = []
    for x in data:
        if isinstance(x, str):  # 兼容旧式纯字符串数组
            c = x.strip()[:300]
            if c:
                ops.append({"op": "add", "content": c})
            continue
        if not isinstance(x, dict):
            continue
        content = str(x.get("content") or "").strip()[:300]
        if not content:
            continue
        if x.get("op") == "update":
            try:
                ops.append({"op": "update", "ref": int(x.get("ref")), "content": content})
            except (TypeError, ValueError):
                ops.append({"op": "add", "content": content})  # ref 不合法 → 退化为 add
        else:
            ops.append({"op": "add", "content": content})
    return ops


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
    """一次性抽取本轮记忆 → 结构化操作（add/update）入库。返回本轮实际变更的记忆。
    best-effort：调用方吞异常。"""
    # 回喂抽取器的「已有记忆」按预算截断并编号；ctx 的序号(1-based) ↔ 记忆 用于 update 定位。
    ctx, _ = _within_budget(_prioritize(db.list_memories(owner_id)), EXTRACT_CTX_BUDGET)
    if ctx:
        known_lines = "\n".join(f"{i + 1}. {(m['content'] or '').strip()}" for i, m in enumerate(ctx))
        known = "已有记忆（带序号，据此判断是新增还是更替；不要重复 add 已有事实）：\n" + known_lines
    else:
        known = "（暂无已有记忆）"
    user_msg = (
        f"{known}\n\n本轮对话：\n用户：{(user_text or '').strip()[:2000]}\n"
        f"助手：{(assistant_text or '').strip()[:2000]}\n\n请按规则输出操作数组。"
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
    for op in _parse_ops(acc)[:MAX_PER_TURN]:
        if op["op"] == "update":
            idx = op["ref"] - 1
            if 0 <= idx < len(ctx):
                row = db.update_memory(owner_id, ctx[idx]["id"], op["content"])
                if row:
                    stored.append(row)
                    continue
            # ref 越界 / 更替被去重守卫挡下 → 退化为 add（下方）
        row = db.add_memory(owner_id, op["content"], source="conversation")
        if row:
            stored.append(row)
    return stored
