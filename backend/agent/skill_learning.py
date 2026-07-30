"""Governed Run -> Skill candidate lifecycle (WB-336).

Candidates are durable drafts.  They never mutate an installed package, and a
local candidate cannot be installed until a separate evidenced Test Run passes
and the owner explicitly approves it.  Platform candidates are handed off to
the existing Server release state machine instead of being published here.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from agent import skills_store
from storage import db

TARGET_SCOPES = {"local", "platform"}
STATES = {"draft", "tested", "approved", "installed", "rejected", "rolled_back"}


def _init() -> None:
    conn = db.get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS skill_candidates (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            source_run_id TEXT NOT NULL,
            test_run_id TEXT,
            target_scope TEXT NOT NULL,
            slug TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            instructions TEXT NOT NULL,
            tools TEXT NOT NULL DEFAULT '[]',
            evidence TEXT NOT NULL DEFAULT '[]',
            base_release_id TEXT NOT NULL DEFAULT '',
            base_content_hash TEXT NOT NULL DEFAULT '',
            content_hash TEXT NOT NULL,
            diff TEXT NOT NULL DEFAULT '{}',
            security_scan TEXT NOT NULL DEFAULT '{}',
            security_warnings_accepted INTEGER NOT NULL DEFAULT 0,
            state TEXT NOT NULL DEFAULT 'draft',
            installed_key TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_skill_candidates_owner
            ON skill_candidates(owner_id, created_at DESC);
        CREATE TABLE IF NOT EXISTS skill_candidate_events (
            id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL,
            actor_id TEXT NOT NULL,
            action TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL,
            FOREIGN KEY(candidate_id) REFERENCES skill_candidates(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_skill_candidate_events_candidate
            ON skill_candidate_events(candidate_id, created_at);
        """
    )
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(skill_candidates)").fetchall()}
    if "security_scan" not in columns:
        conn.execute("ALTER TABLE skill_candidates ADD COLUMN security_scan TEXT NOT NULL DEFAULT '{}'")
    if "security_warnings_accepted" not in columns:
        conn.execute(
            "ALTER TABLE skill_candidates ADD COLUMN security_warnings_accepted INTEGER NOT NULL DEFAULT 0"
        )
    conn.commit()


def _loads(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return fallback


def _event(candidate_id: str, actor_id: str, action: str, details: dict[str, Any] | None = None) -> None:
    db.get_conn().execute(
        """INSERT INTO skill_candidate_events
           (id,candidate_id,actor_id,action,details,created_at) VALUES (?,?,?,?,?,?)""",
        (
            db.new_uuid(), candidate_id, actor_id, action,
            json.dumps(details or {}, ensure_ascii=False), time.time(),
        ),
    )


def _row(row: Any, *, with_events: bool = True) -> dict[str, Any]:
    item = dict(row)
    for field, fallback in (
        ("tools", []), ("evidence", []), ("diff", {}), ("security_scan", {}),
    ):
        item[field] = _loads(item[field], fallback)
    item["security_warnings_accepted"] = bool(item["security_warnings_accepted"])
    item["permissions"] = item["diff"].get("permissions_after", [])
    if with_events:
        events = db.get_conn().execute(
            "SELECT * FROM skill_candidate_events WHERE candidate_id=? ORDER BY created_at,id",
            (item["id"],),
        ).fetchall()
        item["events"] = [
            {**dict(event), "details": _loads(event["details"], {})}
            for event in events
        ]
    return item


def _accepted_evidence(run_id: str) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for artifact in db.list_artifacts(run_id):
        if artifact.validation_status == "passed" and artifact.acceptance_status == "accepted":
            evidence.append({
                "kind": "artifact",
                "id": artifact.id,
                "path": artifact.path,
                "sha256": artifact.sha256,
                "validation": artifact.validation,
            })
    return evidence


def _eligible_run(run_id: str, owner_id: str) -> tuple[Any, list[dict[str, Any]]]:
    run = db.get_run(run_id)
    if not run or run.owner_id != owner_id:
        raise PermissionError("run not found")
    if run.status not in {"completed", "accepted"}:
        raise ValueError("只有已成功完成的 Run 可以沉淀 Skill 候选")
    evidence = _accepted_evidence(run.id)
    if not evidence:
        raise ValueError("Run 缺少已校验且已验收的产物证据")
    return run, evidence


def _candidate_content_hash(candidate: dict[str, Any]) -> str:
    definition = {
        "name": candidate["name"],
        "description": candidate["description"],
        "instructions": candidate["instructions"],
        "tools": candidate["tools"],
    }
    return hashlib.sha256(
        json.dumps(definition, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _assert_candidate_integrity(candidate: dict[str, Any]) -> None:
    if _candidate_content_hash(candidate) != candidate["content_hash"]:
        raise ValueError("Skill 候选内容 hash 校验失败")
    for evidence in candidate.get("evidence", []):
        if evidence.get("kind") != "artifact":
            raise ValueError("Skill 候选包含未知证据类型")
        artifact = db.get_artifact(str(evidence.get("id") or ""))
        if (
            not artifact
            or artifact.run_id != candidate["source_run_id"]
            or artifact.owner_id != candidate["owner_id"]
            or artifact.sha256 != evidence.get("sha256")
            or artifact.validation_status != "passed"
            or artifact.acceptance_status != "accepted"
        ):
            raise ValueError("Skill 候选来源证据已失效或发生变化")


def _base_snapshot(slug: str) -> tuple[str, str, list[str], dict[str, Any]]:
    from agent.skills import skill_runtime_def

    installed = next((item for item in skills_store.scan() if item.get("slug") == slug), None)
    if not installed:
        return "", "", [], {}
    definition = skill_runtime_def(slug)
    snapshot = dict(definition.get("snapshot") or {}) if definition else {}
    detail = skills_store.detail(str(installed["key"])) or {}
    return (
        str(snapshot.get("release_id") or installed.get("release_id") or ""),
        str(snapshot.get("content_hash") or installed.get("content_hash") or ""),
        sorted(str(item) for item in snapshot.get("permissions", []) if str(item)),
        {
            "name": str(detail.get("name") or ""),
            "description": str(detail.get("description") or ""),
            "instructions": str(detail.get("body") or ""),
            "tools": sorted(str(item) for item in snapshot.get("tools", []) if str(item)),
        },
    )


def create_candidate(
    *,
    owner_id: str,
    source_run_id: str,
    target_scope: str,
    slug: str,
    name: str,
    description: str,
    instructions: str,
    tools: list[str] | None = None,
) -> dict[str, Any]:
    from agent import skill_security
    from agent.skills import SKILL_BINDABLE_TOOL_NAMES, tool_permissions

    _init()
    _eligible_run(source_run_id, owner_id)
    scope = (target_scope or "local").strip().lower()
    if scope not in TARGET_SCOPES:
        raise ValueError("target_scope 必须是 local 或 platform")
    slug = (slug or "").strip()
    name = (name or "").strip()
    description = (description or "").strip()
    instructions = (instructions or "").strip()
    if not skills_store.valid_slug(slug):
        raise ValueError("Skill slug 非法")
    if not name or not description or not instructions:
        raise ValueError("候选必须包含名称、描述和完整指令")
    if len(name) > 120 or len(description) > 500 or len(instructions) > 50_000:
        raise ValueError("候选名称、描述或指令过长")
    normalized_tools = sorted({str(item).strip() for item in (tools or []) if str(item).strip()})
    unknown = sorted(set(normalized_tools) - set(SKILL_BINDABLE_TOOL_NAMES))
    if unknown:
        raise ValueError(f"候选声明了当前 App 不允许绑定的工具：{', '.join(unknown)}")
    if scope == "local" and normalized_tools:
        raise ValueError("本地候选只能是 instruction-only；带工具候选必须走 platform 发布审核")

    run, evidence = _eligible_run(source_run_id, owner_id)
    base_release_id, base_content_hash, before_permissions, before = _base_snapshot(slug)
    after_permissions = sorted(tool_permissions(normalized_tools))
    after = {
        "name": name,
        "description": description,
        "instructions": instructions,
        "tools": normalized_tools,
    }
    changed = sorted(
        key for key in ("name", "description", "instructions", "tools")
        if before.get(key) != after.get(key)
    )
    content_hash = hashlib.sha256(
        json.dumps(after, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    markdown = (
        "---\n"
        f"name: {json.dumps(name, ensure_ascii=False)}\n"
        f"slug: {slug}\n"
        f"description: {json.dumps(description, ensure_ascii=False)}\n"
        "---\n\n"
        f"{instructions}\n"
    ).encode("utf-8")
    security_scan = skill_security.scan_package(
        [(skills_store.SKILL_MD, markdown)],
        trust_level="local" if scope == "local" else "agentmate",
    )
    if security_scan["verdict"] == "dangerous":
        raise ValueError("Skill 候选包含不可覆盖的危险行为")
    diff = {
        "changed_fields": changed,
        "tools_added": sorted(set(normalized_tools) - set(before.get("tools") or [])),
        "tools_removed": sorted(set(before.get("tools") or []) - set(normalized_tools)),
        "permissions_before": before_permissions,
        "permissions_after": after_permissions,
        "permissions_added": sorted(set(after_permissions) - set(before_permissions)),
        "permissions_removed": sorted(set(before_permissions) - set(after_permissions)),
    }
    now = time.time()
    candidate_id = db.new_uuid()
    conn = db.get_conn()
    conn.execute(
        """INSERT INTO skill_candidates
           (id,owner_id,source_run_id,target_scope,slug,name,description,instructions,tools,
            evidence,base_release_id,base_content_hash,content_hash,diff,security_scan,
            state,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            candidate_id, owner_id, run.id, scope, slug, name, description, instructions,
            json.dumps(normalized_tools, ensure_ascii=False),
            json.dumps(evidence, ensure_ascii=False),
            base_release_id, base_content_hash, content_hash,
            json.dumps(diff, ensure_ascii=False),
            json.dumps(security_scan, ensure_ascii=False),
            "draft", now, now,
        ),
    )
    _event(candidate_id, owner_id, "candidate_created", {
        "source_run_id": run.id,
        "evidence_ids": [item["id"] for item in evidence],
        "content_hash": content_hash,
    })
    conn.commit()
    return get_candidate(candidate_id, owner_id)  # type: ignore[return-value]


def get_candidate(candidate_id: str, owner_id: str) -> dict[str, Any] | None:
    _init()
    row = db.get_conn().execute(
        "SELECT * FROM skill_candidates WHERE id=? AND owner_id=?",
        (candidate_id, owner_id),
    ).fetchone()
    return _row(row) if row else None


def list_candidates(owner_id: str) -> list[dict[str, Any]]:
    _init()
    rows = db.get_conn().execute(
        "SELECT * FROM skill_candidates WHERE owner_id=? ORDER BY created_at DESC",
        (owner_id,),
    ).fetchall()
    return [_row(row) for row in rows]


def record_test(candidate_id: str, owner_id: str, test_run_id: str) -> dict[str, Any]:
    candidate = get_candidate(candidate_id, owner_id)
    if not candidate:
        raise KeyError(candidate_id)
    if candidate["state"] != "draft":
        raise ValueError("只有 draft 候选可以记录 Test Run")
    _assert_candidate_integrity(candidate)
    if test_run_id == candidate["source_run_id"]:
        raise ValueError("Test Run 必须独立于来源 Run")
    run, evidence = _eligible_run(test_run_id, owner_id)
    now = time.time()
    db.get_conn().execute(
        "UPDATE skill_candidates SET test_run_id=?,state='tested',updated_at=? WHERE id=?",
        (run.id, now, candidate_id),
    )
    _event(candidate_id, owner_id, "test_passed", {
        "test_run_id": run.id,
        "evidence_ids": [item["id"] for item in evidence],
    })
    db.get_conn().commit()
    return get_candidate(candidate_id, owner_id)  # type: ignore[return-value]


def approve(
    candidate_id: str,
    owner_id: str,
    *,
    accept_security_warnings: bool = False,
) -> dict[str, Any]:
    from agent.skill_security import requires_confirmation

    candidate = get_candidate(candidate_id, owner_id)
    if not candidate:
        raise KeyError(candidate_id)
    if candidate["state"] != "tested":
        raise ValueError("候选必须先通过独立 Test Run")
    _assert_candidate_integrity(candidate)
    _eligible_run(str(candidate["test_run_id"] or ""), owner_id)
    if requires_confirmation(candidate["security_scan"]) and not accept_security_warnings:
        raise ValueError("候选安全扫描包含 warning，确认时必须显式接受")
    db.get_conn().execute(
        """UPDATE skill_candidates
           SET state='approved',security_warnings_accepted=?,updated_at=? WHERE id=?""",
        (1 if accept_security_warnings else 0, time.time(), candidate_id),
    )
    _event(candidate_id, owner_id, "owner_approved", {
        "content_hash": candidate["content_hash"],
        "security_warnings_accepted": bool(accept_security_warnings),
    })
    db.get_conn().commit()
    return get_candidate(candidate_id, owner_id)  # type: ignore[return-value]


def reject(candidate_id: str, owner_id: str, reason: str = "") -> dict[str, Any]:
    candidate = get_candidate(candidate_id, owner_id)
    if not candidate:
        raise KeyError(candidate_id)
    if candidate["state"] in {"installed", "rolled_back"}:
        raise ValueError("已安装候选不能改为 rejected；请执行 rollback")
    db.get_conn().execute(
        "UPDATE skill_candidates SET state='rejected',updated_at=? WHERE id=?",
        (time.time(), candidate_id),
    )
    _event(candidate_id, owner_id, "rejected", {"reason": (reason or "").strip()[:500]})
    db.get_conn().commit()
    return get_candidate(candidate_id, owner_id)  # type: ignore[return-value]


def install_local(candidate_id: str, owner_id: str) -> dict[str, Any]:
    candidate = get_candidate(candidate_id, owner_id)
    if not candidate:
        raise KeyError(candidate_id)
    if candidate["state"] != "approved" or candidate["target_scope"] != "local":
        raise ValueError("只有 owner 已确认的 local 候选可以安装")
    _assert_candidate_integrity(candidate)
    if any(item.get("slug") == candidate["slug"] for item in skills_store.scan()):
        raise ValueError("候选不会覆盖现有 Skill；请更换 slug 或走受审升级流程")
    result = skills_store.create_skill(
        candidate["slug"], candidate["name"], candidate["description"], candidate["instructions"],
        accept_security_warnings=bool(candidate["security_warnings_accepted"]),
    )
    installed = result["skill"]
    db.get_conn().execute(
        "UPDATE skill_candidates SET state='installed',installed_key=?,updated_at=? WHERE id=?",
        (str(installed["key"]), time.time(), candidate_id),
    )
    _event(candidate_id, owner_id, "installed", {
        "package_key": installed["key"],
        "content_hash": installed.get("content_hash") or "",
    })
    db.get_conn().commit()
    return get_candidate(candidate_id, owner_id)  # type: ignore[return-value]


def rollback_local(candidate_id: str, owner_id: str) -> dict[str, Any]:
    candidate = get_candidate(candidate_id, owner_id)
    if not candidate:
        raise KeyError(candidate_id)
    if candidate["state"] != "installed" or not candidate["installed_key"]:
        raise ValueError("只有已安装的本地候选可以回滚")
    if not skills_store.uninstall(candidate["installed_key"]):
        raise ValueError("候选对应的本地 Skill 已不存在")
    db.get_conn().execute(
        "UPDATE skill_candidates SET state='rolled_back',updated_at=? WHERE id=?",
        (time.time(), candidate_id),
    )
    _event(candidate_id, owner_id, "rolled_back", {"package_key": candidate["installed_key"]})
    db.get_conn().commit()
    return get_candidate(candidate_id, owner_id)  # type: ignore[return-value]


def platform_release_payload(candidate_id: str, owner_id: str) -> dict[str, Any]:
    candidate = get_candidate(candidate_id, owner_id)
    if not candidate:
        raise KeyError(candidate_id)
    if candidate["target_scope"] != "platform" or candidate["state"] != "approved":
        raise ValueError("只有已测试并确认的平台候选可以进入 Server 发布审核")
    _assert_candidate_integrity(candidate)
    return {
        "candidate_id": candidate["id"],
        "source_run_id": candidate["source_run_id"],
        "test_run_id": candidate["test_run_id"],
        "base_release_id": candidate["base_release_id"],
        "data": {
            "slug": candidate["slug"],
            "name": candidate["name"],
            "description": candidate["description"],
            "instructions": candidate["instructions"],
            "tools": candidate["tools"],
        },
        "evidence": candidate["evidence"],
        "diff": candidate["diff"],
        "content_hash": candidate["content_hash"],
        "next_state_machine": "draft -> testing -> approved(two-person) -> rolling_out -> published/withdrawn/rollback",
    }
