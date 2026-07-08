"""SkillHub CLI 客户端（WB-069）—— Hub 侧复用本机 skillhub CLI 抓目录/查询。

不新起 HTTP 客户端：跑 `~/.skillhub/skills_store_cli.py`（Hub 自己的 Python）。移植自
`backend/agent/skills_store.py` 的硬化封装：白名单转发 env（**绝不透传密钥**，铁律#4）、
强制 `PYTHONUTF8` 避 GBK 崩、失败降级。**安装动作不在 Hub 做**（永远留本地）。

取数策略：
- **镜像同步** `skill rankings --type all` → 6 榜单富卡（下载/星/评分/图标/分类齐全，CLI 原样透传）。
- **查询代理** `search(q)` → **优先直连 `/api/v1/search`**（富字段：下载/星/图标齐全，WB-069 富查询增强）；
  直连失败再回退 CLI `search`（CLI 只保留 slug/name/description/version，富字段缺失但仍可用）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from config import settings

# 白名单转发（与 backend 一致）：绝不把整个 os.environ（含密钥）透传给子进程（铁律#4 / WB-011）。
_SAFE_ENV_KEYS = {
    "SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "TEMP", "TMP", "TMPDIR",
    "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "HOMEDRIVE", "HOMEPATH",
    "LANG", "LC_ALL", "LC_CTYPE",
}


def _cli_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k.upper() in _SAFE_ENV_KEYS}
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["SKILLHUB_SKIP_SELF_UPGRADE"] = "true"  # 服务端不做交互式自升级
    # SkillHub 自己的凭据注入 SkillHub CLI（仅给它，不透传 os.environ；铁律#4/WB-011，WB-095）。
    key = _stored_key()
    if key:
        env["SKILLHUB_API_KEY" if key.startswith("sk-ent-") else "SKILLHUB_TOKEN"] = key
    return env


def _stored_key() -> str:
    """SkillHub API key（WB-095）：优先 Hub 库里的平台设置，env 兜底。skh_ 个人 / sk-ent- 企业。"""
    try:
        import db  # 延迟导入避免 import 期耦合
        v = db.get_setting("skillhub_api_key")
        if v:
            return v.strip()
    except Exception:  # noqa: BLE001 —— 库不可用不阻断取数
        pass
    return (os.getenv("SKILLHUB_TOKEN") or os.getenv("SKILLHUB_API_KEY") or "").strip()


def cli_available() -> bool:
    return settings.SKILLHUB_CLI.is_file()


def _work_dir():
    d = settings.SKILLHUB_WORK_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _run_cli(args: list[str], timeout: int = 90) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(settings.SKILLHUB_CLI), "--skip-self-upgrade", *args]
    return subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=_cli_env(), timeout=timeout, cwd=str(_work_dir()),
    )


def _to_int(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _normalize_card(x: dict[str, Any]) -> dict[str, Any]:
    """把 rankings/search 的一条归一化成前端可直接渲染的商品卡（同 backend 口径）。"""
    return {
        "slug": str(x.get("slug") or "").strip(),
        "name": str(x.get("name") or x.get("displayName") or "").strip(),
        "description": str(x.get("description_zh") or x.get("description") or x.get("summary") or "").strip(),
        "version": str(x.get("version") or "").strip(),
        "category": str(x.get("category") or "").strip(),
        "subCategories": x.get("subCategories") or [],
        "downloads": _to_int(x.get("downloads")),
        "installs": _to_int(x.get("installs")),
        "stars": _to_int(x.get("stars")),
        "score": x.get("score"),
        "iconUrl": str(x.get("iconUrl") or x.get("icon_url") or "").strip(),
        "tags": x.get("tags") or [],
        "verified": bool(x.get("verified")),
        "source": str(x.get("source") or "skillhub").strip(),
        # 发布/更新时间（ms epoch）——HTTP showcase/search 带，CLI 无。支撑「最近上新」排序（WB-092/094）。
        "created_at": _to_int(x.get("created_at") or x.get("createdAt")),
        "updated_at": _to_int(x.get("updated_at") or x.get("updatedAt")),
    }


_API_BASE = os.getenv("SKILLHUB_API_BASE", "https://api.skillhub.cn").rstrip("/")
_SHOWCASE = ("hot", "featured", "newest", "recommended", "trending", "paid")


def _http_json(url: str, key: str = "", timeout: int = 15) -> Any:
    headers = {"User-Agent": "workbuddy-hub/0.1", "Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_rankings() -> list[dict[str, Any]]:
    """直连 6 个 `showcase/*` 端点（WB-094）→ 展平去重归一化（含 created_at）。全空则抛，由上层回退 CLI。

    配了 API key（WB-095）则带 Bearer——可解锁 paid showcase / 企业条目。
    """
    key = _stored_key()
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for name in _SHOWCASE:
        try:
            d = _http_json(f"{_API_BASE}/api/v1/showcase/{name}?limit=500", key)
        except (urllib.error.URLError, OSError, ValueError, TimeoutError):
            continue  # 单个 showcase 失败不影响其它
        skills = (d.get("skills") or d.get("featured_paid_skills") or []) if isinstance(d, dict) else []
        for x in skills:
            if not isinstance(x, dict):
                continue
            slug = str(x.get("slug") or "").strip()
            if not slug or slug in seen:
                continue
            seen.add(slug)
            out.append(_normalize_card(x))
    if not out:
        raise ValueError("showcase HTTP 全空")
    return out


def rankings_all() -> list[dict[str, Any]]:
    """镜像目录：优先直连 HTTP showcase（无需 CLI、带 created_at，WB-094），失败回退 CLI。"""
    try:
        return _http_rankings()
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return _cli_rankings()


def _cli_rankings() -> list[dict[str, Any]]:
    """回退：跑 `skill rankings --type all` → 展平 6 榜单、按 slug 去重、归一化。失败返回 []。

    形态：`{"rankings": {hot|featured|newest|recommended|trending: {section,skills,total},
    paid: {featured_merchants, featured_paid_skills}}}`。paid 用 `featured_paid_skills` 键。
    """
    if not cli_available():
        return []
    try:
        cp = _run_cli(["skill", "rankings", "--type", "all"], timeout=90)
        d = json.loads((cp.stdout or "").strip())
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return []
    ranks = d.get("rankings") if isinstance(d, dict) else None
    if not isinstance(ranks, dict):
        ranks = {"_": d} if isinstance(d, dict) else {}
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for _key, resp in ranks.items():
        if not isinstance(resp, dict):
            continue
        skills = resp.get("skills") or resp.get("featured_paid_skills") or []
        if not isinstance(skills, list):
            continue
        for x in skills:
            if not isinstance(x, dict):
                continue
            slug = str(x.get("slug") or "").strip()
            if not slug or slug in seen:
                continue
            seen.add(slug)
            out.append(_normalize_card(x))
    return out


# 查询代理：短 TTL 缓存（降低对站点压力 + 加速重复查询）。
_SEARCH_TTL = 120.0
_search_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
# 社区搜索接口（与 CLI 的 DEFAULT_SEARCH_URL 一致）；env 可覆盖。
_SEARCH_URL = os.getenv("SKILLHUB_SEARCH_URL", "https://api.skillhub.cn/api/v1/search")
_UA = "workbuddy-hub/0.1"


def _http_search(q: str, limit: int) -> list[dict[str, Any]]:
    """直连 `/api/v1/search`（富字段：下载/星/图标/分类齐全）。失败抛异常，由 search() 兜底。"""
    params = urllib.parse.urlencode({"q": q, "limit": max(1, int(limit))})
    raw = _http_json(f"{_SEARCH_URL}?{params}", _stored_key(), timeout=10)
    results = raw.get("results") if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
    if not isinstance(results, list):
        return []
    return [_normalize_card(x) for x in results if isinstance(x, dict) and x.get("slug")]


def _cli_search(q: str, limit: int) -> list[dict[str, Any]]:
    """回退路径：跑 CLI `search`（字段精简，无下载/星）。失败返回 []。"""
    if not cli_available():
        return []
    try:
        cp = _run_cli(["search", q, "--json", "--search-limit", str(max(1, int(limit)))], timeout=45)
        d = json.loads((cp.stdout or "").strip())
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return []
    results = d.get("results") if isinstance(d, dict) else (d if isinstance(d, list) else [])
    if not isinstance(results, list):
        return []
    return [_normalize_card(x) for x in results if isinstance(x, dict) and x.get("slug")]


def search(q: str, limit: int = 12) -> list[dict[str, Any]]:
    """查询代理：先直连 `/api/v1/search`（富字段），失败回退 CLI，再失败回退缓存/空。"""
    q = (q or "").strip()
    if not q:
        return []
    key = f"{q}::{limit}"
    hit = _search_cache.get(key)
    if hit and (time.time() - hit[0]) < _SEARCH_TTL:
        return hit[1]
    out: list[dict[str, Any]] = []
    try:
        out = _http_search(q, limit)
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        out = []
    if not out:
        out = _cli_search(q, limit)  # 直连失败 → CLI 兜底
    if not out:
        return hit[1] if hit else []  # 都失败 → 保留上次缓存
    _search_cache[key] = (time.time(), out)
    return out
