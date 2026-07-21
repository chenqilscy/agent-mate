# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the AgentMate backend sidecar.
# uvicorn and mcp import their impl modules dynamically, so collect them; the
# mcp_servers subpackage is bundled so the `--mcp-server=<name>` re-exec works.
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hidden = []
datas = []
hidden += collect_submodules('uvicorn')
# Skip mcp.cli — it imports optional `typer`, which we don't ship (we use the
# stdio client + FastMCP server only).
hidden += collect_submodules('mcp', filter=lambda n: not n.startswith('mcp.cli'))
hidden += collect_submodules('anyio')
# Langfuse v4 loads its generated API/OTel modules dynamically. It is runtime
# optional but shipped in the sidecar so enabling it never requires local Python.
hidden += collect_submodules(
    'langfuse',
    filter=lambda n: not n.startswith(('langfuse.langchain', 'langfuse.openai')),
)
hidden += ['mcp_servers', 'mcp_servers.notes', 'mcp_servers.clock', 'mcp_servers.search']
hidden += ['httptools', 'websockets', 'h11', 'sniffio', 'click', 'dotenv']
# Dedicated office artifacts (WB-243). docx/pptx/reportlab load templates,
# schemas and fonts from package data at runtime, so ship both code and data.
for package in ('docx', 'openpyxl', 'pptx', 'reportlab', 'pypdf'):
    hidden += collect_submodules(package)
for package in ('docx', 'pptx', 'reportlab'):
    datas += collect_data_files(package)

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'PySide6', 'PyQt5', 'PyQt6', 'matplotlib', 'pandas'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='agentmate-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
