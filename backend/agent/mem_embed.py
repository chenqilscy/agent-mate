"""记忆嵌入 provider（WB-167 本地；WB-170 本地⇄在线可配置）。

两套向量模型，按 owner 的设置 `pref.embed_backend` 选：
- **local**（默认，local-first）：fastembed（ONNX，`BAAI/bge-small-zh-v1.5`，512 维，离线零成本）。
- **glm**（在线）：GLM `/api/paas/v4/embeddings`，model `embedding-3`（2048 维），key 用 `db.get_provider_key(owner,"zhipu")`
  （与知识库同源，绝不回前端）。没装 fastembed / 没配 GLM key / 请求失败 → 该后端不可用。

跨模型余弦无意义：每条向量存 `model_tag`（如 `local:bge-small-zh-v1.5` / `glm:embedding-3`），
检索/去重只比对同 tag；切后端后旧 tag 向量由调用方重嵌入回填。`embed` 全部 owner-aware。
仿 WB-139 ASR：可选依赖、懒加载、不可用则诚实降级（返回 None）→ 记忆退回档一非语义。
"""
from __future__ import annotations

import os
import threading
from typing import Optional

import httpx
import numpy as np

from storage import db

EMBED_BACKEND_KEY = "pref.embed_backend"  # user_setting：'local' | 'glm'，默认 local

_LOCAL_MODEL = os.getenv("MEM_EMBED_MODEL", "BAAI/bge-small-zh-v1.5")
_GLM_MODEL = os.getenv("MEM_EMBED_GLM_MODEL", "embedding-3")
_GLM_URL = os.getenv("MEM_EMBED_GLM_URL", "https://open.bigmodel.cn/api/paas/v4/embeddings")
_GLM_PROVIDER = "zhipu"

_lock = threading.Lock()
_model = None
_local_unavailable = False


def _model_downloads_disabled() -> bool:
    return os.getenv("AGENTMATE_DISABLE_EMBED_MODEL_DOWNLOAD", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


# ---- 本地后端（fastembed）------------------------------------------------

def _local_model():
    global _model, _local_unavailable
    if _model_downloads_disabled():
        return None
    if _model is not None or _local_unavailable:
        return _model
    with _lock:
        if _model is not None or _local_unavailable:
            return _model
        try:
            from fastembed import TextEmbedding  # 可选依赖
            _model = TextEmbedding(model_name=_LOCAL_MODEL)
        except Exception:  # noqa: BLE001 —— 没装/下载失败/onnx 不可用等
            _local_unavailable = True
            _model = None
        return _model


def local_available() -> bool:
    return _local_model() is not None


def _local_embed_batch(texts: list[str]) -> Optional[list[list[float]]]:
    m = _local_model()
    if m is None:
        return None
    try:
        return [[float(x) for x in v] for v in m.embed(texts)]
    except Exception:  # noqa: BLE001
        return None


# ---- 在线后端（GLM embedding-3）------------------------------------------

def _glm_key(owner_id: str) -> Optional[str]:
    return db.get_provider_key(owner_id, _GLM_PROVIDER)


def glm_available(owner_id: str) -> bool:
    return bool(_glm_key(owner_id))


def _glm_embed_batch(owner_id: str, texts: list[str]) -> Optional[list[list[float]]]:
    key = _glm_key(owner_id)
    if not key:
        return None
    try:
        r = httpx.post(
            _GLM_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": _GLM_MODEL, "input": texts},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json().get("data", [])
        rows = sorted(data, key=lambda x: x.get("index", 0))
        vecs = [row.get("embedding") for row in rows]
        return vecs if all(isinstance(v, list) and v for v in vecs) and len(vecs) == len(texts) else None
    except Exception:  # noqa: BLE001 —— 网络/鉴权/配额/格式等，一律诚实降级
        return None


# ---- 后端选择 + 对外 API --------------------------------------------------

def configured_backend(owner_id: str) -> str:
    return (db.get_user_setting(owner_id, EMBED_BACKEND_KEY) or "local").strip() or "local"


def set_backend(owner_id: str, backend: str) -> None:
    db.set_user_setting(owner_id, EMBED_BACKEND_KEY, backend if backend in ("local", "glm") else None)


def active_backend(owner_id: str) -> Optional[str]:
    """当前实际生效的后端：优先用户所选（若可用），否则回退另一个可用后端，都不可用则 None。"""
    cfg = configured_backend(owner_id)
    if cfg == "glm" and glm_available(owner_id):
        return "glm"
    if cfg == "local" and local_available():
        return "local"
    # 所选不可用 → 回退另一个可用的（尽量让语义仍工作）
    if local_available():
        return "local"
    if glm_available(owner_id):
        return "glm"
    return None


def model_tag(owner_id: str) -> Optional[str]:
    b = active_backend(owner_id)
    if b == "glm":
        return f"glm:{_GLM_MODEL}"
    if b == "local":
        return f"local:{_LOCAL_MODEL.split('/')[-1]}"
    return None


def available(owner_id: str) -> bool:
    return active_backend(owner_id) is not None


def backends_status(owner_id: str) -> dict:
    """供 UI：所配后端 / 实际生效后端 / 各后端可用性。"""
    return {
        "configured": configured_backend(owner_id),
        "active": active_backend(owner_id),
        "local": local_available(),
        "glm": glm_available(owner_id),
    }


def embed_batch(owner_id: str, texts: list[str]) -> Optional[list[list[float]]]:
    """按当前生效后端批量嵌入；不可用/失败 → None。"""
    texts = [t for t in (texts or [])]
    if not texts:
        return []
    b = active_backend(owner_id)
    if b == "glm":
        return _glm_embed_batch(owner_id, texts)
    if b == "local":
        return _local_embed_batch(texts)
    return None


def embed(owner_id: str, text: str) -> Optional[list[float]]:
    """按当前生效后端嵌入单条文本；不可用/空 → None。"""
    text = (text or "").strip()
    if not text:
        return None
    out = embed_batch(owner_id, [text])
    return out[0] if out else None


# ---- 向量工具 -------------------------------------------------------------

def to_blob(vec) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def from_blob(b) -> Optional[np.ndarray]:
    if not b:
        return None
    return np.frombuffer(b, dtype=np.float32)


def cosine(a: Optional[np.ndarray], b: Optional[np.ndarray]) -> float:
    """余弦相似度；任一为空/维度不匹配 → 0（跨模型维度不同自然不比对）。"""
    if a is None or b is None or a.size == 0 or b.size == 0 or a.size != b.size:
        return 0.0
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))
