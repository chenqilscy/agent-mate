"""Built-in local MCP servers, and a dispatcher so they can run as a subcommand.

In dev, the MCP client spawns each server as `python mcp_servers/<name>.py`. In a
PyInstaller bundle there's no python interpreter to run a .py, so the client
instead re-execs the app itself as `WorkBuddy.exe --mcp-server=<name>`, which
main.py routes here. Same FastMCP servers, launched two ways.
"""
from __future__ import annotations

# connector name / cli name → module holding a FastMCP `mcp` object.
_SERVERS = {"notes", "clock", "search", "telegram"}


def run_mcp_server(name: str) -> None:
    if name == "notes":
        from mcp_servers.notes import mcp
    elif name == "clock":
        from mcp_servers.clock import mcp
    elif name == "search":
        from mcp_servers.search import mcp
    elif name == "telegram":
        from mcp_servers.telegram import mcp
    else:
        raise SystemExit(f"unknown mcp server: {name}")
    mcp.run()
