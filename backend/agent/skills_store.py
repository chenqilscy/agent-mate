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

import base64
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

from config import settings

SKILL_MD = "SKILL.md"
SKILLHUB_META = "_skillhub_meta.json"
PUB_META = "_meta.json"
DISABLED_MARKER = ".disabled"
_MAX_INJECT = 6000  # 注入系统提示时单技能正文上限，控 token
MAX_IMPORT_BYTES = 20 * 1024 * 1024
MAX_IMPORT_FILES = 256
MAX_SKILL_MD_BYTES = 512 * 1024

# 技能 slug 白名单：仅字母数字与 . _ - ；杜绝路径分隔符与 `..`，因为 slug 会拼进
# SKILLS_DIR/<slug> 与临时预览目录路径、并作为 `skillhub install <slug>` 的子进程
# 参数（路径穿越 / CLI 参数注入面）。与 hub/skillhub_client.py 的校验保持同一口径
# ——WB-160 只硬化了 Hub 侧，App 侧这个孪生站点漏网，见 WB-185。
_SLUG_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def valid_slug(slug: str) -> bool:
    # 前导 `-` 另拒：字符集白名单挡不住 `--dir` 这类「合法字符但会被 CLI 当选项吃掉」的
    # slug（argv 传参，无 shell 注入，但可污染 skillhub CLI 的参数解析）。
    return (
        bool(slug)
        and ".." not in slug
        and not slug.startswith("-")
        and _SLUG_RE.match(slug) is not None
    )


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
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        try:
            value = json.loads(s)
            return value if isinstance(value, str) else str(value)
        except ValueError:
            return s[1:-1]
    if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
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
    m = re.match(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?(.*)$", md, re.S)
    if not m:
        return {}, md
    fm: dict[str, Any] = {}
    lines = m.group(1).splitlines()
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


class SkillImportError(ValueError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _safe_import_path(raw: str) -> PurePosixPath:
    """Normalize an uploaded archive/folder path without ever touching disk."""
    value = (raw or "").replace("\\", "/").strip()
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or any(part in {"", ".", ".."} or ":" in part or "\x00" in part for part in path.parts)
    ):
        raise SkillImportError(f"技能包包含非法路径：{raw[:120]}")
    return path


def _import_slug(frontmatter: dict[str, Any], root_hint: str, source_name: str, skill_md: bytes) -> str:
    candidates = [
        str(frontmatter.get("slug") or "").strip(),
        root_hint.strip(),
        Path(source_name).stem.strip(),
    ]
    name = str(frontmatter.get("name") or "").strip().lower()
    candidates.append(re.sub(r"[^a-z0-9._-]+", "-", name).strip("-"))
    for candidate in candidates:
        if valid_slug(candidate):
            return candidate
    return "local-" + hashlib.sha256(skill_md).hexdigest()[:12]


def _install_import_files(files: list[tuple[str, bytes]], source_name: str) -> dict[str, Any]:
    if not files:
        raise SkillImportError("未选择任何技能文件")
    if len(files) > MAX_IMPORT_FILES:
        raise SkillImportError(f"技能包文件过多（最多 {MAX_IMPORT_FILES} 个）", 413)

    normalized: dict[PurePosixPath, bytes] = {}
    total = 0
    seen_casefold: set[str] = set()
    for raw_path, data in files:
        path = _safe_import_path(raw_path)
        folded = path.as_posix().casefold()
        if folded in seen_casefold:
            raise SkillImportError(f"技能包包含重复路径：{path.as_posix()}")
        seen_casefold.add(folded)
        total += len(data)
        if total > MAX_IMPORT_BYTES:
            raise SkillImportError(f"技能包过大（最多 {MAX_IMPORT_BYTES // (1024 * 1024)}MB）", 413)
        normalized[path] = data

    manifests = [path for path in normalized if path.name.casefold() == SKILL_MD.casefold()]
    if len(manifests) != 1:
        raise SkillImportError("技能包必须包含且只能包含一个 SKILL.md")
    manifest = manifests[0]
    skill_md = normalized[manifest]
    if len(skill_md) > MAX_SKILL_MD_BYTES:
        raise SkillImportError("SKILL.md 过大（最多 512KB）", 413)
    try:
        markdown = skill_md.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SkillImportError("SKILL.md 必须使用 UTF-8 编码") from exc
    frontmatter, _ = parse_frontmatter(markdown)
    name = str(frontmatter.get("name") or "").strip()
    description = str(
        frontmatter.get("description")
        or frontmatter.get("description_zh")
        or frontmatter.get("description_en")
        or ""
    ).strip()
    if not name or not description:
        raise SkillImportError("SKILL.md 的 YAML frontmatter 必须包含 name 和 description")

    package_root = manifest.parent
    root_hint = "" if package_root == PurePosixPath(".") else package_root.name
    slug = _import_slug(frontmatter, root_hint, source_name, skill_md)
    root = skills_dir()
    target = root / slug
    if target.exists():
        raise SkillImportError(f"技能「{slug}」已存在，请先卸载或更换 slug", 409)

    staging_root = Path(tempfile.mkdtemp(prefix=".skill-import-", dir=root))
    staging = staging_root / "package"
    staging.mkdir()
    try:
        for path, data in normalized.items():
            try:
                relative = path.relative_to(package_root)
            except ValueError:
                continue
            if relative.name in {SKILLHUB_META, DISABLED_MARKER}:
                continue
            destination = staging.joinpath(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)

        meta = {
            "slug": slug,
            "name": name,
            "version": str(frontmatter.get("version") or "").strip(),
            "installedAt": int(time.time() * 1000),
            "source": "local",
        }
        (staging / SKILLHUB_META).write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(staging, target)
    except OSError as exc:
        raise SkillImportError(f"写入技能目录失败：{exc}", 500) from exc
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)

    _invalidate_cache()
    skill = _info_from_dir(target)
    if not skill:
        shutil.rmtree(target, ignore_errors=True)
        raise SkillImportError("导入后的技能无法读取", 500)
    return {"ok": True, "skill": skill}


def import_skill_file(filename: str, data: bytes) -> dict[str, Any]:
    """Import a standalone SKILL.md or a zip containing one skill tree."""
    suffix = Path(filename or "").suffix.lower()
    if suffix == ".md":
        return _install_import_files([(SKILL_MD, data)], filename)
    if suffix != ".zip":
        raise SkillImportError("仅支持 .md 或 .zip 技能文件")
    if len(data) > MAX_IMPORT_BYTES:
        raise SkillImportError(f"技能包过大（最多 {MAX_IMPORT_BYTES // (1024 * 1024)}MB）", 413)

    files: list[tuple[str, bytes]] = []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            if len(infos) > MAX_IMPORT_FILES:
                raise SkillImportError(f"技能包文件过多（最多 {MAX_IMPORT_FILES} 个）", 413)
            if sum(info.file_size for info in infos) > MAX_IMPORT_BYTES:
                raise SkillImportError(f"技能包解压后过大（最多 {MAX_IMPORT_BYTES // (1024 * 1024)}MB）", 413)
            for info in infos:
                mode = (info.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    raise SkillImportError("技能包不能包含符号链接")
                if info.flag_bits & 0x1:
                    raise SkillImportError("不支持加密的技能包")
                files.append((info.filename, archive.read(info)))
    except zipfile.BadZipFile as exc:
        raise SkillImportError("无效的 zip 技能包") from exc
    return _install_import_files(files, filename)


def import_skill_directory(files: list[dict[str, str]]) -> dict[str, Any]:
    """Import browser directory-selection payload (relative path + base64 bytes)."""
    decoded: list[tuple[str, bytes]] = []
    for item in files:
        try:
            decoded.append((str(item.get("path") or ""), base64.b64decode(item.get("content") or "", validate=True)))
        except (ValueError, TypeError) as exc:
            raise SkillImportError("技能文件内容编码无效") from exc
    return _install_import_files(decoded, "uploaded-folder")


def create_skill(slug: str, name: str, description: str, instructions: str) -> dict[str, Any]:
    """Create and install one instruction skill from agent-confirmed fields."""
    slug = (slug or "").strip()
    name = (name or "").strip()
    description = (description or "").strip()
    instructions = (instructions or "").strip()
    if not valid_slug(slug):
        raise SkillImportError("slug 仅允许字母、数字与 . _ -，且不能以 - 开头")
    if not name or not description or not instructions:
        raise SkillImportError("创建技能需要 name、description 和 instructions")
    if len(name) > 120 or len(description) > 500 or len(instructions) > 50_000:
        raise SkillImportError("技能名称、描述或指令过长")
    markdown = (
        "---\n"
        f"name: {json.dumps(name, ensure_ascii=False)}\n"
        f"slug: {slug}\n"
        f"description: {json.dumps(description, ensure_ascii=False)}\n"
        "---\n\n"
        f"{instructions}\n"
    )
    return _install_import_files([(SKILL_MD, markdown.encode("utf-8"))], f"{slug}.md")


def canonical_slug(key: str) -> str | None:
    """把已安装技能的目录 key / slug / 展示名解析为稳定 slug。

    slug 与目录 key 是强身份，可直接命中；展示名只有在唯一对应一个 slug 时才接受，
    避免同名 SkillHub 技能因文件系统遍历顺序被静默指向不同包（WB-179/183）。
    """
    q = (key or "").strip()
    if not q:
        return None
    items = scan()
    for item in items:
        if q == item["slug"] or q == item["key"]:
            return str(item["slug"] or item["key"])
    matches = {str(item["slug"] or item["key"]) for item in items if q == item["name"]}
    return next(iter(matches)) if len(matches) == 1 else None


def display_name_for(key: str) -> str | None:
    """按稳定身份返回已安装技能展示名；仅用于 UI/SSE 文案，不参与能力解析。"""
    slug = canonical_slug(key)
    if not slug:
        return None
    for item in scan():
        if (item["slug"] or item["key"]) == slug:
            return str(item["name"] or slug)
    return slug


def _build_detail(d: Path, installed: bool, name_override: str = "") -> dict[str, Any] | None:
    """从任意目录（已安装的 SKILLS_DIR 子目录 或 预览临时目录）构造详情。"""
    info = _info_from_dir(d)
    if not info:
        return None
    if name_override:
        info["name"] = name_override
    info["installed"] = installed
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
        "dir": str(d) if installed else "",
    })
    return info


def detail(key: str) -> dict[str, Any] | None:
    d = _safe_dir(key)
    return _build_detail(d, installed=True) if d else None


def _installed_dir_for_slug(slug: str) -> Path | None:
    root = skills_dir()
    for d in (root.iterdir() if root.exists() else []):
        if not d.is_dir():
            continue
        if d.name == slug or d.name.replace("__skillhub", "") == slug:
            return d
        if str(_read_json(d / SKILLHUB_META).get("slug") or "") == slug:
            return d
    return None


# 安装前预览缓存（slug → (ts, detail)），避免重复下载。
# 必须有 TTL：否则技能在 SkillHub 发了新版，本进程会永远返回旧预览（WB-186）。
# 300s 与 hub/skillhub_client.py 的 _PREVIEW_TTL 对齐，避免两侧行为不一致。
_PREVIEW_TTL = 300.0
_preview_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def preview(slug: str = "", name: str = "") -> dict[str, Any] | None:
    """安装前预览：已安装则给本地详情；否则把 zip 下到临时目录读 SKILL.md，读完即删。
    不污染 ~/.workbuddy/skills/。"""
    slug = (slug or "").strip()
    name = (name or "").strip()
    if not slug and name:
        slug = resolve_slug(name) or ""
    if not slug or not valid_slug(slug):  # WB-185：slug 会拼进 tmp/<slug> 与 CLI 参数
        return None
    inst = _installed_dir_for_slug(slug)
    if inst:
        return _build_detail(inst, installed=True)
    hit = _preview_cache.get(slug)
    if hit and (time.time() - hit[0]) < _PREVIEW_TTL:
        return hit[1]
    if not cli_available():
        return None
    tmp = Path(tempfile.mkdtemp(prefix="skhub-prev-"))
    try:
        _run_cli(["install", slug, "--dir", str(tmp), "--json", "--force"], timeout=120)
        dest = tmp / slug
        if not (dest / SKILL_MD).is_file():
            return None
        det = _build_detail(dest, installed=False, name_override=name)
        if det:
            det["key"] = ""      # 未安装无本地 key
            det["slug"] = slug
            if len(_preview_cache) > 64:
                _preview_cache.clear()
            _preview_cache[slug] = (time.time(), det)
        return det
    except (subprocess.TimeoutExpired, OSError):
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


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
    """把展示名/关键词解析成一个 SkillHub slug —— **仅精确命中**（slug 或 name 完全相等）。

    不做模糊兜底：曾经「否则取第一条」，导致一个根本不存在的名字也能装上搜索结果里
    毫不相干的技能，并被 install() 的 display_name 贴上用户输入的名字，用户无从发现
    （WB-187，实测 `{"name":"不存在的技能xyz"}` 真装上了 self-improving-agent）。
    模糊匹配要给用户，就走 /api/skills/search 让**用户自己选**，后端不替他猜。

    远端搜索返回的 slug 同样过白名单（WB-185）——它会直接流进 install() 的路径拼接
    与子进程参数，不因为「来自 SkillHub」就当可信。
    """
    q = (query or "").strip()
    if not q:
        return None
    for it in search(q, limit=8):
        slug = str(it.get("slug", "")).strip()
        if not valid_slug(slug):
            continue
        if slug == q or str(it.get("name", "")).strip() == q:
            return slug
    return None


# ── skillhub.cn 实时目录来源（WB-064）──────────────────────────────────────
# 真实排行接口，供「分层」方案里 skillhub.cn 实时那一层用；WB-060 的 Hub-DB
# 目录层可消费本函数/端点做整合+离线兜底。清单来自 skillhub 站点，非模拟。
_VALID_RANK_TYPES = {"all", "hot", "featured", "newest", "recommended", "trending", "paid"}
_RANKINGS_TTL = 300.0  # 秒；排行变化慢，短缓存降低对站点的压力
_rankings_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _to_int(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _normalize_card(x: dict[str, Any]) -> dict[str, Any]:
    """把 rankings/search 的一条归一化成前端可直接渲染的商品卡。"""
    return {
        "slug": str(x.get("slug") or "").strip(),
        "name": str(x.get("name") or "").strip(),
        "description": str(x.get("description_zh") or x.get("description") or "").strip(),
        "version": str(x.get("version") or "").strip(),
        "category": str(x.get("category") or "").strip(),
        "subCategories": x.get("subCategories") or [],
        "downloads": _to_int(x.get("downloads")),
        "installs": _to_int(x.get("installs")),
        "stars": _to_int(x.get("stars")),
        "score": x.get("score"),
        "iconUrl": str(x.get("iconUrl") or "").strip(),
        "tags": x.get("tags") or [],
        "verified": bool(x.get("verified")),
        "source": str(x.get("source") or "skillhub").strip(),
    }


def rankings(rtype: str = "featured", category: str = "", limit: int = 0) -> list[dict[str, Any]]:
    """实时排行目录：skillhub CLI `skill rankings --type <rtype>`，归一化 + 标记本地已安装。
    站点不可达/超时时回退到上次缓存（有则），否则空列表。"""
    rtype = (rtype or "featured").strip().lower()
    if rtype not in _VALID_RANK_TYPES:
        rtype = "featured"
    cached = _rankings_cache.get(rtype)
    items = cached[1] if cached else []  # 缓存命中 / CLI 缺失 / 取数失败，都以它兜底
    if cached and (time.time() - cached[0]) < _RANKINGS_TTL:
        pass
    elif cli_available():
        try:
            cp = _run_cli(["skill", "rankings", "--type", rtype], timeout=30)
            d = json.loads((cp.stdout or "").strip())
            raw = d.get("skills") if isinstance(d, dict) else (d if isinstance(d, list) else [])
            if isinstance(raw, list):
                items = [_normalize_card(x) for x in raw if isinstance(x, dict) and x.get("slug")]
                _rankings_cache[rtype] = (time.time(), items)
        except (subprocess.TimeoutExpired, OSError, ValueError):
            pass  # 保留上次缓存（items 已置为 cached）

    return decorate_cards(items, category, limit)


def decorate_cards(
    items: list[dict[str, Any]], category: str = "", limit: int = 0
) -> list[dict[str, Any]]:
    """给商品卡按本机状态加工：标记已安装 + 按分类过滤 + 截断。

    「已安装」是**本机磁盘**的知识，Manager 给不出来，所以经 Hub 代理取回的榜单
    也要过这一步（WB-186）。
    """
    inst = scan()
    inst_keys = {s["slug"] for s in inst} | {s["name"] for s in inst}
    cat = category.strip().lower()
    out: list[dict[str, Any]] = []
    for it in items:
        if cat:
            hay = " ".join([
                str(it.get("category", "")),
                " ".join(str(x) for x in (it.get("subCategories") or [])),
                " ".join(str(x) for x in (it.get("tags") or [])),
            ]).lower()
            if cat not in hay:
                continue
        out.append({**it, "installed": it.get("slug") in inst_keys or it.get("name") in inst_keys})
    return out[:limit] if limit and limit > 0 else out


def install(slug: str, display_name: str = "") -> dict[str, Any]:
    """真正安装：跑 CLI 下载解压进 SKILLS_DIR/<slug>/。成功返回 {ok, skill}。"""
    slug = (slug or "").strip()
    if not slug:
        return {"ok": False, "error": "empty slug"}
    if not valid_slug(slug):  # WB-185：挡路径穿越 / CLI 参数注入
        return {"ok": False, "error": f"非法 slug：{slug[:80]}"}
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
