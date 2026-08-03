"""Read-only mounted resources for immutable Skill releases (WB-247)."""
from __future__ import annotations

import hashlib
import os
import tempfile
from contextvars import ContextVar
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

from agent import skills_store
from agent.sandbox import SandboxError, relpath, resolve_in_sandbox
from agent.tools import Tool, ToolOutcome

_MAX_RESOURCE_BYTES = 256 * 1024
_active_resources: ContextVar[dict[str, dict[str, Any]]] = ContextVar(
    "active_skill_resources", default={},
)


def set_active_skill_resources(snapshots: list[dict[str, Any]]) -> None:
    active: dict[str, dict[str, Any]] = {}
    for snapshot in snapshots:
        slug = str(snapshot.get("slug") or "")
        package_key = str(snapshot.get("package_key") or slug)
        root = skills_store.package_dir(package_key)
        if not slug or not root:
            continue
        files = {
            str(item.get("path") or ""): {
                "sha256": str(item.get("sha256") or ""),
                "size": int(item.get("size") or 0),
            }
            for item in snapshot.get("files", [])
            if isinstance(item, dict) and str(item.get("path") or "").casefold() != skills_store.SKILL_MD.casefold()
        }
        if files:
            active[slug] = {"root": root, "files": files, "release_id": snapshot.get("release_id", "")}
    _active_resources.set(active)


def has_active_resources() -> bool:
    return any(item["files"] for item in _active_resources.get().values())


def active_resource_mounts() -> dict[str, dict[str, Any]]:
    """Return a JSON-safe copy for the trusted isolated tool worker."""
    return {
        slug: {
            **dict(item),
            "root": str(item["root"]),
            "files": {path: dict(meta) for path, meta in item["files"].items()},
        }
        for slug, item in _active_resources.get().items()
    }


def set_active_resource_mounts(value: dict[str, dict[str, Any]] | None) -> None:
    mounted: dict[str, dict[str, Any]] = {}
    for slug, item in (value or {}).items():
        if not isinstance(item, dict) or not item.get("root"):
            continue
        mounted[str(slug)] = {
            **dict(item),
            "root": Path(str(item["root"])),
            "files": {
                str(path): dict(meta) for path, meta in (item.get("files") or {}).items()
                if isinstance(meta, dict)
            },
        }
    _active_resources.set(mounted)


def _resource(skill: str, path: str) -> tuple[Any, PurePosixPath, dict[str, Any]]:
    mounted = _active_resources.get().get((skill or "").strip())
    if not mounted:
        raise ValueError(f"Skill 未启用或没有可访问资源：{skill}")
    try:
        rel = skills_store.safe_package_path(path)
    except skills_store.SkillImportError as exc:
        raise ValueError(str(exc)) from exc
    meta = mounted["files"].get(rel.as_posix())
    if not meta:
        raise ValueError(f"资源未在当前 release manifest 中声明：{path}")
    return mounted, rel, meta


def _verified_bytes(skill: str, path: str) -> tuple[bytes, PurePosixPath]:
    mounted, rel, meta = _resource(skill, path)
    target = mounted["root"].joinpath(*rel.parts)
    try:
        data = target.read_bytes()
    except OSError as exc:
        raise ValueError(f"资源无法读取：{path}") from exc
    if len(data) != meta["size"] or hashlib.sha256(data).hexdigest() != meta["sha256"]:
        raise ValueError(f"资源完整性校验失败：{path}")
    return data, rel


def _list_resources_run(args: dict[str, Any]) -> ToolOutcome:
    skill = str(args.get("skill") or "").strip()
    mounted = _active_resources.get()
    if skill:
        entries = {skill: mounted.get(skill)} if mounted.get(skill) else {}
    else:
        entries = mounted
    if not entries:
        return ToolOutcome(text="当前 Run 没有已挂载的 Skill 资源。")
    lines: list[str] = []
    for slug, item in sorted(entries.items()):
        lines.append(f"{slug} ({item['release_id']}):")
        lines.extend(f"- {path}" for path in sorted(item["files"]))
    return ToolOutcome(text="\n".join(lines))


skill_list_resources = Tool(
    name="skill_list_resources",
    description="列出当前 Run 已启用 Skill 的 manifest 声明资源；不会暴露本机安装绝对路径。",
    parameters={
        "type": "object",
        "properties": {"skill": {"type": "string", "description": "可选 Skill slug；留空列出全部"}},
    },
    pre=lambda args: {"kind": "step", "tool": "skill_list_resources", "label": f"查看技能资源 {args.get('skill', '')}"},
    run=_list_resources_run,
    plan_safe=True,
    permissions=("skill.resource.read",),
)


def _read_resource_run(args: dict[str, Any]) -> ToolOutcome:
    skill = str(args.get("skill") or "")
    path = str(args.get("path") or "")
    try:
        data, rel = _verified_bytes(skill, path)
    except ValueError as exc:
        return ToolOutcome(text=str(exc))
    if len(data) > _MAX_RESOURCE_BYTES:
        return ToolOutcome(text=f"资源过大，拒绝注入（>{_MAX_RESOURCE_BYTES} bytes）：{rel.as_posix()}")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return ToolOutcome(text=f"资源不是 UTF-8 文本：{rel.as_posix()}")
    return ToolOutcome(
        text=text,
        trace=[{"kind": "file_read", "path": f"skill://{skill}/{rel.as_posix()}", "range": "全文"}],
    )


skill_read_resource = Tool(
    name="skill_read_resource",
    description="按需读取当前 Run 已启用 Skill release 中声明的 UTF-8 文本资源。",
    parameters={
        "type": "object",
        "properties": {
            "skill": {"type": "string", "description": "Skill slug"},
            "path": {"type": "string", "description": "manifest 中的相对资源路径"},
        },
        "required": ["skill", "path"],
    },
    pre=lambda args: {"kind": "step", "tool": "skill_read_resource", "label": f"读取技能资源 {args.get('path', '')}"},
    run=_read_resource_run,
    plan_safe=True,
    permissions=("skill.resource.read",),
)


def _copy_template_run(args: dict[str, Any]) -> ToolOutcome:
    skill = str(args.get("skill") or "")
    path = str(args.get("path") or "")
    destination = str(args.get("destination") or "")
    try:
        data, rel = _verified_bytes(skill, path)
        if not rel.parts or rel.parts[0].casefold() != "templates":
            raise ValueError("只有 templates/ 下的声明文件可以复制到工作区")
        target = resolve_in_sandbox(destination)
    except (ValueError, OSError, SandboxError) as exc:
        return ToolOutcome(text=str(exc))
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        os.replace(temp_name, target)
    except OSError as exc:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        return ToolOutcome(text=f"模板复制失败：{exc}")
    relative = relpath(target)
    return ToolOutcome(
        text=f"已从 skill://{skill}/{rel.as_posix()} 原子复制到 {relative}",
        trace=[{"kind": "file_write", "path": relative, "source": f"skill://{skill}/{rel.as_posix()}"}],
        artifacts=[{"path": relative, "kind": "skill-template"}],
    )


skill_copy_template = Tool(
    name="skill_copy_template",
    description="把当前 Skill release 的 templates/ 文件原子复制到项目工作区。",
    parameters={
        "type": "object",
        "properties": {
            "skill": {"type": "string", "description": "Skill slug"},
            "path": {"type": "string", "description": "templates/ 下的 manifest 路径"},
            "destination": {"type": "string", "description": "工作区内目标相对路径"},
        },
        "required": ["skill", "path", "destination"],
    },
    pre=lambda args: {"kind": "step", "tool": "skill_copy_template", "label": f"复制技能模板 {args.get('path', '')}"},
    run=_copy_template_run,
    permissions=("skill.resource.read", "workspace.write"),
)


RESOURCE_TOOLS = [skill_list_resources, skill_read_resource, skill_copy_template]
