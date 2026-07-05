"""OpenAI-compatible streaming client.

One interface adapts DeepSeek / GLM / Kimi / MiniMax / OpenAI — anything that
speaks the /chat/completions SSE protocol. We use httpx directly rather than a
vendor SDK so the same code path works against any `LLM_API_BASE` (decision A.2).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, AsyncIterator

import httpx

from config import settings


class LLMError(RuntimeError):
    pass


@dataclass
class Delta:
    """A single streamed increment from the model."""
    content: str = ""
    finish_reason: str | None = None
    # token counts arrive on the final chunk when the provider sends usage
    usage: dict[str, Any] | None = None


async def stream_chat(
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    temperature: float = 0.7,
) -> AsyncIterator[Delta]:
    """Yield Delta increments from an OpenAI-compatible /chat/completions stream."""
    if not settings.llm_configured:
        raise LLMError(
            "LLM 未配置：请在 backend/.env 填入 LLM_API_KEY 与 LLM_API_BASE"
        )

    url = f"{settings.LLM_API_BASE}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model or settings.LLM_MODEL,
        "messages": messages,
        "stream": True,
        "temperature": temperature,
        # ask providers that support it to report token usage on the final chunk
        "stream_options": {"include_usage": True},
    }

    timeout = httpx.Timeout(connect=15.0, read=None, write=15.0, pool=15.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", url, headers=headers, json=body) as resp:
            if resp.status_code >= 400:
                detail = (await resp.aread()).decode("utf-8", "replace")
                raise LLMError(f"LLM {resp.status_code}: {detail[:500]}")

            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue

                usage = chunk.get("usage")
                choices = chunk.get("choices") or []
                if not choices:
                    # some providers emit a trailing usage-only chunk
                    if usage:
                        yield Delta(usage=usage)
                    continue

                choice = choices[0]
                delta = choice.get("delta") or {}
                content = delta.get("content") or ""
                finish = choice.get("finish_reason")
                if content or finish or usage:
                    yield Delta(content=content, finish_reason=finish, usage=usage)
