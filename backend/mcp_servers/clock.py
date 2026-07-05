"""时间助手 — a built-in local MCP server (stdio) giving the agent a real clock.

The LLM has no reliable sense of "now"; this exposes the host machine's current
time / date and simple date math over MCP. Zero external deps or credentials —
one of the built-in connectors that work out of the box. Run: `python clock.py`.
"""
from __future__ import annotations

import datetime as dt

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("clock")

_WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


@mcp.tool()
def now() -> str:
    """返回本机当前的日期、时间与星期。"""
    n = dt.datetime.now()
    return f"{n:%Y-%m-%d %H:%M:%S} {_WEEKDAYS[n.weekday()]}"


@mcp.tool()
def today() -> str:
    """返回今天的日期（YYYY-MM-DD）与星期。"""
    d = dt.date.today()
    return f"{d:%Y-%m-%d} {_WEEKDAYS[d.weekday()]}"


@mcp.tool()
def days_until(date: str) -> str:
    """计算从今天到给定日期（YYYY-MM-DD）还有多少天（负数表示已过去）。"""
    try:
        target = dt.date.fromisoformat(date.strip())
    except ValueError:
        return f"无法解析日期：{date}（请用 YYYY-MM-DD）"
    diff = (target - dt.date.today()).days
    if diff == 0:
        return f"{date} 就是今天。"
    if diff > 0:
        return f"距离 {date} 还有 {diff} 天。"
    return f"{date} 已过去 {-diff} 天。"


if __name__ == "__main__":
    mcp.run()
