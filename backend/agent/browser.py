"""Safe persistent-browser tools backed by system Edge/Chrome (WB-244).

The R1 boundary is intentionally read-only at the network layer: navigation,
form filling and downloads are allowed, but every non-GET/HEAD/OPTIONS request
is aborted. R2 will add user-issued approval tokens before network writes.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
from pathlib import Path
import socket
import threading
from typing import Any, Callable
from urllib.parse import urlparse

from agent import security
from agent.sandbox import relpath, resolve_in_sandbox
from config import settings

MAX_TEXT = 12_000
_locks: dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()
_dns_cache: dict[str, bool] = {}
_FAKE_IP_NET = ipaddress.ip_network("198.18.0.0/15")


class BrowserUnavailable(RuntimeError):
    pass


class BrowserPolicyError(PermissionError):
    pass


def _lock(owner_id: str) -> threading.RLock:
    with _locks_guard:
        return _locks.setdefault(owner_id, threading.RLock())


def _browser_executable() -> Path:
    candidates = [
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise BrowserUnavailable("未找到本机 Microsoft Edge 或 Google Chrome")


def _profile(owner_id: str) -> Path:
    digest = hashlib.sha256(owner_id.encode("utf-8")).hexdigest()[:24]
    # Never place cookies/storage state under the agent workspace: list_dir/read_file
    # are intentionally available to the model. DB-adjacent local data is outside
    # every sandbox root and remains backend-only.
    profile = settings.DB_PATH.parent / ".browser-profiles" / digest
    profile.mkdir(parents=True, exist_ok=True)
    return profile


def _public_hostname(hostname: str) -> bool:
    host = hostname.rstrip(".").lower()
    if not host or host == "localhost" or host.endswith((".localhost", ".local")) or "." not in host:
        return False
    if host in _dns_cache:
        return _dns_cache[host]
    try:
        literal = ipaddress.ip_address(host)
        result = literal.is_global and literal not in _FAKE_IP_NET
    except ValueError:
        try:
            addresses = {ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(host, None)}
        except (OSError, ValueError):
            result = False
        else:
            # Clash/Mihomo fake-ip mode maps public names into 198.18/15. It is a
            # proxy placeholder, not a destination permission; literal 198.18 IPs
            # remain blocked by the branch above.
            result = bool(addresses) and all(addr.is_global or addr in _FAKE_IP_NET for addr in addresses)
    _dns_cache[host] = result
    return result


def validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise BrowserPolicyError("浏览器只允许公共 HTTP(S) URL")
    if parsed.username or parsed.password:
        raise BrowserPolicyError("URL 不得包含账号或密码")
    if not _public_hostname(parsed.hostname):
        raise BrowserPolicyError("已阻止 localhost、私网、链路本地或非全局地址")
    return url


def _state_path(profile: Path) -> Path:
    return profile / "agentmate-state.json"


def _storage_path(profile: Path) -> Path:
    return profile / "agentmate-storage-state.json"


def _remember_url(profile: Path, url: str) -> None:
    state = _state_path(profile)
    temp = state.with_suffix(".tmp")
    temp.write_text(json.dumps({"url": url}, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, state)


def _last_url(profile: Path) -> str | None:
    try:
        return str(json.loads(_state_path(profile).read_text(encoding="utf-8")).get("url") or "") or None
    except (OSError, ValueError, TypeError):
        return None


def _request_allowed(url: str) -> bool:
    if url.startswith(("data:", "blob:", "about:")):
        return True
    try:
        validate_url(url)
        return True
    except BrowserPolicyError:
        return False


def _run_page(
    fn: Callable[[Any, Path], dict[str, Any]], *, allow_network_write: bool = False,
) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    owner = security.current_owner()
    if not owner:
        raise BrowserPolicyError("缺少浏览器 owner 上下文")
    profile = _profile(owner)
    with _lock(owner), sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(profile), executable_path=str(_browser_executable()), headless=True,
            accept_downloads=True, viewport={"width": 1440, "height": 1000},
            args=["--disable-background-networking", "--no-first-run"],
        )
        # Persistent Chromium profiles do not flush cookies deterministically on
        # every short headless lifetime. Keep an explicit owner-local storage
        # snapshot as the authoritative replay source; it never crosses the API.
        try:
            stored = json.loads(_storage_path(profile).read_text(encoding="utf-8"))
            if stored.get("cookies"):
                context.add_cookies(stored["cookies"])
        except (OSError, ValueError, TypeError):
            pass

        def route_request(route) -> None:
            request = route.request
            if not _request_allowed(request.url):
                route.abort("blockedbyclient")
            elif not allow_network_write and request.method.upper() not in {"GET", "HEAD", "OPTIONS"}:
                route.abort("blockedbyclient")
            else:
                route.continue_()

        context.route("**/*", route_request)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            result = fn(page, profile)
            if page.url and page.url != "about:blank":
                _remember_url(profile, page.url)
            return result
        finally:
            storage = _storage_path(profile)
            temp_storage = storage.with_suffix(".tmp")
            context.storage_state(path=str(temp_storage))
            os.replace(temp_storage, storage)
            context.close()


def _page_summary(page) -> dict[str, Any]:
    text = page.locator("body").inner_text(timeout=10_000)
    links = page.locator("a[href]").evaluate_all(
        "els => els.slice(0,50).map(e => ({text:(e.innerText||'').trim().slice(0,120), href:e.href}))"
    )
    controls = page.locator("input, textarea, select, button").evaluate_all(
        "els => els.slice(0,80).map(e => ({tag:e.tagName.toLowerCase(), type:e.type||'', name:e.name||'', "
        "label:(e.getAttribute('aria-label')||e.innerText||e.placeholder||'').trim().slice(0,120)}))"
    )
    return {"url": page.url, "title": page.title(), "text": text[:MAX_TEXT], "links": links, "controls": controls}


def _screenshot(page, path: str) -> dict[str, Any]:
    target = resolve_in_sandbox(path)
    if target.suffix.lower() != ".png":
        raise BrowserPolicyError("截图路径必须以 .png 结尾")
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f".{target.stem}.tmp.png")
    try:
        page.screenshot(path=str(temp), full_page=True)
        os.replace(temp, target)
    finally:
        if temp.exists():
            temp.unlink()
    viewport = page.viewport_size or {}
    return {
        "path": relpath(target), "kind": "screenshot",
        "validation": {"format": "png", "width": viewport.get("width"), "height": viewport.get("height")},
    }


def navigate(args: dict[str, Any]) -> dict[str, Any]:
    url = validate_url(str(args["url"]))

    def action(page, _profile_path):
        page.goto(url, wait_until="domcontentloaded", timeout=min(60_000, int(args.get("timeout_ms") or 30_000)))
        validate_url(page.url)
        result = _page_summary(page)
        artifacts = []
        if args.get("screenshot_path"):
            artifacts.append(_screenshot(page, str(args["screenshot_path"])))
        result["artifacts"] = artifacts
        return result

    return _run_page(action)


def read(args: dict[str, Any]) -> dict[str, Any]:
    def action(page, profile):
        url = str(args.get("url") or _last_url(profile) or "")
        if not url:
            raise BrowserPolicyError("没有可读取的页面，请先 browser_navigate")
        validate_url(url)
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        validate_url(page.url)
        return _page_summary(page)

    return _run_page(action)


def _is_submit(locator) -> bool:
    return bool(locator.evaluate(
        "e => { const t=(e.type||'').toLowerCase(); const tag=e.tagName.toLowerCase(); "
        "const role=(e.getAttribute('role')||'').toLowerCase(); "
        "return t==='submit'||role==='submit'||(tag==='button' && t!=='button'); }"
    ))


def interact(args: dict[str, Any]) -> dict[str, Any]:
    actions = (args.get("actions") or [])[:50]

    def action(page, profile):
        url = str(args.get("url") or _last_url(profile) or "")
        if not url:
            raise BrowserPolicyError("没有可交互的页面，请先 browser_navigate")
        validate_url(url)
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        performed = []
        artifacts = []
        for index, spec in enumerate(actions):
            kind = str(spec.get("type") or "").lower()
            selector = str(spec.get("selector") or "")
            if kind in {"submit", "press_enter"}:
                return {"confirmation_required": True, "blocked_action": index, "performed": performed,
                        "reason": "外部提交需等待 R2 用户审批令牌，当前未执行",
                        "url": page.url, "title": page.title(), "artifacts": artifacts}
            if kind == "fill":
                page.locator(selector).fill(str(spec.get("value") or ""))
            elif kind == "select":
                page.locator(selector).select_option(str(spec.get("value") or ""))
            elif kind in {"check", "uncheck"}:
                getattr(page.locator(selector), kind)()
            elif kind == "click":
                locator = page.locator(selector)
                if _is_submit(locator):
                    return {"confirmation_required": True, "blocked_action": index, "performed": performed,
                            "reason": "检测到 submit 控件，当前未点击",
                            "url": page.url, "title": page.title(), "artifacts": artifacts}
                locator.click()
                page.wait_for_load_state("domcontentloaded", timeout=30_000)
            elif kind == "upload":
                upload = resolve_in_sandbox(str(spec.get("path") or ""))
                if not upload.is_file():
                    raise FileNotFoundError(upload)
                page.locator(selector).set_input_files(str(upload))
            elif kind == "screenshot":
                artifacts.append(_screenshot(page, str(spec.get("path") or "browser.png")))
            elif kind == "download":
                target = resolve_in_sandbox(str(spec.get("path") or ""))
                target.parent.mkdir(parents=True, exist_ok=True)
                with page.expect_download(timeout=30_000) as pending:
                    page.locator(selector).click()
                download = pending.value
                temp = target.with_name(f".{target.name}.tmp")
                try:
                    download.save_as(str(temp))
                    os.replace(temp, target)
                finally:
                    if temp.exists():
                        temp.unlink()
                artifacts.append({"path": relpath(target), "kind": "download", "validation": {"suggested_filename": download.suggested_filename}})
            else:
                raise BrowserPolicyError(f"未知浏览器动作：{kind}")
            performed.append({"type": kind, "selector": selector})
        result = _page_summary(page)
        result.update({"performed": performed, "artifacts": artifacts, "confirmation_required": False})
        return result

    return _run_page(action, allow_network_write=False)
