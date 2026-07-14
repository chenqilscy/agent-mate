"""记忆强度/衰减/检索打分（纯函数，便于单测）。WB-166 认知记忆 档一。

参考 AgentOS `packages/core/src/memory/decay.ts`：
strength = importance × recency(指数半衰期) × usageBoost(对数强化)；检索得分 = 相似度 × strength。
"""
from __future__ import annotations

import math

_DAY_MS = 24 * 60 * 60 * 1000
DEFAULT_HALF_LIFE_MS = 7 * _DAY_MS  # 默认半衰期 7 天
ARCHIVE_THRESHOLD = 0.05           # 强度低于此则归档（GC）


def _clamp01(x: float) -> float:
    return min(1.0, max(0.0, x))


def recency_weight(age_ms: float, half_life_ms: float = DEFAULT_HALF_LIFE_MS) -> float:
    """遗忘曲线：按半衰期指数衰减。age=0 → 1，age=半衰期 → 0.5。"""
    if age_ms <= 0:
        return 1.0
    return math.pow(0.5, age_ms / half_life_ms)


def usage_boost(usage_count: int) -> float:
    """使用强化系数：命中越多越强，但收益递减（对数）。"""
    return 1.0 + math.log1p(max(0, usage_count)) * 0.2


def compute_strength(
    importance: float,
    age_ms: float,
    usage_count: int,
    half_life_ms: float = DEFAULT_HALF_LIFE_MS,
) -> float:
    """记忆当前强度 ∈ [0,1]：importance×recency 定基线，usage 做有上限的强化。"""
    base = _clamp01(importance) * recency_weight(age_ms, half_life_ms)
    return _clamp01(base * usage_boost(usage_count))


def retrieval_score(similarity: float, strength: float) -> float:
    """检索综合得分 = 相似度 × 强度。"""
    return _clamp01(similarity) * _clamp01(strength)


def should_archive(strength: float, threshold: float = ARCHIVE_THRESHOLD) -> bool:
    """强度低于阈值则归档（GC）。"""
    return strength < threshold
