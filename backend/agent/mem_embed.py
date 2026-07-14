"""本地嵌入 provider（WB-167 认知记忆 档二）。

懒加载 fastembed（ONNX runtime，默认 `BAAI/bge-small-zh-v1.5`，离线、CPU、零 API 成本），
把记忆文本 → 向量做语义去重/更替/相关性检索。仿 WB-139 ASR：**可选依赖、懒加载单例、没装/不可用则
`embed` 返回 None** → 调用方回退档一（非语义强度排序）。向量以 float32 bytes 存 user_memories.embedding。
首次使用会下载模型到缓存（需联网一次）。
"""
from __future__ import annotations

import os
import threading
from typing import Optional

import numpy as np

_MODEL_NAME = os.getenv("MEM_EMBED_MODEL", "BAAI/bge-small-zh-v1.5")

_lock = threading.Lock()
_model = None
_unavailable = False  # 一旦确认没装/加载失败就置真，之后不再反复尝试


def _get_model():
    """懒加载嵌入模型单例；没装 fastembed 或加载失败 → 返回 None 并记为不可用。"""
    global _model, _unavailable
    if _model is not None or _unavailable:
        return _model
    with _lock:
        if _model is not None or _unavailable:
            return _model
        try:
            from fastembed import TextEmbedding  # 可选依赖
            _model = TextEmbedding(model_name=_MODEL_NAME)
        except Exception:  # noqa: BLE001 —— 没装/模型下载失败/onnx 不可用等，一律诚实降级
            _unavailable = True
            _model = None
        return _model


def available() -> bool:
    """本地嵌入是否可用（模型能加载）。"""
    return _get_model() is not None


def embed(text: str) -> Optional[list[float]]:
    """文本 → 归一化向量（list[float]）；不可用或空文本 → None。"""
    text = (text or "").strip()
    if not text:
        return None
    m = _get_model()
    if m is None:
        return None
    try:
        vec = next(iter(m.embed([text])))
        return [float(x) for x in vec]
    except Exception:  # noqa: BLE001
        return None


def to_blob(vec) -> bytes:
    """向量 → float32 bytes（存 DB BLOB）。"""
    return np.asarray(vec, dtype=np.float32).tobytes()


def from_blob(b) -> Optional[np.ndarray]:
    """float32 bytes → np 向量；空 → None。"""
    if not b:
        return None
    return np.frombuffer(b, dtype=np.float32)


def cosine(a: Optional[np.ndarray], b: Optional[np.ndarray]) -> float:
    """余弦相似度；任一为空/维度不匹配 → 0。"""
    if a is None or b is None or a.size == 0 or b.size == 0 or a.size != b.size:
        return 0.0
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))
