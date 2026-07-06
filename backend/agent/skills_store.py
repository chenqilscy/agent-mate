"""SkillHub 已安装技能的真实读写（WB-055）。

一个 skill = `SKILLS_DIR/<dir>/SKILL.md`（+ 可选 _meta.json / _skillhub_meta.json /
references/），和出货版 WorkBuddy 及 skillhub CLI 的落盘约定一致。这里做的是**真实**的：
- scan()      扫描目录，解析 SKILL.md front-matter 得到已安装技能清单；
- install()   用后端自己的 Python 直接跑 skillhub CLI 真正下载解压进 SKILLS_DIR；
- uninstall() 删目录；set_disabled() 写/删 .disabled 标记；reveal() 打开资源管理器；
- instructions_for() 供 runtime 在技能进 loadout 时注入其 SKILL.md 正文（真生效）。

不模拟：清单来自磁盘真实文件，安装来自真实 CLI 下载，注入的是真实 SKILL.md。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from config import settings

SKILL_MD = "SKILL.md"
SKILLHUB_META = "_skillhub_meta.json"
PUB_META = "_meta.json"
DISABLED_MARKER = ".disabled"
_MAX_INJECT = 6000  # 注入系统提示时单技能正文上限，控 token


def skills_dir() -> Path:
    d = settings.SKILLS_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_dir(key: str) -> Path | None:
    """把外部传入的 key（目录名）安全解析为 SKILLS_DIR 下的直接子目录，挡路径穿越。"""
    key = (key or "").strip()
    if not key:
        return None
    root = skills_dir()
    p = (root / key).resolve()
    if p.parent != root or not p.is_dir():
        return None
    return p


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:  # noqa: BLE001 — 坏/缺文件都当空
        return {}


def _scalar(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
        return s[1:-1]
    return s


def _split_inline_list(inner: str) -> list[str]:
    """拆 `[a, "b,c", d]` 里的逗号（引号内的逗号不算）。"""
    out: list[str] = []
    cur = ""
    quote: str | None = None
    for ch in inner:
        if quote:
            cur += ch
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            cur += ch
        elif ch == ",":
            out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur)
    return [_scalar(x) for x in out if x.strip()]


# 极简 YAML-front-matter 解析（不引入 PyYAML 依赖）：够覆盖 SKILL.md 的
# key: value / key: [inline list] / key:\n  - block list。复杂结构忽略。
_KEY_RE = re.compile(r"^([A-Za-z0-9_-]+):[ \t]*(.*)$")
_ITEM_RE = re.compile(r"^[ \t]+-[ \t]*(.*)$")


def parse_frontmatter(md: str) -> tuple[dict[str, Any], str]:
    """拆 SKILL.md：返回 (front-matter dict, 正文)。无 front-matter 则 ({}, 全文)。"""
    if md.startswith("﻿"):
        md = md[1:]
    m = re.match(r"^---[ \t]*\n(.*?)\n---[ \t]*\n?(.*)$", md, re.S)
    if not m:
        return {}, md
    fm: dict[str, Any] = {}
    lines = m.group(1).split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        km = _KEY_RE.match(line)
        if not km:
            i += 1
            continue
        key, val = km.group(1), km.group(2).strip()
        if val == "":
            items: list[str] = []
            j = i + 1
            while j < len(lines):
                im = _ITEM_RE.match(lines[j])
                if not im:
                    break
                items.append(_scalar(im.group(1)))
                j += 1
            fm[key] = items if items else ""
            i = j if items else i + 1
        elif val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            fm[key] = _split_inline_list(inner) if inner else []
            i += 1
        else:
            fm[key] = _scalar(val)
            i += 1
    return fm, m.group(2)


def _info_from_dir(d: Path) -> dict[str, Any] | None:
    skill_md = d / SKILL_MD
    if not skill_md.is_file():
        return None
    try:
        fm, _ = parse_frontmatter(skill_md.read_text(encoding="utf-8", errors="ignore"))
    except OSError:
        return None
    sh = _read_json(d / SKILLHUB_META)
    pub = _read_json(d / PUB_META)
    slug = str(sh.get("slug") or pub.get("slug") or d.name.replace("__skillhub", "")).strip()
    name = str(sh.get("name") or fm.get("name") or d.name.replace("__skillhub", "")).strip()
    desc = str(fm.get("description") or fm.get("description_zh") or fm.get("description_en") or "").strip()
    version = str(sh.get("version") or pub.get("version") or fm.get("version") or "").strip()
    source = str(sh.get("source") or ("skillhub" if d.name.endswith("__skillhub") else "local")).strip()
    return {
        "key": d.name,
        "slug": slug,
        "name": name,
        "description": desc,
        "version": version,
        "source": source,
        "disabled": (d / DISABLED_MARKER).exists(),
    }


def scan() -> list[dict[str, Any]]:
    """已安装技能清单（按名字排序）。"""
    root = skills_dir()
    out: list[dict[str, Any]] = []
    for d in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not d.is_dir():
            continue
        info = _info_from_dir(d)
        if info:
            out.append(info)
    return out


def detail(key: str) -> dict[str, Any] | None:
    d = _safe_dir(key)
    if not d:
        return None
    info = _info_from_dir(d)
    if not info:
        return None
    try:
        raw = (d / SKILL_MD).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        raw = ""
    fm, body = parse_frontmatter(raw)
    refs: list[str] = []
    ref_dir = d / "references"
    if ref_dir.is_dir():
        refs = sorted(p.name for p in ref_dir.iterdir() if p.is_file())
    info.update({
        "markdown": raw,          # 完整 SKILL.md（含 front-matter），供源码视图
        "body": body,             # 去掉 front-matter 的正文，供预览渲染
        "frontmatter": fm,
        "references": refs,
        "dir": str(d),
    })
    return info


# ── 跑 skillhub CLI（后端自己的 Python，不依赖 bash wrapper / PATH）───────────
_SAFE_ENV_KEYS = {
    "SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "TEMP", "TMP", "TMPDIR",
    "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "HOMEDRIVE", "HOMEPATH",
    "LANG", "LC_ALL", "LC_CTYPE",
}


def _cli_env() -> dict[str, str]:
    # 白名单转发 —— 绝不把整个 os.environ（含 LLM_API_KEY）透传给子进程（WB-011）。
    env = {k: v for k, v in os.environ.items() if k.upper() in _SAFE_ENV_KEYS}
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def cli_available() -> bool:
    return settings.SKILLHUB_CLI.is_file()


def _run_cli(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(settings.SKILLHUB_CLI), "--skip-self-upgrade", *args]
    return subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=_cli_env(), timeout=timeout, cwd=str(skills_dir()),
    )


def search(query: str, limit: int = 8) -> list[dict[str, Any]]:
    """在 SkillHub 注册表搜索，返回 [{slug,name,description,version,...}]。"""
    query = (query or "").strip()
    if not query or not cli_available():
        return []
    try:
        cp = _run_cli(["search", query, "--json", "--search-limit", str(limit)], timeout=45)
    except (subprocess.TimeoutExpired, OSError):
        return []
    out = (cp.stdout or "").strip()
    try:
        data = json.loads(out)
    except Exception:  # noqa: BLE001
        return []
    items = data.get("results", data) if isinstance(data, dict) else data
    results: list[dict[str, Any]] = []
    if isinstance(items, list):
        for it in items:
            if isinstance(it, dict) and it.get("slug"):
                results.append(it)
    return results


def resolve_slug(query: str) -> str | None:
    """把展示名/关键词解析成一个 SkillHub slug：精确 slug 命中优先，否则取第一条。"""
    q = (query or "").strip()
    if not q:
        return None
    results = search(q, limit=8)
    if not results:
        return None
    for it in results:
        if str(it.get("slug", "")).strip() == q or str(it.get("name", "")).strip() == q:
            return str(it["slug"]).strip()
    return str(results[0].get("slug", "")).strip() or None


def install(slug: str, display_name: str = "") -> dict[str, Any]:
    """真正安装：跑 CLI 下载解压进 SKILLS_DIR/<slug>/。成功返回 {ok, skill}。"""
    slug = (slug or "").strip()
    if not slug:
        return {"ok": False, "error": "empty slug"}
    if not cli_available():
        return {"ok": False, "error": "SkillHub CLI 未安装（~/.skillhub/skills_store_cli.py）"}
    root = skills_dir()
    try:
        cp = _run_cli(["install", slug, "--dir", str(root), "--json", "--force"], timeout=180)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "安装超时"}
    except OSError as e:
        return {"ok": False, "error": f"启动 CLI 失败：{e}"}

    dest = (root / slug)
    ok = dest.is_dir() and (dest / SKILL_MD).is_file()
    if not ok:
        # 解析 CLI 的 JSON 报错（stdout 或 stderr）
        msg = (cp.stdout or "").strip() or (cp.stderr or "").strip() or f"exit {cp.returncode}"
        try:
            j = json.loads((cp.stdout or "").strip())
            if isinstance(j, dict) and j.get("error"):
                msg = str(j["error"])
        except Exception:  # noqa: BLE001
            pass
        return {"ok": False, "error": msg[:500]}

    # 写 _skillhub_meta.json（CLI 不写），给出好看的展示名 + 与出货版落盘一致。
    if not (dest / SKILLHUB_META).exists():
        fm, _ = parse_frontmatter((dest / SKILL_MD).read_text(encoding="utf-8", errors="ignore"))
        pub = _read_json(dest / PUB_META)
        meta = {
            "slug": slug,
            "name": (display_name or fm.get("name") or slug).strip(),
            "version": str(pub.get("version") or fm.get("version") or "").strip(),
            "installedAt": int(time.time() * 1000),
            "source": "skillhub",
        }
        try:
            (dest / SKILLHUB_META).write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass

    _invalidate_cache()
    return {"ok": True, "skill": _info_from_dir(dest)}


def uninstall(key: str) -> bool:
    d = _safe_dir(key)
    if not d:
        return False
    try:
        shutil.rmtree(d)
    except OSError:
        return False
    # 顺手清 CLI 锁文件里的条目（若有）
    lock = skills_dir() / ".skills_store_lock.json"
    raw = _read_json(lock)
    slug = key.replace("__skillhub", "")
    if isinstance(raw.get("skills"), dict) and slug in raw["skills"]:
        raw["skills"].pop(slug, None)
        try:
            lock.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except OSError:
            pass
    _invalidate_cache()
    return True


def set_disabled(key: str, disabled: bool) -> bool:
    d = _safe_dir(key)
    if not d:
        return False
    marker = d / DISABLED_MARKER
    try:
        if disabled:
            marker.write_text("", encoding="utf-8")
        elif marker.exists():
            marker.unlink()
    except OSError:
        return False
    _invalidate_cache()
    return True


def reveal(key: str) -> bool:
    """在系统文件管理器里打开该技能目录。"""
    d = _safe_dir(key)
    if not d:
        return False
    try:
        if sys.platform == "win32":
            os.startfile(str(d))  # type: ignore[attr-defined]  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(d)])
        else:
            subprocess.Popen(["xdg-open", str(d)])
        return True
    except OSError:
        return False


# ── runtime 注入（技能进 loadout → 注入其 SKILL.md 正文）────────────────────
_cache: dict[str, dict[str, Any]] | None = None


def _invalidate_cache() -> None:
    global _cache
    _cache = None


def _index() -> dict[str, dict[str, Any]]:
    """name/slug/folder/frontmatter-name → 该 skill 的目录信息 + 正文（缓存）。"""
    global _cache
    if _cache is not None:
        return _cache
    idx: dict[str, dict[str, Any]] = {}
    for d in skills_dir().iterdir() if skills_dir().exists() else []:
        if not d.is_dir() or not (d / SKILL_MD).is_file():
            continue
        try:
            raw = (d / SKILL_MD).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        fm, body = parse_frontmatter(raw)
        sh = _read_json(d / SKILLHUB_META)
        disabled = (d / DISABLED_MARKER).exists()
        entry = {"body": body.strip(), "disabled": disabled}
        keys = {
            d.name, d.name.replace("__skillhub", ""),
            str(sh.get("name") or ""), str(sh.get("slug") or ""), str(fm.get("name") or ""),
        }
        for k in keys:
            k = k.strip()
            if k:
                idx[k] = entry
    _cache = idx
    return idx


def instructions_for(name: str) -> str | None:
    """某个 loadout 技能名若对应一个已安装（且未停用）的磁盘 skill，返回其正文（截断）。"""
    entry = _index().get((name or "").strip())
    if not entry or entry.get("disabled"):
        return None
    body = entry.get("body") or ""
    if not body:
        return None
    return body if len(body) <= _MAX_INJECT else body[:_MAX_INJECT] + f"\n… [截断，共 {len(body)} 字符]"
