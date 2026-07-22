"""Server-side WeKnora client for project knowledge (WB-290).

Only this process sees the tenant API key. Console and AgentMate call authenticated
Server project routes with stable local KB ids; routers resolve those ids to the
provider ids before this module is invoked.
"""
from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urlsplit

import httpx

import platform_settings

TIMEOUT = 60.0
MIN_SAFE_URL_IMPORT_VERSION = (0, 2, 12)


class WeKnoraError(RuntimeError):
    pass


def configured() -> bool:
    return bool(platform_settings.effective("knowledge.weknora_api_key"))


def public_config() -> dict[str, Any]:
    url, url_source = platform_settings.effective_with_source("knowledge.weknora_url")
    model, model_source = platform_settings.effective_with_source("knowledge.weknora_embedding_model_id")
    _key, key_source = platform_settings.effective_with_source("knowledge.weknora_api_key")
    return {
        "configured": configured(),
        "url": url,
        "embedding_model_configured": bool(model),
        "source": {"url": url_source, "api_key": key_source, "embedding_model_id": model_source},
    }


def _headers(extra: Optional[dict[str, str]] = None) -> dict[str, str]:
    headers = {"X-API-Key": str(platform_settings.effective("knowledge.weknora_api_key"))}
    if extra:
        headers.update(extra)
    return headers


def _error_message(body: Any) -> str:
    if isinstance(body, dict):
        if body.get("message"):
            return str(body["message"])
        error = body.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("details") or "")
        if error:
            return str(error)
    return ""


def _unwrap(response: httpx.Response) -> Any:
    if response.status_code in (401, 403):
        raise WeKnoraError("中央 WeKnora 鉴权失败，请联系平台管理员更新 Server 服务凭据。")
    if 200 <= response.status_code < 300 and not (response.content or b"").strip():
        return None
    try:
        body = response.json()
    except Exception as exc:  # noqa: BLE001
        raise WeKnoraError(
            f"WeKnora 返回无法解析（HTTP {response.status_code}）：{response.text[:200]}"
        ) from exc
    if not 200 <= response.status_code < 300:
        raise WeKnoraError(_error_message(body) or f"WeKnora 错误（HTTP {response.status_code}）")
    if isinstance(body, dict):
        if body.get("success") is False:
            raise WeKnoraError(_error_message(body) or "WeKnora 请求失败。")
        code = body.get("code")
        if code is not None:
            try:
                if int(code) not in (0, 200):
                    raise WeKnoraError(str(body.get("message") or f"WeKnora 错误（code={code}）"))
            except (TypeError, ValueError):
                pass
        return body.get("data", body)
    return body


def request(method: str, path: str, **kwargs: Any) -> Any:
    if not configured():
        raise WeKnoraError(
            "中央知识库尚未配置：请在 AgentMate Server 部署环境设置 "
            "AGENTMATE_SERVER_WEKNORA_API_KEY。"
        )
    try:
        base_url = str(platform_settings.effective("knowledge.weknora_url"))
        response = httpx.request(
            method,
            f"{base_url}/api/v1{path}",
            headers=_headers(kwargs.pop("_headers", None)),
            timeout=TIMEOUT,
            **kwargs,
        )
    except httpx.HTTPError as exc:
        raise WeKnoraError(f"连接中央 WeKnora 失败（{base_url}）：{exc}") from exc
    return _unwrap(response)


def as_list(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        for key in ("data", "list", "items"):
            rows = data.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def list_models() -> list[dict[str, Any]]:
    return as_list(request("GET", "/models"))


def default_embedding_model_id() -> str:
    configured_model = str(platform_settings.effective("knowledge.weknora_embedding_model_id"))
    if configured_model:
        return configured_model
    for model in list_models():
        if str(model.get("type", "")).lower() == "embedding" and model.get("id"):
            return str(model["id"])
    raise WeKnoraError(
        "中央 WeKnora 未注册 Embedding 模型；请先在 WeKnora 配置模型，或设置 "
        "AGENTMATE_SERVER_WEKNORA_EMBEDDING_MODEL_ID。"
    )


def create_kb(*, name: str, description: str = "", chunk_size: int = 1000,
              chunk_overlap: int = 200) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": name,
        "type": "document",
        "embedding_model_id": default_embedding_model_id(),
        "chunking_config": {
            "chunk_size": max(100, min(int(chunk_size), 4000)),
            "chunk_overlap": max(0, min(int(chunk_overlap), 1000)),
        },
    }
    if description:
        body["description"] = description
    data = request("POST", "/knowledge-bases", json=body)
    return data if isinstance(data, dict) else {"id": data}


def get_kb(provider_id: str) -> dict[str, Any]:
    data = request("GET", f"/knowledge-bases/{provider_id}")
    return data if isinstance(data, dict) else {}


def update_kb(provider_id: str, **fields: Any) -> None:
    request("PUT", f"/knowledge-bases/{provider_id}", json={k: v for k, v in fields.items() if v is not None})


def delete_kb(provider_id: str) -> None:
    request("DELETE", f"/knowledge-bases/{provider_id}")


def upload_file(provider_id: str, *, filename: str, content: bytes, content_type: str) -> dict[str, Any]:
    data = request(
        "POST", f"/knowledge-bases/{provider_id}/knowledge/file",
        files={"file": (filename, content, content_type)},
    )
    return data if isinstance(data, dict) else {"id": data}


def list_docs(
    provider_id: str, *, page: int = 1, page_size: int = 100, keyword: str = "",
) -> dict[str, Any]:
    params: dict[str, Any] = {"page": page, "page_size": page_size}
    if keyword:
        params["keyword"] = keyword
    data = request(
        "GET", f"/knowledge-bases/{provider_id}/knowledge",
        params=params,
    )
    rows = as_list(data)
    total = data.get("total", len(rows)) if isinstance(data, dict) else len(rows)
    return {"items": rows, "total": total}


def delete_doc(provider_doc_id: str) -> None:
    request("DELETE", f"/knowledge/{provider_doc_id}")


def search(*, query: str, provider_ids: list[str], top_k: int = 8) -> list[dict[str, Any]]:
    data = request(
        "POST", "/knowledge-search",
        json={
            "query": query[:1000],
            "knowledge_base_ids": provider_ids,
            "top_k": max(1, min(int(top_k), 20)),
        },
    )
    hits = []
    for row in as_list(data):
        hits.append({
            "text": str(row.get("content") or row.get("text") or "").strip(),
            "score": row.get("score"),
            "metadata": {
                "doc_name": row.get("knowledge_filename") or row.get("knowledge_title") or "",
                "doc_id": row.get("knowledge_id") or row.get("id") or "",
            },
        })
    return hits


def system_info() -> dict[str, Any]:
    data = request("GET", "/system/info")
    return data if isinstance(data, dict) else {}


def validate_import_url(raw: str) -> str:
    value = str(raw or "").strip()
    if not value or len(value) > 2048:
        raise WeKnoraError("URL 格式非法：请提供不超过 2048 字符的 http(s) URL。")
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError as exc:
        raise WeKnoraError(f"URL 格式非法：{exc}") from exc
    if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
        raise WeKnoraError("URL 格式非法：仅支持包含主机名的 http(s) URL。")
    if parsed.username is not None or parsed.password is not None:
        raise WeKnoraError("URL 格式非法：不允许在 URL 中携带用户名或密码。")
    return value


def _require_safe_url_import() -> None:
    raw = str(system_info().get("version") or "").strip()
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:\+[0-9A-Za-z.-]+)?", raw)
    parsed = tuple(map(int, match.groups())) if match else None
    minimum = ".".join(map(str, MIN_SAFE_URL_IMPORT_VERSION))
    if parsed is None or parsed < MIN_SAFE_URL_IMPORT_VERSION:
        raise WeKnoraError(
            f"为安全起见未执行 URL 入库：中央 WeKnora 版本 {raw or '未知'}，需要稳定版 >= {minimum}。"
        )


def create_from_url(provider_id: str, *, url: str) -> dict[str, Any]:
    target = validate_import_url(url)
    _require_safe_url_import()
    data = request("POST", f"/knowledge-bases/{provider_id}/knowledge/url", json={"url": target})
    return data if isinstance(data, dict) else {"id": data}
