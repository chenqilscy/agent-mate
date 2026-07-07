"""Experts = preset personas (M5). Selecting an expert on a project injects its
persona into the system prompt so the agent answers with that role's expertise.

内置人格已从此处的硬编码字典迁到 DB（catalog_experts，WB-059）——`persona_for` 现在**读库**，
种子源见 `storage/catalog_seed.py`。名字与前端选择器（NP_EXPERTS / EXP_GRID）逐字对齐；
库里查不到（未知专家）则回退通用人格，保证每个目录专家仍有效果。
"""
from __future__ import annotations

from storage import db


def persona_for(name: str) -> str:
    persona = db.builtin_persona(name)
    return persona if persona else f"以「{name}」的专业身份与专长作答。"
