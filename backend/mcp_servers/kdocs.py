"""金山文档 — a built-in local MCP server (stdio) that bridges the official
`kdocs-cli` (WPS 云文档 API 的命令行封装).

Lets the agent really operate 金山文档 (WPS 云文档): 搜索 / 读取 / 新建写入 /
分享 / 网页剪藏 / AI 生成 PPT，以及经通用透传覆盖全部 10 服务 170+ 动作。Same
shape as the other built-in connectors (notes / clock / telegram): one FastMCP
server launched in-process, so it works in dev and in a frozen bundle — no
Node/npx needed. It shells out to the separately-installed `kdocs-cli.exe`.

Credentials (hard-line #4): the WPS token is read from the environment
(`KDOCS_TOKEN`) AT CALL TIME — never baked in, never sent to the frontend — and
the connector is gated by `requires` in mcp_client.py so a run without the token
is skipped with a clear reason. When `KDOCS_TOKEN` is set it is passed via
`--token`; otherwise `kdocs-cli` falls back to its own system-keychain login
(`kdocs-cli auth login`). The subprocess env is a secret-free whitelist (WB-011)
so `LLM_API_KEY` and other backend secrets never cross into the CLI process.

Concurrency: `kdocs-cli` is a synchronous CLI, so each tool runs it via
`subprocess.run` inside `asyncio.to_thread`. That both (a) keeps the backend's
event loop free — a blocking call here would stall every other SSE stream
(WB-002) — and (b) sidesteps Windows' Selector event loop not supporting
`asyncio.create_subprocess_exec`.

Run standalone: `python kdocs.py` (speaks MCP on stdio).
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("kdocs")

# kdocs-cli's JSON envelope: {"code": 0, "message": "...", "data": ...}. code==0
# means success — the process exit code is 0 even on auth failure, so we MUST
# inspect `code`, never trust the exit status.
_OK = 0
# Cap a tool result so a huge document read can't flood the LLM context (ethos of
# WB-025's truncation). Reads/creates return structured JSON well under this.
_MAX_OUT = 12000
# Default per-call timeout; slow ops (read big docs, create, AI PPT) raise it.
_TIMEOUT = 90.0

# Only these host env vars reach the kdocs-cli subprocess — a whitelist, never
# `os.environ` wholesale, so LLM_API_KEY / other connector tokens can't leak into
# it (WB-011, hard-line #4). kdocs-cli needs USERPROFILE/APPDATA/LOCALAPPDATA to
# reach its own config / system-keychain; PATH to resolve helpers.
_SAFE_ENV = {
    "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "SYSTEMDRIVE",
    "TEMP", "TMP", "TMPDIR", "HOME", "HOMEPATH", "HOMEDRIVE", "USERPROFILE",
    "USERNAME", "USERDOMAIN", "APPDATA", "LOCALAPPDATA", "PROGRAMFILES",
    "PROGRAMFILES(X86)", "PROGRAMDATA", "LANG", "LC_ALL", "LC_CTYPE", "TZ",
}

# The 10 服务 exposed by kdocs-cli, for the generic `run` / `list_actions` tools.
_SERVICES = ["drive", "sheet", "otl", "dbsheet", "form", "wpp", "aippt", "wps", "pdf", "kwiki"]


def _token() -> str:
    # Read at call time (not import) so the server picks up backend/.env whether
    # it runs in-process (env already loaded) or as a spawned subprocess.
    return os.environ.get("KDOCS_TOKEN", "").strip()


def _cli() -> str | None:
    """Locate the kdocs-cli executable, or None if it isn't installed. On Windows
    `shutil.which` honours PATHEXT so it finds kdocs-cli.exe; we also probe the
    default per-user install dir as a fallback."""
    found = shutil.which("kdocs-cli")
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        cand = Path(local) / "kdocs-cli" / "kdocs-cli.exe"
        if cand.exists():
            return str(cand)
    return None


def _safe_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k.upper() in _SAFE_ENV}
    # Harmless on a native exe; belt-and-braces for any Python helper it spawns.
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _run_sync(args: list[str], timeout: float) -> tuple[bool, str, str]:
    """Blocking kdocs-cli invocation (run off-loop via asyncio.to_thread).

    Returns (spawned_ok, stdout, stderr). `spawned_ok` is False only when the
    process couldn't run at all (missing binary / timeout) — a CLI that ran and
    returned an error envelope is spawned_ok=True with that JSON on stdout.
    """
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            timeout=timeout,
            env=_safe_env(),
            # stdin closed so a prompt (e.g. auth) can never hang the call.
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return False, "", f"调用超时（>{int(timeout)}s）"
    except Exception as e:  # noqa: BLE001 — surface as a readable tool result
        return False, "", str(e)
    out = proc.stdout.decode("utf-8", "replace")
    err = proc.stderr.decode("utf-8", "replace")
    return True, out, err


async def _call_raw(
    service: str, action: str, params: dict[str, Any] | None = None, *, timeout: float = _TIMEOUT
) -> tuple[bool, Any]:
    """Call one kdocs-cli <service> <action>. Returns (ok, data_or_error_text).

    Never raises: a missing binary / timeout / API error all come back as
    (False, <human text>) so a broken call degrades to a readable tool result
    instead of crashing the chat.
    """
    exe = _cli()
    if not exe:
        return False, (
            "未安装 kdocs-cli（金山文档命令行工具）。请安装后在 backend/.env 配置 "
            "KDOCS_TOKEN，或运行 `kdocs-cli auth login` 登录。"
        )
    args = [exe, service, action, "--output", "json"]
    token = _token()
    if token:
        args += ["--token", token]
    if params:
        args += ["--args", json.dumps(params, ensure_ascii=False)]

    spawned, out, err = await asyncio.to_thread(_run_sync, args, timeout)
    if not spawned:
        return False, f"调用 kdocs-cli 失败：{err}"

    text = out.strip()
    if not text:
        return False, (err.strip() or "kdocs-cli 无输出。")
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        # Not the JSON envelope (shouldn't happen with --output json) — return raw.
        return True, text
    if isinstance(obj, dict):
        code = obj.get("code")
        if code not in (_OK, None):
            msg = obj.get("message") or "未知错误"
            hint = ""
            if code == 400006:
                hint = "（未授权或 Token 已失效，请在连接器页点『金山文档 · 连接』重新完成 WPS 授权）"
            return False, f"金山文档接口错误 code={code}：{msg}{hint}"
        return True, obj.get("data", obj)
    return True, obj


def _fmt(res: Any) -> str:
    """Serialize a successful result to a readable, length-capped string."""
    s = res if isinstance(res, str) else json.dumps(res, ensure_ascii=False, indent=2)
    if len(s) > _MAX_OUT:
        s = s[:_MAX_OUT] + f"\n…（结果已截断，原文共 {len(s)} 字符；可缩小范围或分页再取）"
    return s


async def _call(
    service: str, action: str, params: dict[str, Any] | None = None, *, timeout: float = _TIMEOUT
) -> str:
    ok, res = await _call_raw(service, action, params, timeout=timeout)
    return _fmt(res) if ok else str(res)


# ─────────────────────────── curated tools ───────────────────────────
# High-frequency flows get first-class tools with clean signatures; everything
# else is reachable via `run` + `list_actions` below.

@mcp.tool()
async def search_files(keyword: str, search_type: str = "all", page_size: int = 20) -> str:
    """在金山文档云盘中搜索文件（夹）。

    search_type：`all` 全局 / `file_name` 仅文件名 / `content` 全文内容。返回文件名、
    file_id、drive_id、类型等，供后续 read_file / share_file 等使用。
    """
    return await _call(
        "drive", "search-files",
        {"keyword": keyword, "type": search_type, "page_size": max(1, min(int(page_size or 20), 100))},
    )


@mcp.tool()
async def read_file(url: str = "", file_id: str = "", link_id: str = "", fmt: str = "markdown") -> str:
    """读取金山文档正文，返回 Markdown / 纯文本 / 结构化数据。

    url / file_id / link_id 三选一（至少给一个）。fmt：`markdown`（默认）/ `plain` / `kdc`。
    读取表格类文档可先用 run 传 sheet_name / sheet_range 精确取区域。
    """
    if not (url or file_id or link_id):
        return "需要提供 url、file_id 或 link_id 其中之一。"
    params: dict[str, Any] = {"format": fmt}
    if url:
        params["url"] = url
    if file_id:
        params["file_id"] = file_id
    if link_id:
        params["link_id"] = link_id
    return await _call("drive", "read-file", params, timeout=120.0)


@mcp.tool()
async def create_doc(name: str, content: str = "", parent_id: str = "") -> str:
    """在金山文档新建文件并一步写入内容。

    name 必须带后缀，决定文档类型：`.otl` 智能文档（首选，排版好）/ `.docx` Word /
    `.pdf` / `.xlsx` 表格。content 为 UTF-8 的 Markdown 正文（otl/docx/pdf 适用）。
    表格/多维表的结构化数据（rangeData/records）请用 run 调 create-file-with-content。
    parent_id 为目标文件夹 ID，留空放个人云盘根目录。成功返回文件信息（含在线链接）。
    """
    if not name.strip():
        return "缺少文件名（需带后缀，如 周报.otl）。"
    params: dict[str, Any] = {"name": name}
    if content:
        params["content"] = content
    if parent_id:
        params["parent_id"] = parent_id
    return await _call("drive", "create-file-with-content", params, timeout=120.0)


@mcp.tool()
async def list_files(drive_id: str, parent_id: str = "0", page_size: int = 50) -> str:
    """列出某云盘目录下的子文件（夹）。

    drive_id 必填（可从 search_files 结果里取）；parent_id 根目录为 "0"。
    """
    return await _call(
        "drive", "list-files",
        {"drive_id": drive_id, "parent_id": parent_id or "0", "page_size": max(1, min(int(page_size or 50), 200))},
    )


@mcp.tool()
async def share_file(file_id: str, scope: str = "anyone") -> str:
    """开启文件分享并返回分享链接。

    scope：`anyone` 所有人可访问 / `company` 仅企业 / `users` 指定用户。
    """
    return await _call("drive", "share-file", {"file_id": file_id, "scope": scope})


@mcp.tool()
async def scrape_url(url: str) -> str:
    """网页剪藏：抓取一个网页并自动保存为金山智能文档，返回剪藏任务 job_id。

    这是把外部网页内容存入金山文档的正确方式。剪藏是异步的：拿到 job_id 后，
    每隔约 2 秒用 `run("drive", "scrape-progress", '{"job_id": "..."}')` 轮询，
    status=1 表示完成，届时服务端已建好文档。（金山文档自身的分享链接不要用本工具。）
    """
    return await _call("drive", "scrape-url", {"url": url})


@mcp.tool()
async def generate_ppt(topic: str, style_tags: str = "") -> str:
    """AI 生成演示文稿（PPT）：输入一句话主题，AI 联网研究后生成，返回可下载/在线链接。

    style_tags 可选，逗号分隔（如 "科技风,商务风"）。基于金山文档已有内容生成 PPT，
    请用 run 调 aippt.execute 传 task_type=doc_ppt + link_id。生成较慢，请耐心等待。
    """
    if not topic.strip():
        return "缺少 PPT 主题。"
    item: dict[str, Any] = {"type": "text", "content": topic}
    tags = [t.strip() for t in style_tags.split(",") if t.strip()]
    if tags:
        item["style_tags"] = tags
    return await _call(
        "aippt", "execute",
        {"task_type": "theme_ppt", "mode": "basic", "input": [item]},
        timeout=300.0,
    )


# ─────────────────── generic passthrough + discovery ───────────────────

@mcp.tool()
async def run(service: str, action: str, params_json: str = "{}") -> str:
    """直接调用任意金山文档 CLI 能力（覆盖 10 服务 170+ 动作），curated 工具没覆盖的都走这里。

    service ∈ drive/sheet/otl/dbsheet/form/wpp/aippt/wps/pdf/kwiki；action 为该服务下的
    动作名（连字符式，如 rename-file、move-file、create-folder）；params_json 是该动作的
    完整 JSON 参数字符串。不确定 action 名或参数时，先用 list_actions 查。
    ⚠ 删除 / 关闭 / 取消分享等不可逆操作执行前，务必先向用户确认。
    """
    if service not in _SERVICES:
        return f"未知 service：{service}。可用：{', '.join(_SERVICES)}。"
    try:
        params = json.loads(params_json) if params_json.strip() else {}
    except json.JSONDecodeError as e:
        return f"params_json 不是合法 JSON：{e}"
    if not isinstance(params, dict):
        return "params_json 需是一个 JSON 对象（{...}）。"
    return await _call(service, action, params, timeout=180.0)


@mcp.tool()
async def list_actions(service: str = "", action: str = "") -> str:
    """查询金山文档 CLI 支持的服务 / 动作 / 参数（等价于 --help），供调用 run 前查阅。

    留空 → 列出全部服务；给定 service → 列出其所有动作；给定 service+action → 该动作的
    详细参数（类型、可选值、约束）。据此再用 run 精确调用。
    """
    exe = _cli()
    if not exe:
        return "未安装 kdocs-cli（金山文档命令行工具）。"
    if service and service not in _SERVICES:
        return f"未知 service：{service}。可用：{', '.join(_SERVICES)}。"
    args = [exe]
    if service:
        args.append(service)
    if action:
        args.append(action)
    args.append("--help")
    spawned, out, err = await asyncio.to_thread(_run_sync, args, 30.0)
    if not spawned:
        return f"查询失败：{err}"
    text = (out.strip() or err.strip() or "（无输出）")
    return text[:_MAX_OUT]


if __name__ == "__main__":
    mcp.run()
