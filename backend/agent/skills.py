"""Skills = injectable prompt + optional toolpack (M5).

Enabling a skill on a project appends its instructions to the system prompt and
adds any tools it carries to the agent's toolset. Most skills are instruction-only
(they steer behaviour); the "Web Access" skill ships a real `web_fetch` tool — a
genuinely new capability the base agent lacks — proving toolpacks work.

Names match the frontend skill picker (SK_GRID); unknown names get a generic
instruction so every catalog skill still has an effect.
"""
from __future__ import annotations

import csv
import io
import ipaddress
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
)


# name → (instructions, tools)
SKILLS: dict[str, tuple[str, list[Tool]]] = {
    "Web Access（浏览器自动化）": ("需要联网信息时，用 web_fetch 抓取网页内容再作答；引用来源 URL。", [web_fetch]),
    "MarkItDown": ("把网页 / 文档整理成干净、结构化的 Markdown：用 html_to_markdown 抓取并转换网页，再按需精修标题层级、列表与表格。", [html_to_markdown]),
    "技能创建指南": ("当用户想创建自定义技能时，说明技能 = 提示词 + 工具包 的结构，并给出可落地的模板。", []),
    "Word 文档生成": ("以规范的长文档结构组织输出：清晰的标题层级、要点、必要的表格与结论。", []),
    "Excel 文件处理": ("处理表格数据时：对工作区里的 CSV 用 analyze_csv 获取行列/数值列统计，再基于真实数据作答；输出用清晰的表格结构。", [analyze_csv]),
    "股票综合分析器": ("做股票分析时分三维展开：基本面、消息面、资金面，结论先行并提示风险。", []),
}


def builtin_list() -> list[dict[str, Any]]:
    """内置技能清单（名字 / 描述 / 工具名）——供前端 loadout 选择器（WB-180）。

    它们**不在磁盘上**（不是从 SkillHub 装的），只存在于上面的 SKILLS dict，因此
    `GET /api/skills` 的磁盘扫描列不出它们。前端此前只能靠静态 SK_GRID 里的名字恰好
    撞上 SKILLS 的 key 才选得到 —— 这里给它一个真实来源。
    `tools` 为空 = 纯提示词技能（按本项目定义「技能 = 提示词 + 工具包」，这也是真技能）。
    """
    return [
        {"name": n, "description": instr, "tools": [t.name for t in tools]}
        for n, (instr, tools) in SKILLS.items()
    ]


def skill_def(name: str) -> tuple[str, list[Tool]]:
    # 内置技能（带工具包）优先；否则若它对应一个已安装（未停用）的磁盘 skill（WB-055），
    # 注入其真实 SKILL.md 正文 —— 让从 SkillHub 装的技能真生效，而不是通用兜底话术。
    if name in SKILLS:
        return SKILLS[name]
    from agent import skills_store  # 延迟导入，避免与 config/加载顺序耦合
    body = skills_store.instructions_for(name)
    if body:
        return (body, [])
    return (f"运用「{name}」技能的专长完成相关任务。", [])
