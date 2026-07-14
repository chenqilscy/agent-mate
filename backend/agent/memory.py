"""用户记忆（WB-148；机制优化 WB-162；认知记忆 WB-166/167 参考 AgentOS）。

长期事实的存取、注入对话、从对话自动抽取。核心机制：
- **强度**：每条记忆有 strength = importance × recency(指数衰减) × usage(对数强化)，见 mem_decay。
- **注入**：active 记忆按强度排序、取字符预算内 top-N 注入 system prompt，**命中即强化**（档二 WB-167 起改为
  按当前对话语义相关性检索）。
- **抽取**：开启后每轮跑一次性 LLM 抽取，产出结构化操作（add 新增 / update 更替）；update 走 **supersede**
  （旧记忆软置 superseded、留 superseded_by 链，不原地覆盖）。默认关：local-first 尊重 API 花费。
- **衰退 GC**：强度低于阈值的记忆软归档（archived），不硬删，可回滚。
记忆是纯文本用户事实，绝不放密钥/凭据。
"""
from __future__ import annotations

import json
import time

import numpy as np

from agent import mem_embed
from agent.llm import stream_chat
from agent.mem_decay import compute_strength, retrieval_score, should_archive
from storage import db

# user_settings KV 键：是否从对话自动抽取记忆（"1"=开）。默认关。
MEM_CAPTURE_KEY = "pref.memory_capture"
MAX_PER_TURN = 3        # 每轮最多几个操作，避免一次灌太多
INJECT_CHAR_BUDGET = 1500   # 注入 system prompt 的记忆总字符预算，防随库增长无界膨胀
EXTRACT_CTX_BUDGET = 1500   # 回喂抽取器的「已有记忆」上下文字符预算
# 语义阈值（档二 WB-167，参考 AgentOS）：≥DEDUPE 且同文→强化既有；≥CONFLICT 且异文→插新+旧 supersede。
DEDUPE_THRESHOLD = 0.98
CONFLICT_THRESHOLD = 0.90
EMBED_BACKFILL_CAP = 64     # 单次注入最多给几条缺 embedding 的旧记忆补嵌入（一次性、持久化）


def capture_enabled(owner_id: str) -> bool:
    return (db.get_user_setting(owner_id, MEM_CAPTURE_KEY) or "") == "1"


def set_capture_enabled(owner_id: str, on: bool) -> None:
    db.set_user_setting(owner_id, MEM_CAPTURE_KEY, "1" if on else None)


# ---- 强度与预算 -----------------------------------------------------------

def _strength_of(m: dict, now_s: float) -> float:
    """一条记忆的当前强度。recency 以「最近一次使用」为基准（回退创建时间）：常用旧记忆不被误衰减。"""
    basis_s = max(m["created_at"], m.get("last_used_at") or m["created_at"])
    age_ms = max(0.0, (now_s - basis_s) * 1000.0)
    return compute_strength(m.get("importance", 0.5), age_ms, m.get("usage_count", 0) or 0)


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


def _rank_by_strength(mems: list[dict], now_s: float) -> list[dict]:
    """按强度降序（稳定：同分保持原顺序，即 created_at DESC）。"""
    return sorted(mems, key=lambda m: _strength_of(m, now_s), reverse=True)


def _ensure_embeddings(owner_id: str, mems: list[dict], cap: int = EMBED_BACKFILL_CAP) -> None:
    """给缺 embedding 的 active 记忆补嵌入（持久化、一次性）；就地写回 mems 的 'embedding'。
    仅在本地嵌入可用时调用。有上限，避免一次补太多拖住注入。"""
    changed = 0
    for m in mems:
        if m.get("embedding") or changed >= cap:
            continue
        vec = mem_embed.embed(m.get("content") or "")
        if vec is not None:
            blob = mem_embed.to_blob(vec)
            db.set_memory_embedding(owner_id, m["id"], blob)
            m["embedding"] = blob
            changed += 1


def _rank_by_relevance(owner_id: str, mems: list[dict], qvec: list[float], now_s: float) -> list[dict]:
    """按 retrieval_score(相似度, 强度) 降序（档二）。mems 需含 'embedding' bytes。"""
    _ensure_embeddings(owner_id, mems)
    qa = np.asarray(qvec, dtype=np.float32)
    scored = []
    for m in mems:
        mv = mem_embed.from_blob(m.get("embedding"))
        sim = mem_embed.cosine(qa, mv) if mv is not None else 0.0
        scored.append((retrieval_score(sim, _strength_of(m, now_s)), m))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored]


def build_memory_prompt(owner_id: str, query_text: str | None = None) -> str:
    """把已存记忆拼成注入 system prompt 的段；无记忆则空串。

    档二（WB-167）：本地嵌入可用且有 query_text → embed(当前对话) → 按 相似度×强度 取相关性 top-N。
    档一回退：按强度排序取 top-N。两者都取字符预算内、并**命中强化**。
    """
    now_s = time.time()
    qvec = mem_embed.embed(query_text) if query_text else None
    if qvec is not None:
        mems = db.list_active_with_embedding(owner_id)
        if not mems:
            return ""
        ranked = _rank_by_relevance(owner_id, mems, qvec, now_s)
    else:
        mems = db.list_memories(owner_id)  # active，created_at DESC
        if not mems:
            return ""
        ranked = _rank_by_strength(mems, now_s)
    picked, omitted = _within_budget(ranked, INJECT_CHAR_BUDGET)
    if not picked:
        return ""
    for m in picked:  # 命中强化：被注入即视为「用到」，refresh usage/last_used
        db.reinforce_memory(owner_id, m["id"], now_s)
    lines = "\n".join(f"- {(m['content'] or '').strip()}" for m in picked)
    tail = f"\n（另有 {omitted} 条较弱/不相关记忆已省略）" if omitted > 0 else ""
    return (
        "\n\n# 关于用户的记忆\n"
        "以下是你此前记住的、关于该用户的长期事实。作答时自然地纳入考量，不要生硬复述：\n"
        + lines + tail
    )


# ---- 落库（去重/强化/更替）------------------------------------------------

def store_memory(owner_id: str, content: str, source: str, importance: float = 0.5) -> dict | None:
    """落库一条记忆。

    档二（本地嵌入可用）：embed(content) → 与 active 记忆取最相似一条。
      ≥DEDUPE 且同文 → 强化既有并返回；≥CONFLICT 且异文 → 插新 + 旧 supersede（自动更替）；否则纯插入。
    档一回退（无嵌入）：精确字符串去重 → 命中强化 / 否则插入。
    """
    text = (content or "").strip()
    if not text:
        return None
    vec = mem_embed.embed(text)
    if vec is None:  # 档一回退
        dup = db.find_active_memory_by_content(owner_id, text)
        if dup is not None:
            return db.reinforce_memory(owner_id, dup["id"])
        return db.insert_memory(owner_id, text, source, importance)

    # 档二语义路径
    qa = np.asarray(vec, dtype=np.float32)
    actives = db.list_active_with_embedding(owner_id)
    _ensure_embeddings(owner_id, actives)
    best, best_sim = None, -1.0
    for m in actives:
        mv = mem_embed.from_blob(m.get("embedding"))
        if mv is None:
            continue
        sim = mem_embed.cosine(qa, mv)
        if sim > best_sim:
            best, best_sim = m, sim
    # 完全重复（语义极高 + 同文）→ 强化既有
    if best is not None and best_sim >= DEDUPE_THRESHOLD and (best["content"] or "").strip() == text:
        return db.reinforce_memory(owner_id, best["id"])
    new = db.insert_memory(owner_id, text, source, importance, embedding=mem_embed.to_blob(vec))
    # 语义高度相近但异文 → 自动更替：旧记忆软置 superseded（留链）
    if best is not None and best_sim >= CONFLICT_THRESHOLD and (best["content"] or "").strip() != text:
        db.supersede_memory(owner_id, best["id"], new["id"])
    return new


def decay_gc(owner_id: str) -> int:
    """衰退 GC：强度低于阈值的 active 记忆软归档（archived，不硬删）。返回归档数。best-effort。"""
    now_s = time.time()
    archived = 0
    for m in db.list_memories(owner_id, limit=10**9):  # 全部 active
        if should_archive(_strength_of(m, now_s)):
            db.set_memory_status(owner_id, m["id"], "archived")
            archived += 1
    return archived


# ---- 从对话抽取（结构化操作 add / update→supersede）-----------------------

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
    """一次性抽取本轮记忆 → 结构化操作（add / update→supersede）入库。返回本轮实际变更的记忆。
    best-effort：调用方吞异常。"""
    # 回喂抽取器的「已有记忆」按强度排序 + 预算截断并编号；ctx 序号(1-based) ↔ 记忆 用于 update 定位。
    now_s = time.time()
    ctx, _ = _within_budget(_rank_by_strength(db.list_memories(owner_id), now_s), EXTRACT_CTX_BUDGET)
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
        row = store_memory(owner_id, op["content"], "conversation")
        if row is None:
            continue
        if op["op"] == "update":
            idx = op["ref"] - 1
            old = ctx[idx] if 0 <= idx < len(ctx) else None
            # 新记忆更替旧记忆：旧的软置 superseded（留链）。同一条（内容没变→dedup 回既有）则不 supersede。
            if old and old["id"] != row["id"] and row.get("status") == "active":
                db.supersede_memory(owner_id, old["id"], row["id"])
        stored.append(row)
    return stored
