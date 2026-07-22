"""语音输入本地转写（WB-139）—— faster-whisper 小模型跑在本机。

按住麦克风录一段音频（浏览器 MediaRecorder，webm/opus），松开 POST 到
`/api/asr/transcribe`，本机 faster-whisper 转成文字返回。音频不出本机（local-first）。

铁律#1（不模拟）：依赖没装 / 模型没就绪时端点**诚实** 503，绝不返回假文本。
`GET /api/asr/status` 让前端提前知道能不能用，把麦克风按钮显示成可用/不可用。

- 模型懒加载一次、进程内单例（首次调用才加载，避免拖慢启动 / 不用语音的用户零开销）。
- 加载与转写都是 CPU 阻塞活，一律 `asyncio.to_thread` 丢线程池，绝不阻塞事件循环（WB-002 教训）。
- 解码走 faster-whisper 内置 PyAV（ctranslate2 依赖里自带的 av），webm/opus 直解，无需外部 ffmpeg。
"""
from __future__ import annotations

import asyncio
import io
import threading

from fastapi import APIRouter, HTTPException, Request

from config import settings

router = APIRouter(prefix="/api/asr", tags=["asr"])

# 音频体上限（与全局 8MB JSON 上限一致）。按住说话的语音条只有几秒、opus 极小，够用有余。
MAX_AUDIO = 8 * 1024 * 1024

# 进程内单例：模型对象 + 加载错误原因 + 一把锁（并发首帧只加载一次）。
_model = None
_load_error: str | None = None
_load_lock = threading.Lock()


def reset_model() -> None:
    """Release the cached model after a device-setting change."""
    global _model, _load_error
    with _load_lock:
        _model = None
        _load_error = None


def _load_model():
    """懒加载 faster-whisper 模型（阻塞，只该在线程池里调）。返回模型或抛异常。"""
    global _model, _load_error
    if _model is not None:
        return _model
    with _load_lock:
        if _model is not None:
            return _model
        try:
            from faster_whisper import WhisperModel  # 依赖没装会 ImportError
        except Exception as e:  # noqa: BLE001 — 把原因原样带给前端提示装依赖
            _load_error = f"faster-whisper 未安装：{e}（后端 venv 内 pip install faster-whisper）"
            raise RuntimeError(_load_error) from e
        try:
            settings.ASR_MODEL_DIR.mkdir(parents=True, exist_ok=True)
            _model = WhisperModel(
                settings.ASR_MODEL,
                device=settings.ASR_DEVICE,
                compute_type=settings.ASR_COMPUTE_TYPE,
                download_root=str(settings.ASR_MODEL_DIR),
            )
            _load_error = None
        except Exception as e:  # noqa: BLE001 — 下载失败/模型名错等，如实上报
            _load_error = f"模型加载失败（{settings.ASR_MODEL}）：{e}"
            raise RuntimeError(_load_error) from e
    return _model


def _transcribe_sync(data: bytes) -> dict:
    """阻塞转写：解码 → 识别 → 拼段。只该在线程池里调。"""
    model = _load_model()
    segments, info = model.transcribe(
        io.BytesIO(data),
        beam_size=5,
        vad_filter=True,  # 掐掉静音，短语音条更稳
    )
    text = "".join(seg.text for seg in segments).strip()
    return {"text": text, "language": getattr(info, "language", None)}


@router.get("/status")
def status() -> dict:
    """报告语音输入能不能用：是否开启 / 依赖是否装齐 / 模型是否已加载。

    只做轻量探测（不触发模型下载）：仅检查 faster-whisper 能否 import。
    真正的模型加载留到首次 transcribe，以免 status 拖慢或触发大文件下载。
    """
    if not settings.ASR_ENABLED:
        return {"enabled": False, "available": False, "model": settings.ASR_MODEL,
                "loaded": False, "error": "语音输入已在后端关闭（ASR_ENABLED=0）"}
    try:
        import faster_whisper  # noqa: F401
        dep_ok, err = True, None
    except Exception as e:  # noqa: BLE001
        dep_ok, err = False, f"faster-whisper 未安装：{e}"
    return {
        "enabled": True,
        "available": dep_ok,
        "model": settings.ASR_MODEL,
        "loaded": _model is not None,
        "error": _load_error or err,
    }


@router.post("/transcribe")
async def transcribe(request: Request) -> dict:
    """收音频原始字节（非 multipart，前端直接把 Blob 当 body 发），转写成文字。"""
    if not settings.ASR_ENABLED:
        raise HTTPException(503, "语音输入已在后端关闭（ASR_ENABLED=0）")

    # 流式累积并卡上限，避免超大体撑爆内存（对齐 files 上传的防护思路）。
    buf = bytearray()
    async for chunk in request.stream():
        buf.extend(chunk)
        if len(buf) > MAX_AUDIO:
            raise HTTPException(413, f"音频过大（>{MAX_AUDIO // (1024 * 1024)}MB）")
    data = bytes(buf)
    if not data:
        raise HTTPException(400, "空音频")

    try:
        # CPU 阻塞活丢线程池，别卡事件循环（否则全部会话 SSE 卡死，WB-002）。
        result = await asyncio.to_thread(_transcribe_sync, data)
    except RuntimeError as e:
        # 依赖没装 / 模型没就绪 —— 诚实 503，前端据此提示，不返回假文本。
        raise HTTPException(503, str(e)) from e
    except Exception as e:  # noqa: BLE001 — 解码失败等
        raise HTTPException(422, f"转写失败：{e}") from e
    return result
