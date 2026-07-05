"""工作区检索 — a built-in local MCP server (stdio) for full-text search.

Greps the project's workspace (WORKBUDDY_NOTES_DIR, set by the runtime to the
current project/session root) for a query string across text files, returning
`relpath:line: text` hits. Complements the built-in read_file/list_dir tools
(which can't search content). Zero external deps or credentials. Run standalone:
`python search.py` (speaks MCP on stdio).
"""
from __future__ import annotations

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("workspace-search")

_ROOT = Path(os.environ.get("WORKBUDDY_NOTES_DIR", ".")).resolve()

# Skip huge files and obvious binaries so a search stays fast and text-only.
_MAX_BYTES = 1_000_000
_SKIP_SUFFIX = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz",
    ".tar", ".exe", ".dll", ".so", ".dylib", ".bin", ".db", ".sqlite", ".woff",
    ".woff2", ".ttf", ".mp3", ".mp4", ".mov",
}


@mcp.tool()
def search_files(query: str, max_results: int = 20) -> str:
    """在当前工作区里全文检索（大小写不敏感），返回 相对路径:行号: 匹配行。"""
    q = (query or "").strip().lower()
    if not q:
        return "请提供检索关键词。"
    hits: list[str] = []
    for path in _ROOT.rglob("*"):
        if len(hits) >= max_results:
            break
        if not path.is_file() or path.suffix.lower() in _SKIP_SUFFIX:
            continue
        try:
            if path.stat().st_size > _MAX_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = path.relative_to(_ROOT).as_posix()
        for i, line in enumerate(text.splitlines(), 1):
            if q in line.lower():
                hits.append(f"{rel}:{i}: {line.strip()[:200]}")
                if len(hits) >= max_results:
                    break
    if not hits:
        return f"未找到包含「{query}」的内容。"
    return "\n".join(hits)


@mcp.tool()
def list_workspace() -> str:
    """列出当前工作区里的文件（相对路径），了解可检索的范围。"""
    files = [
        p.relative_to(_ROOT).as_posix()
        for p in sorted(_ROOT.rglob("*"))
        if p.is_file()
    ]
    if not files:
        return "（工作区为空）"
    return "\n".join(files[:200])


if __name__ == "__main__":
    mcp.run()
