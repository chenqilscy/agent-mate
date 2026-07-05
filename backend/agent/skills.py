"""Skills = injectable prompt + optional toolpack (M5).

Enabling a skill on a project appends its instructions to the system prompt and
adds any tools it carries to the agent's toolset. Most skills are instruction-only
(they steer behaviour); the "Web Access" skill ships a real `web_fetch` tool — a
genuinely new capability the base agent lacks — proving toolpacks work.

Names match the frontend skill picker (SK_GRID); unknown names get a generic
instruction so every catalog skill still has an effect.
"""
from __future__ import annotations

import httpx

from agent.tools import Tool, ToolOutcome

_MAX = 6000


def _web_fetch_run(args: dict) -> ToolOutcome:
    url = (args.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return ToolOutcome(text="请提供 http(s) URL")
    try:
        r = httpx.get(url, timeout=15, follow_redirects=True, headers={"User-Agent": "WorkBuddy/0.1"})
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


# name → (instructions, tools)
SKILLS: dict[str, tuple[str, list[Tool]]] = {
    "Web Access（浏览器自动化）": ("需要联网信息时，用 web_fetch 抓取网页内容再作答；引用来源 URL。", [web_fetch]),
    "MarkItDown": ("把提供的文档 / 网页内容整理成干净、结构化的 Markdown（标题层级、列表、表格）。", []),
    "技能创建指南": ("当用户想创建自定义技能时，说明技能 = 提示词 + 工具包 的结构，并给出可落地的模板。", []),
    "Word 文档生成": ("以规范的长文档结构组织输出：清晰的标题层级、要点、必要的表格与结论。", []),
    "Excel 文件处理": ("处理表格数据时用清晰的表格 / CSV 结构表达，注意表头、字段类型与单位。", []),
    "股票综合分析器": ("做股票分析时分三维展开：基本面、消息面、资金面，结论先行并提示风险。", []),
}


def skill_def(name: str) -> tuple[str, list[Tool]]:
    return SKILLS.get(name, (f"运用「{name}」技能的专长完成相关任务。", []))
