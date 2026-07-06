"""金山文档 连接器 · WPS OAuth 授权（连接 / 状态 / 断开）。

「连接」走真实的 WPS OAuth：后端 spawn `kdocs-cli auth login`，它会打开浏览器到
WPS 授权页（openclaw 回调），用户授权后 Token 自动存入系统密钥链；此后 kdocs 桥接
（mcp_servers/kdocs.py）在无 `KDOCS_TOKEN` 时回退用密钥链里的 Token，连接器即可用。

关键机制（实测得来）：
- `auth login` 把授权 URL 打到 **stderr**（且立即 flush），把最终 Token 打到 stdout。
  我们只从 stderr 抓 URL 当作前端的「手动打开」兜底，stdout 丢弃到 DEVNULL——Token 只进
  系统密钥链，绝不进后端进程内存 / 日志 / 前端（hard-line #4）。
- 已登录 WPS 的用户，`auth login` 会自动完成（浏览器静默授权），所以 /connect 里再探一次
  状态可能直接就是 connected。
- 端点用同步 `def`（FastAPI 丢线程池跑），阻塞的子进程调用不会卡事件循环（WB-002）。
"""
from __future__ import annotations

import json
import re
import subprocess
import threading
import time

from fastapi import APIRouter, HTTPException

# Reuse the bridge's executable resolver + secret-free subprocess env (WB-011).
from mcp_servers.kdocs import _cli, _safe_env

router = APIRouter(prefix="/api/connectors/kdocs", tags=["kdocs"])

# The WPS OAuth URL that `auth login` prints to stderr.
_URL_RE = re.compile(r"https://account\.wps\.cn/\S+")

# One in-flight login at a time (local-first, single machine). Guards a tiny bit
# of shared state between the /connect request thread and the login worker thread.
_lock = threading.Lock()
_login: dict[str, object] = {"running": False, "url": None, "error": None}


def _authed(exe: str) -> bool:
    """True if kdocs-cli currently has a valid Token (env / keychain)."""
    try:
        p = subprocess.run(
            [exe, "auth", "status", "--output", "json"],
            capture_output=True, timeout=15, env=_safe_env(), stdin=subprocess.DEVNULL,
        )
    except Exception:  # noqa: BLE001
        return False
    try:
        return json.loads(p.stdout.decode("utf-8", "replace")).get("authenticated") is True
    except Exception:  # noqa: BLE001
        return False


def _login_worker(exe: str, env: dict[str, str]) -> None:
    """Run `kdocs-cli auth login` to completion (browser OAuth → keychain).

    stdout carries the raw Token → sent to DEVNULL so it never enters our memory.
    stderr carries the auth URL banner → scanned for the WPS URL (a manual-open
    fallback for the frontend); the CLI also opens the browser itself.
    """
    try:
        proc = subprocess.Popen(
            [exe, "auth", "login"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env=env,
        )
        assert proc.stderr is not None
        for raw in proc.stderr:
            m = _URL_RE.search(raw.decode("utf-8", "replace"))
            if m:
                with _lock:
                    _login["url"] = m.group(0)
        proc.wait()
    except Exception as e:  # noqa: BLE001
        with _lock:
            _login["error"] = str(e)
    finally:
        with _lock:
            _login["running"] = False


@router.get("/status")
def status() -> dict:
    exe = _cli()
    if not exe:
        return {"installed": False, "authenticated": False}
    return {"installed": True, "authenticated": _authed(exe)}


@router.post("/connect")
def connect() -> dict:
    """Start (or observe) the WPS OAuth login. Returns:
    - {status: 'connected'}                already authorized
    - {status: 'pending', authUrl: <url>}  browser opened; poll /status until done
    """
    exe = _cli()
    if not exe:
        raise HTTPException(400, "未安装 kdocs-cli（金山文档命令行工具）。请先安装再连接。")
    if _authed(exe):
        return {"status": "connected", "authUrl": None}

    with _lock:
        if not _login["running"]:
            _login.update(running=True, url=None, error=None)
            threading.Thread(target=_login_worker, args=(exe, _safe_env()), daemon=True).start()

    # Wait briefly for the URL (stderr flushes it fast) or for an auto-completed login.
    for _ in range(30):  # ~6s
        with _lock:
            if _login["url"] or _login["error"] or not _login["running"]:
                break
        time.sleep(0.2)

    with _lock:
        err = _login["error"]
        url = _login["url"]
    if err:
        raise HTTPException(500, f"启动金山文档授权失败：{err}")
    # An already-signed-in WPS user gets auto-approved within the wait above.
    if _authed(exe):
        return {"status": "connected", "authUrl": None}
    return {"status": "pending", "authUrl": url}


@router.post("/disconnect")
def disconnect() -> dict:
    exe = _cli()
    if not exe:
        raise HTTPException(400, "未安装 kdocs-cli")
    try:
        subprocess.run(
            [exe, "auth", "logout"], capture_output=True, timeout=15,
            env=_safe_env(), stdin=subprocess.DEVNULL,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"断开金山文档连接失败：{e}") from e
    return {"status": "disconnected"}
