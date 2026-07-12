"""OpenAI-compatible streaming client.

One interface adapts DeepSeek / GLM / Kimi / MiniMax / OpenAI — anything that
speaks the /chat/completions SSE protocol. We use httpx directly rather than a
vendor SDK so the same code path works against any `LLM_API_BASE` (decision A.2).

Streams three kinds of increment: assistant prose (`content`), chain-of-thought
(`reasoning_content`, when the model exposes it), and function/tool-call deltas.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import httpx

from config import settings


class LLMError(RuntimeError):
    pass


@dataclass
class ToolCallDelta:
    index: int
    id: str | None = None
    name: str | None = None
    arguments: str = ""


@dataclass
class Delta:
    """A single streamed increment from the model."""
    content: str = ""
    reasoning: str = ""
    tool_calls: list[ToolCallDelta] = field(default_factory=list)
    finish_reason: str | None = None
    usage: dict[str, Any] | None = None


async def stream_chat(
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.6,
    api_base: str | None = None,
    api_key: str | None = None,
    chat_path: str = "/chat/completions",
) -> AsyncIterator[Delta]:
    """Yield Delta increments from an OpenAI-compatible /chat/completions stream.

    api_base/api_key override the .env defaults so a custom model (WB-124) or a
    built-in provider (WB-128) can hit its own endpoint. chat_path lets a
    non-standard provider (e.g. MiniMax's /text/chatcompletion_v2) work while the
    request/response stay OpenAI-shaped. Absent overrides fall back to the .env provider.
    """
    base = (api_base or settings.LLM_API_BASE).rstrip("/")
    key = api_key or settings.LLM_API_KEY
    # Custom/provider models carry their own key; a bare .env with no key is only
    # fatal when this call also lacks an override.
    if not key or not base:
        raise LLMError("LLM 未配置：请在 backend/.env 填入 LLM_API_KEY 与 LLM_API_BASE，或为该厂商/自定义模型填写 API Key")

    url = f"{base}/{chat_path.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    body: dict[str, Any] = {
        "model": model or settings.LLM_MODEL,
        "messages": messages,
        "stream": True,
        "temperature": temperature,
        "stream_options": {"include_usage": True},
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"

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
                    if usage:
                        yield Delta(usage=usage)
                    continue

                choice = choices[0]
                delta = choice.get("delta") or {}
                content = delta.get("content") or ""
                reasoning = delta.get("reasoning_content") or delta.get("reasoning") or ""
                finish = choice.get("finish_reason")

                tcs: list[ToolCallDelta] = []
                for tc in delta.get("tool_calls") or []:
                    fn = tc.get("function") or {}
                    tcs.append(
                        ToolCallDelta(
                            index=tc.get("index", 0),
                            id=tc.get("id"),
                            name=fn.get("name"),
                            arguments=fn.get("arguments") or "",
                        )
                    )

                if content or reasoning or tcs or finish or usage:
                    yield Delta(
                        content=content,
                        reasoning=reasoning,
                        tool_calls=tcs,
                        finish_reason=finish,
                        usage=usage,
                    )
