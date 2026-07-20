"""Skills = injectable prompt + optional toolpack (M5).

Enabling a skill on a project appends its instructions to the system prompt and
adds any tools it carries to the agent's toolset. Most skills are instruction-only
(they steer behaviour); the "Web Access" skill ships a real `web_fetch` tool — a
genuinely new capability the base agent lacks — proving toolpacks work.

Runtime identity is the stable skill slug. Display names are resolved only for UI text;
unknown identities are skipped and reported honestly instead of receiving a generic prompt.
"""
from __future__ import annotations

import csv
import io
import ipaddress
import logging
import re
import socket
import statistics
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

import httpx

from agent.sandbox import SandboxError, resolve_in_sandbox
from agent.tools import Tool, ToolOutcome

_MAX = 6000
_log = logging.getLogger("workbuddy.skills")


def _is_blocked_host(host: str) -> bool:
    """主机是否解析到 loopback/私网/链路本地/保留地址 —— 挡 SSRF（打本机 API、内网服务、
    云元数据 169.254.169.254 等）。解析不了也保守拒绝（WB-160）。"""
    host = (host or "").strip().strip("[]")
    if not host:
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:  # noqa: BLE001 — 解析失败 → 拒绝
        return True
    for info in infos:
        try:
            addr = ipaddress.ip_address(info[4][0].split("%")[0])
        except ValueError:
            return True
        if (addr.is_loopback or addr.is_private or addr.is_link_local
                or addr.is_multicast or addr.is_reserved or addr.is_unspecified):
            return True
    return False


def _guarded_get(url: str) -> httpx.Response:
    """带 SSRF 防护的 GET：仅 http(s)，逐跳（含重定向）校验目标主机不指向本机/内网（WB-160）。"""
    for _ in range(5):  # 最多跟 5 跳重定向
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("仅支持 http(s) URL")
        if _is_blocked_host(parsed.hostname or ""):
            raise ValueError("拒绝访问本机/内网地址")
        r = httpx.get(url, timeout=15, follow_redirects=False, headers={"User-Agent": "WorkBuddy/0.1"})
        loc = r.headers.get("location")
        if r.is_redirect and loc:
            url = str(r.url.join(loc))
            continue
        return r
    raise ValueError("重定向过多")


def _web_fetch_run(args: dict) -> ToolOutcome:
    url = (args.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return ToolOutcome(text="请提供 http(s) URL")
    try:
        r = _guarded_get(url)
        body = r.text
        body = body if len(body) <= _MAX else body[:_MAX] + f"\n… [截断，共 {len(body)} 字符]"
        return ToolOutcome(text=f"HTTP {r.status_code} {url}\n{body}")
    except Exception as e:  # noqa: BLE001
        return ToolOutcome(text=f"抓取失败：{e}")


web_fetch = Tool(
    name="web_fetch",
    description="抓取一个网页 / URL 的内容（HTTP GET，返回文本，可用于联网获取信息）。",
    parameters={
        "type": "object",
        "properties": {"url": {"type": "string", "description": "要抓取的 http(s) 链接"}},
        "required": ["url"],
    },
    pre=lambda a: {"kind": "step", "tool": "web_fetch", "label": f"网页获取 {a.get('url', '')[:80]}"},
    run=_web_fetch_run,
    # HTTP GET = 读，不改任何状态 → 计划模式可用（WB-186）。plan 的契约是「plan, don't
    # execute / no write_file、run_command」，查资料正是规划该做的事，滤掉反而让规划变差。
    plan_safe=True,
)


# ── Excel 文件处理: analyze_csv — real structured-data analysis over a workspace CSV.
def _analyze_csv_run(args: dict) -> ToolOutcome:
    path = (args.get("path") or "").strip()
    if not path:
        return ToolOutcome(text="请提供工作区内的 CSV 文件路径。")
    try:
        p = resolve_in_sandbox(path)
    except SandboxError as e:
        return ToolOutcome(text=f"路径无效：{e}")
    if not p.exists() or not p.is_file():
        return ToolOutcome(text=f"文件不存在：{path}")
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        return ToolOutcome(text=f"读取失败：{e}")
    rows = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
    if not rows:
        return ToolOutcome(text="（空文件或无数据行）")
    header, data = rows[0], rows[1:]
    out = [f"CSV：{path}", f"行数：{len(data)}（不含表头）", f"列数：{len(header)}", f"表头：{', '.join(header)}", ""]
    for ci, col in enumerate(header):
        vals: list[float] = []
        for r in data:
            if ci < len(r) and r[ci].strip():
                try:
                    vals.append(float(r[ci].replace(",", "")))
                except ValueError:
                    pass
        if vals and len(vals) >= max(1, len(data) // 2):
            out.append(
                f"· [{col}] 数值列：计数 {len(vals)}，最小 {min(vals):g}，最大 {max(vals):g}，"
                f"均值 {statistics.mean(vals):.4g}，求和 {sum(vals):g}"
            )
        else:
            uniq = len({r[ci] for r in data if ci < len(r)})
            out.append(f"· [{col}] 文本列：{uniq} 个不同值")
    return ToolOutcome(text="\n".join(out))


analyze_csv = Tool(
    name="analyze_csv",
    description="读取工作区内的 CSV 文件并给出概览：行列数、表头、每个数值列的最小/最大/均值/求和。",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string", "description": "工作区内的 CSV 相对路径"}},
        "required": ["path"],
    },
    pre=lambda a: {"kind": "step", "tool": "analyze_csv", "label": f"分析 CSV {a.get('path', '')[:60]}"},
    run=_analyze_csv_run,
    plan_safe=True,  # 沙箱内只读 CSV（WB-186）
)


# ── MarkItDown: html_to_markdown — fetch a URL and convert its HTML to Markdown.
class _MdParser(HTMLParser):
    """Minimal HTML → Markdown: headings, paragraphs, lists, links, emphasis, code.
    Good enough for typical article/doc pages; stdlib only, no external deps."""

    _SKIP = {"script", "style", "head", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__()
        self.out: list[str] = []
        self._skip = 0
        self._href: str | None = None

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self._SKIP:
            self._skip += 1
            return
        if self._skip:
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.out.append("\n\n" + "#" * int(tag[1]) + " ")
        elif tag in ("p", "div", "section", "tr"):
            self.out.append("\n\n")
        elif tag == "br":
            self.out.append("\n")
        elif tag == "li":
            self.out.append("\n- ")
        elif tag == "a":
            self._href = dict(attrs).get("href")
            self.out.append("[")
        elif tag in ("strong", "b"):
            self.out.append("**")
        elif tag in ("em", "i"):
            self.out.append("*")
        elif tag == "code":
            self.out.append("`")
        elif tag == "hr":
            self.out.append("\n\n---\n\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP:
            self._skip = max(0, self._skip - 1)
            return
        if self._skip:
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6", "p", "ul", "ol"):
            self.out.append("\n")
        elif tag == "a":
            href, self._href = self._href, None
            self.out.append(f"]({href})" if href else "]")
        elif tag in ("strong", "b"):
            self.out.append("**")
        elif tag in ("em", "i"):
            self.out.append("*")
        elif tag == "code":
            self.out.append("`")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.out.append(re.sub(r"[ \t\r\n]+", " ", data))

    def markdown(self) -> str:
        return re.sub(r"\n{3,}", "\n\n", "".join(self.out)).strip()


def _html_to_md_run(args: dict) -> ToolOutcome:
    url = (args.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return ToolOutcome(text="请提供 http(s) URL。")
    try:
        r = _guarded_get(url)
    except Exception as e:  # noqa: BLE001
        return ToolOutcome(text=f"抓取失败：{e}")
    parser = _MdParser()
    try:
        parser.feed(r.text)
    except Exception:  # noqa: BLE001 — malformed HTML must not crash the tool
        pass
    md = parser.markdown()
    md = md if len(md) <= _MAX else md[:_MAX] + f"\n… [截断，共 {len(md)} 字符]"
    return ToolOutcome(text=f"# 来自 {url}\n\n{md}" if md else f"（{url} 未提取到正文）")


html_to_markdown = Tool(
    name="html_to_markdown",
    description="抓取一个网页并把它的 HTML 转成干净的 Markdown（标题/段落/列表/链接）。",
    parameters={
        "type": "object",
        "properties": {"url": {"type": "string", "description": "要转换的 http(s) 网页链接"}},
        "required": ["url"],
    },
    pre=lambda a: {"kind": "step", "tool": "html_to_markdown", "label": f"转 Markdown {a.get('url', '')[:70]}"},
    run=_html_to_md_run,
    plan_safe=True,  # HTTP GET = 读（WB-186）
)


# ── 技能创建指南：把确认后的结构化字段真写入本机技能目录（WB-206）。
def _create_local_skill_run(args: dict) -> ToolOutcome:
    from agent import skills_store

    try:
        result = skills_store.create_skill(
            slug=str(args.get("slug") or ""),
            name=str(args.get("name") or ""),
            description=str(args.get("description") or ""),
            instructions=str(args.get("instructions") or ""),
        )
    except skills_store.SkillImportError as exc:
        return ToolOutcome(text=f"创建技能失败：{exc}")
    skill = result["skill"]
    return ToolOutcome(text=f"已创建并安装技能「{skill['name']}」（slug={skill['slug']}）。可在技能页的“我安装的”中查看和启用。")


create_local_skill = Tool(
    name="create_local_skill",
    description="创建并安装一个本机提示词技能。先与用户确认名称、用途和完整指令，再调用本工具。",
    parameters={
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "稳定英文标识，如 meeting-notes；仅字母数字与 . _ -"},
            "name": {"type": "string", "description": "技能显示名称"},
            "description": {"type": "string", "description": "一句话说明技能用途和触发场景"},
            "instructions": {"type": "string", "description": "给智能体执行该技能的完整 Markdown 指令"},
        },
        "required": ["slug", "name", "description", "instructions"],
    },
    pre=lambda a: {"kind": "step", "tool": "create_local_skill", "label": f"创建技能 {a.get('name', '')[:60]}"},
    run=_create_local_skill_run,
)


# 工具名 → 真 Tool 对象（WB-183）。技能**定义**（提示词 + 该用哪些工具）已迁进 DB 的
# catalog_skills（种子见 storage/catalog_seed.py::BUILTIN_SKILLS），改一条内置技能的提示词
# 只要改数据、不必改代码重启 —— 补齐 WB-059 漏掉的第三块（专家人格/连接器 spec 早已入库）。
# 代码里只保留这张注册表：Tool 是 Python 对象、进不了 DB，库里存工具**名**，这里按名解析。
# 同连接器「launch spec 存库、实现在代码」的分工。
_TOOL_REGISTRY: dict[str, Tool] = {
    "web_fetch": web_fetch,
    "html_to_markdown": html_to_markdown,
    "analyze_csv": analyze_csv,
    "create_local_skill": create_local_skill,
}


def _resolve_tools(names: list[str]) -> list[Tool]:
    """工具名 → Tool；库里写了但代码里没有的名字**跳过**（目录可运营，注册表是代码事实）。"""
    return [_TOOL_REGISTRY[n] for n in names if n in _TOOL_REGISTRY]


def builtin_list() -> list[dict[str, Any]]:
    """内置技能清单（供前端 loadout 选择器，WB-180）——**读库**（catalog_skills，WB-183）。

    它们**不在磁盘上**（不是从 SkillHub 装的），故 `GET /api/skills` 的磁盘扫描列不出它们；
    前端此前只能靠静态 SK_GRID 里的名字恰好撞上硬编码 SKILLS 的 key 才选得到。
    `tools` 只报**代码里真有实现**的（库里写了但注册表没有的不算数，别让目录承诺不存在的能力）。
    """
    from storage import db  # 延迟导入，避免 storage.db ↔ agent.* 循环依赖
    return [
        {
            "slug": s["slug"],
            "name": s["name"],
            "description": s["description"] or s["instructions"],
            "tools": [t.name for t in _resolve_tools(s["tools"])],
        }
        for s in db.skill_specs()
    ]


def canonical_skill_key(key: str) -> str | None:
    """目录名/展示名/磁盘 key → 稳定 slug；无法唯一解析时返回 None。"""
    from storage import db
    spec = db.skill_spec_for(key)
    if spec:
        return str(spec["slug"])
    from agent import skills_store
    installed = skills_store.canonical_slug(key)
    if installed:
        return installed
    # 一个合法 slug 即使当前机器尚未安装，也仍是可持久化的稳定身份；运行时会诚实报未就绪。
    # 中文/带空格的纯展示名无法解析时则返回 None，由持久化调用方清理。
    raw = (key or "").strip()
    return raw if skills_store.valid_slug(raw) else None


def canonical_skill_keys(keys: list[str], *, keep_unknown: bool = False) -> list[str]:
    """把一组技能身份归一为 slug 并去重。

    持久化配置使用默认值：未知商品卡直接丢弃；即时聊天可 `keep_unknown=True`，
    让运行时继续通过 SSE 诚实报告“未安装或已停用”，而不是静默吞掉。
    """
    out: list[str] = []
    for raw in keys:
        value = canonical_skill_key(raw)
        if value is None and keep_unknown:
            value = (raw or "").strip() or None
        elif value is None and (raw or "").strip():
            _log.warning("drop unresolved persisted skill identity: %s", (raw or "").strip())
        if value and value not in out:
            out.append(value)
    return out


def skill_display_name(key: str) -> str:
    """稳定 slug → 人类可读名称；身份与展示彻底分离。"""
    from storage import db
    spec = db.skill_spec_for(key)
    if spec:
        return str(spec["name"] or spec["slug"])
    from agent import skills_store
    return skills_store.display_name_for(key) or key


def skill_def(name: str) -> tuple[str, list[Tool]] | None:
    """把 loadout 里的技能名（或 slug）解析成 (指令, 工具包)；**解析不到返回 None**。

    两层，都是真的：
    1. 目录技能（DB 的 `catalog_skills`，WB-183）——指令读库，工具名经 `_TOOL_REGISTRY` 解析；
    2. 对应一个已安装且未停用的磁盘 skill（WB-055）→ 注入其真实 SKILL.md 正文。

    曾经还有第三层兜底 `f"运用「{name}」技能的专长完成相关任务。"` —— 那是**伪装**：
    它让每张后端零能力的商品卡都"看起来有效果"，UI 显示技能已挂载，实则 agent 只收到
    一句空话（`SK_GRID` 17 张卡里 11 张如此）。已删除（WB-179，铁律#1）。
    解析不到就返回 None，由调用方**如实告知用户「未就绪」**——照连接器 `mcp_skipped`
    的既有范式（选了但加载不了就明说，不做静默 no-op），宁可少一个技能也不假装有。
    """
    from storage import db  # 延迟导入，避免 storage.db ↔ agent.* 循环依赖
    spec = db.skill_spec_for(name)  # 按 slug 或 name 命中（迁移期两者并存，WB-179）
    if spec and spec["instructions"]:
        return (spec["instructions"], _resolve_tools(spec["tools"]))
    from agent import skills_store  # 延迟导入，避免与 config/加载顺序耦合
    body = skills_store.instructions_for(name)
    if body:
        return (body, [])
    return None
