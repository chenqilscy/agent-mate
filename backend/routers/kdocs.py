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


def _run_json(exe: str, service: str, action: str, params: dict, timeout: float = 30.0) -> tuple[bool, object]:
    """Run one kdocs-cli <service> <action> and parse its JSON envelope.

    Returns (ok, data_or_errtext). stdout carries the clean JSON envelope
    ({code,data,message}); the upgrade-notice banner goes to stderr, so parsing
    stdout alone is safe. exit code is 0 even on API error — trust `code`, not it.
    """
    args = [exe, service, action, "--output", "json", "--args", json.dumps(params, ensure_ascii=False)]
    try:
        p = subprocess.run(
            args, capture_output=True, timeout=timeout, env=_safe_env(), stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return False, f"调用超时（>{int(timeout)}s）"
    except Exception as e:  # noqa: BLE001
        return False, str(e)
    text = p.stdout.decode("utf-8", "replace").strip()
    if not text:
        return False, (p.stderr.decode("utf-8", "replace").strip() or "kdocs-cli 无输出")
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return False, "kdocs-cli 返回非 JSON"
    if isinstance(obj, dict) and obj.get("code") not in (0, None):
        return False, f"金山文档接口错误 code={obj.get('code')}：{obj.get('message') or '未知错误'}"
    return True, (obj.get("data") if isinstance(obj, dict) else obj)


def _items(data: object) -> list[dict]:
    """Dig the items[] list out of a search / latest-items result (nested envelope)."""
    node = data
    while isinstance(node, dict) and "items" not in node and "data" in node:
        node = node["data"]
    if isinstance(node, dict):
        got = node.get("items")
        return got if isinstance(got, list) else []
    return []


def _norm(it: dict, keep_folders: bool = False) -> dict | None:
    """Normalize one item (its `.file` sub-object) for the panel.

    keep_folders=False (最近/搜索): drop 文件夹, only real files.
    keep_folders=True (目录浏览): also yield folders, flagged is_folder so the UI
    can render a drill-in row instead of an open-link row.
    """
    f = it.get("file") if isinstance(it.get("file"), dict) else it
    if not isinstance(f, dict):
        return None
    typ = f.get("type")
    is_folder = typ == "folder"
    if typ != "file" and not (keep_folders and is_folder):
        return None
    name = str(f.get("name") or "")
    ext = "" if is_folder else (name.rsplit(".", 1)[-1].lower() if "." in name else "")
    creator = f.get("created_by") if isinstance(f.get("created_by"), dict) else {}
    return {
        "name": name,
        "file_id": str(f.get("id") or ""),
        "drive_id": str(f.get("drive_id") or ""),
        "parent_id": str(f.get("parent_id") or ""),
        "link_url": str(f.get("link_url") or ""),
        "ext": ext,
        "is_folder": is_folder,
        "mtime": int(f.get("mtime") or 0),
        "size": int(f.get("size") or 0),
        "owner": str(creator.get("name") or ""),
    }


def _personal_root_drive(exe: str) -> str:
    """Discover the 我的云文档 (personal cloud) root drive_id — never hardcoded.

    The installed CLI (v2.5.11) has no root-listing action, but every 最近访问 item
    carries `file_src.name` (its location, e.g. 我的云文档 / 我的漫游箱 / <知识库>).
    We pick the drive_id of the first item located in 我的云文档; `list-files` on it
    with parent_id="0" is that tree's root. Empty string if none found.
    """
    ok, data = _run_json(exe, "drive", "list-latest-items", {"page_size": 60})
    if not ok:
        return ""
    for it in _items(data):
        f = it.get("file") if isinstance(it.get("file"), dict) else {}
        src = it.get("file_src") if isinstance(it.get("file_src"), dict) else {}
        if src.get("name") == "我的云文档" and f.get("drive_id"):
            return str(f["drive_id"])
    return ""


@router.get("/files")
def files(keyword: str = "", kind: str = "recent", page_size: int = 30) -> dict:
    """List the user's 金山文档 (flat): recent / starred, or a search when keyword given.

    kind: `recent` (list-latest-items, 最近访问) or `star` (list-star-items, 收藏/星标).
    A non-empty keyword always searches, regardless of kind. (No 共享/shared-with-me:
    the installed kdocs-cli has no such action — 铁律#1, so we don't fake that tab.)
    Honest degradation: not installed / not authorized come back as flags the panel
    can act on, not a 500.
    """
    exe = _cli()
    if not exe:
        return {"installed": False, "authenticated": False, "files": []}
    if not _authed(exe):
        return {"installed": True, "authenticated": False, "files": []}
    size = max(1, min(int(page_size or 30), 100))
    kw = keyword.strip()
    if kw:
        ok, data = _run_json(exe, "drive", "search-files", {"keyword": kw, "type": "all", "page_size": size})
    elif kind == "star":
        ok, data = _run_json(exe, "drive", "list-star-items", {"page_size": size})
    else:
        ok, data = _run_json(exe, "drive", "list-latest-items", {"page_size": size})
    if not ok:
        raise HTTPException(502, str(data))
    out = [n for it in _items(data) if (n := _norm(it))]
    return {"installed": True, "authenticated": True, "files": out}


@router.get("/folder")
def folder(drive_id: str = "", parent_id: str = "0", page_size: int = 100) -> dict:
    """Browse the 我的云文档 folder tree (mirrors the WPS web 我的云文档 sidebar).

    drive_id empty → auto-discover the personal-cloud root (see _personal_root_drive)
    and list its root (parent_id="0"); otherwise list the given folder. Folders come
    first, then files. Returns the resolved drive_id so the client can drill deeper.
    """
    exe = _cli()
    if not exe:
        return {"installed": False, "authenticated": False, "drive_id": "", "files": []}
    if not _authed(exe):
        return {"installed": True, "authenticated": False, "drive_id": "", "files": []}
    drive = drive_id.strip() or _personal_root_drive(exe)
    if not drive:
        # No personal-cloud drive discoverable (e.g. empty account) — honest empty,
        # not a crash; the panel shows 暂无 and the user can still use 最近/搜索.
        return {"installed": True, "authenticated": True, "drive_id": "", "files": []}
    size = max(1, min(int(page_size or 100), 200))
    ok, data = _run_json(exe, "drive", "list-files",
                         {"drive_id": drive, "parent_id": parent_id or "0", "page_size": size})
    if not ok:
        raise HTTPException(502, str(data))
    items = [n for it in _items(data) if (n := _norm(it, keep_folders=True))]
    items.sort(key=lambda x: (not x["is_folder"], x["name"].lower()))  # folders first
    return {"installed": True, "authenticated": True, "drive_id": drive, "files": items}


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
