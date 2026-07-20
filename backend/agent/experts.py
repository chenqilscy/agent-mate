"""Experts = preset personas (M5). Selecting an expert on a project injects its
persona into the system prompt so the agent answers with that role's expertise.

内置人格已从此处的硬编码字典迁到 DB（catalog_experts，WB-059）——`persona_for` 现在**读库**，
种子源见 `storage/catalog_seed.py`。名字与前端选择器（NP_EXPERTS / EXP_GRID）逐字对齐；
库里查不到（未知专家）返回 None，由 runtime 诚实报告未就绪，不再伪装有效果（WB-196）。
"""
from __future__ import annotations

from storage import db


def expert_for(key: str) -> dict[str, str] | None:
    return db.expert_spec_for(key)


def persona_for(name: str) -> str | None:
    spec = expert_for(name)
    return spec["persona"] if spec else None
