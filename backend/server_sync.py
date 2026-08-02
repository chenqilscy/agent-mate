"""下行同步：本地 backend 从 Server 拉项目/成员镜像进本地（WB-062 Phase 2）。

Server 项目落本地 `projects`(origin='server')，成员落 `project_members`——WB-050 的
`project_access_role` 读同一批表，故镜像后本地访问控制「自动」认它（owner/成员按 Server 侧 id 对齐，
与鉴权桥镜像的账号 id 一致）。**只拉控制平面元数据**（项目名/指令/loadout/成员），
绝不涉及 LLM 凭据 / 连接器 secret / 沙箱工作区文件（铁律 4/11）。项目级 knowledge_ids
是 Server 内部稳定绑定 ID，不含 WeKnora provider ID 或 API Key。Server 不可达 → 返回 0、不报错。

这些是**同步阻塞**调用——放在 FastAPI 的**同步路由**里跑（自动走线程池，不占事件循环）。
"""
from __future__ import annotations

import hashlib
import platform
import uuid

import server_client
from agent.skills import _TOOL_REGISTRY, canonical_skill_keys
from config import settings
from storage import db
from storage.models import LOCAL_USER_ID


_CATALOG_REVISION_KEY = "server.catalog_revision"
_RELAY_DEVICE_ID_KEY = "server.relay_device_id"


def relay_device_id() -> str:
    """Stable opaque local device target. It contains no hostname/user data."""
    current = db.get_device_setting(_RELAY_DEVICE_ID_KEY)
    if current:
        return current
    created = f"device-{uuid.uuid4()}"
    db.set_device_setting(_RELAY_DEVICE_ID_KEY, created)
    return created


def _capability_report(revision: str) -> dict:
    # 直接报告本 App 构建中可执行的真实注册表；目录展示/启停属于 Server DB，不能反向
    # 声明出本机不存在的实现。ask_user 是 runtime 特判 schema，没有 Tool 对象。
    contracts = {name: settings.TOOL_CONTRACT_VERSION for name in _TOOL_REGISTRY}
    contracts["ask_user"] = settings.TOOL_CONTRACT_VERSION
    return {
        "revision": revision,
        "app_version": settings.APP_VERSION,
        "platform": platform.system().lower(),
        "arch": platform.machine().lower(),
        "tool_contract_version": settings.TOOL_CONTRACT_VERSION,
        "supported_tools": contracts,
    }


def pull(token: str) -> dict:
    """用请求携带的 Server token 拉该账号在 Server 的项目 + 成员，幂等镜像进本地。返回 {synced, projects}。"""
    projects = server_client.list_projects(token)
    if projects is None:
        return {"synced": 0, "projects": []}
    synced: list[str] = []
    for p in projects:
        pid = p.get("id")
        if not pid:
            continue
        db.mirror_server_project(
            id=pid, name=p.get("name", ""), owner_id=p.get("owner_id", ""),
            instruction=p.get("instruction", ""), connectors=p.get("connectors", []),
            experts=p.get("experts", []), skills=canonical_skill_keys(p.get("skills", [])),
            knowledge_ids=p.get("knowledge_ids", []),
            created_at=p.get("created_at"), updated_at=p.get("updated_at"),
        )
        members = server_client.list_project_members(token, pid)
        # 项目列表成功不代表成员子请求也成功；子请求不可达时保留 last-known-good，
        # 不能把“未知”误当空快照并清空本地权限镜像。
        if members is not None:
            db.replace_server_project_members(pid, members)
        synced.append(pid)
    account_id = db.user_id_for_token(token)
    if account_id:
        db.reconcile_server_project_access(account_id, set(synced))
    conflicts = [
        conflict for pid in synced for conflict in db.list_server_sync_conflicts(pid)
    ]
    return {"synced": len(synced), "projects": synced, "conflicts": conflicts}


# ---- 上行 outbox（WB-062 Phase 3）--------------------------------------

def enqueue_timeline_event(*, session, actor_id: str, actor_name: str = "") -> bool:
    """项目会话完成时把一条时间线事件入 outbox。仅当：已接 Server + 开了上报开关 + 该会话属于一个
    Server 镜像项目。返回是否入队。**只放元数据 + 短标题**——绝不含正文/凭据/工作区文件（隐私，铁律 4）。"""
    if not settings.server_enabled or not settings.AGENTMATE_SERVER_TIMELINE_UPLOAD:
        return False
    if not getattr(session, "project_id", None):
        return False
    proj = db.get_project(session.project_id)
    if not proj or proj.origin != "server":
        return False  # 只回传 Server 镜像项目的执行（本地私有项目不上云）
    db.enqueue_outbox(
        kind="timeline", actor_id=actor_id, project_id=session.project_id,
        payload={"kind": "session", "title": (session.title or "")[:200], "summary": "", "ext_id": session.id},
    )
    return True


def enqueue_work_item_event(
    *, project_id: str, work_item_id: str, launch_id: str, actor_id: str,
    status: str, artifact_count: int,
) -> bool:
    """Upload only collaboration-safe delivery metadata, never task/file text."""
    if not settings.server_enabled or not settings.AGENTMATE_SERVER_TIMELINE_UPLOAD:
        return False
    project = db.get_project(project_id)
    if not project or project.origin != "server":
        return False
    labels = {
        "completed": "工作项执行已完成，等待验收",
        "failed": "工作项执行失败",
        "cancelled": "工作项执行已取消",
    }
    db.enqueue_outbox(
        kind="timeline", actor_id=actor_id, project_id=project_id,
        payload={
            "kind": "work_item_run",
            "title": f"{labels.get(status, '工作项执行更新')} · {max(0, artifact_count)} 个产物",
            "summary": "",
            "ext_id": f"work-item:{work_item_id}:launch:{launch_id}",
        },
    )
    return True


def flush_token_revocations(limit: int = 50) -> dict:
    """重试本地已登出但尚未送达 Server 的 token 撤销；不记录或返回 token 内容。"""
    if not settings.server_enabled:
        return {"revoked": 0, "pending": len(db.list_pending_token_revocations(limit))}
    pending = db.list_pending_token_revocations(limit)
    revoked = 0
    for item in pending:
        token = item["token"]
        if server_client.server_logout(token):
            db.mark_token_revoked(token)
            revoked += 1
        else:
            db.bump_token_revocation_tries(token)
    return {"revoked": revoked, "pending": len(pending) - revoked}


def flush_outbox(limit: int = 50) -> dict:
    """后台补推：把 pending outbox 推给 Server（用各 actor 缓存的 Server token）。成功标 synced，
    失败留待下轮（断线/离线自动补推）。未接 Server → 直接返回。"""
    if not settings.server_enabled:
        return {"pushed": 0, "pending": 0}
    # 登录撤销比业务时间线上报优先，且不受 timeline upload 开关影响。
    flush_token_revocations(limit)
    pending = db.list_pending_outbox(limit)
    pushed = 0
    for item in pending:
        token = db.get_server_identity(item["actor_id"])
        if not token:
            db.bump_outbox_tries(item["id"])  # 该 actor 尚无 Server token，暂留
            continue
        ok = server_client.post_timeline(token, item["project_id"], item["payload"]) \
            if item["kind"] == "timeline" else False
        if ok:
            db.mark_outbox_synced(item["id"])
            pushed += 1
        else:
            db.bump_outbox_tries(item["id"])
    return {"pushed": pushed, "pending": len(pending) - pushed}


# ---- 存量导入（WB-063）--------------------------------------------------

def import_local_to_server(token: str, account: dict) -> dict:
    """首次登录 Server 时，把本机存量数据（LOCAL_USER 的本地原生项目）上行到 Server（架构设计 §8）。
    **幂等**：已导入的（server_imports 有记录）跳过 → 「重复导入不产生重复数据」。记 LOCAL_USER↔Server 绑定。
    只上行控制平面元数据（项目名/指令/loadout），绝不含凭据/工作区文件（铁律 4/11）。"""
    if not settings.server_enabled:
        return {"server": False, "imported": 0, "skipped": 0}
    aid = account.get("id")
    if not aid:
        return {"server": True, "imported": 0, "skipped": 0}
    db.set_server_link(LOCAL_USER_ID, str(aid), str(account.get("name", "")))
    imported, skipped = 0, 0
    for p in db.list_projects(LOCAL_USER_ID):
        if p.origin != "local":
            continue  # 不导入已是 Server 镜像的项目
        if db.get_import(p.id):
            skipped += 1
            continue  # 幂等：已导入
        server_id = server_client.create_project(token, {
            "name": p.name, "instruction": p.instruction,
            "connectors": p.connectors, "experts": p.experts, "skills": p.skills,
        })
        if server_id:
            db.record_import(p.id, "project", server_id, str(aid))
            imported += 1
        # 失败不记 → 下次可重试
    return {"server": True, "imported": imported, "skipped": skipped}


# ---- 目录下发（WB-066）--------------------------------------------------

def pull_catalog(token: str) -> dict:
    """从 Server 拉全量目录与工具定义并镜像到本地。

    Server 不可达或工具快照损坏时保留最后可用版本；旧 Server 没有 tools 字段时也不清空。
    """
    if not settings.server_enabled:
        return {"downlinked": 0, "reachable": False}
    revision = db.get_user_setting(LOCAL_USER_ID, _CATALOG_REVISION_KEY) or ""
    snapshot = server_client.pull_catalog_snapshot(token, _capability_report(revision))
    if snapshot is None:
        # Compatibility window for pre-WB-246 Server versions. A truly unreachable
        # Server returns None from both guarded requests, preserving last-known-good.
        legacy = server_client.list_all_catalog(token)
        if legacy is None:
            return {"downlinked": 0, "reachable": False}
        digest = hashlib.sha256(json.dumps(legacy, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        snapshot = {"items": legacy, "revision": f"legacy:{digest}", "unchanged": False}
    if snapshot.get("unchanged"):
        return {"downlinked": 0, "reachable": True, "unchanged": True, "revision": revision}
    items = snapshot.get("items")
    if not isinstance(items, list):
        return {"downlinked": 0, "reachable": False, "error": "invalid_catalog_snapshot"}
    tool_result = {"accepted": True, "inserted": 0, "skipped": 0, "preserved": True}
    if "tools" in snapshot:
        if not isinstance(snapshot["tools"], list):
            return {"downlinked": 0, "reachable": False, "error": "invalid_tool_snapshot"}
        tool_result = db.replace_server_tool_catalog(snapshot["tools"])
        if not tool_result["accepted"]:
            return {
                "downlinked": 0, "reachable": False, "error": "invalid_tool_snapshot",
                "tools_skipped": tool_result["skipped"], "tools_preserved": True,
            }
    skill_rows = [
        {
            **it["data"], "sort": it.get("sort", 0), "version": str(it.get("version", "")),
            "withdrawn": bool(it.get("withdrawn", False)),
            "compatible": bool(it.get("compatible", True)),
            "compatibility_error": str(it.get("compatibility_error", "")),
            "min_app_version": str(it.get("min_app_version", "0.0.0")),
        }
        for it in items
        if it.get("category") == "APP_SKILLS" and isinstance(it.get("data"), dict)
    ]
    connector_rows = [
        {**it["data"], "sort": it.get("sort", 0)}
        for it in items
        if it.get("category") == "CONN_DEFS" and isinstance(it.get("data"), dict)
    ]
    expert_rows = [
        {**it["data"], "sort": it.get("sort", 0)}
        for it in items
        if it.get("category") == "EXPERT_DEFS" and isinstance(it.get("data"), dict)
    ]
    # WB-215：第三方 SkillHub 是每台 App 的本地市场，不属于 Server 控制平面。
    # 过滤旧 Server 版本可能仍残留的镜像/分类/精选，避免再次写入本地 downlink。
    local_market_categories = {"skill", "skill-category", "SKILLHUB_FEATURED"}
    showcase_rows = []
    for it in items:
        if it.get("category") in {"APP_SKILLS", "CONN_DEFS", "EXPERT_DEFS"} or it.get("category") in local_market_categories:
            continue
        if it.get("category") in {"SKILL_RECOMMENDATIONS", "CONNECTOR_RECOMMENDATIONS", "EXPERT_RECOMMENDATIONS"} and isinstance(it.get("data"), dict):
            it = {**it, "data": {**it["data"], "_enabled": bool(it.get("enabled", True))}}
        showcase_rows.append(it)
    skill_result = db.replace_server_skill_catalog(skill_rows)
    connector_result = db.replace_server_connector_catalog(connector_rows)
    expert_result = db.replace_server_expert_catalog(expert_rows)
    db.replace_all_downlink(showcase_rows)
    next_revision = str(snapshot.get("revision") or "")
    if next_revision:
        db.set_user_setting(LOCAL_USER_ID, _CATALOG_REVISION_KEY, next_revision)
    return {
        "downlinked": len(items), "reachable": True,
        "unchanged": False, "revision": next_revision,
        "skills": skill_result["inserted"], "skills_skipped": skill_result["skipped"],
        "connectors": connector_result["inserted"], "connectors_skipped": connector_result["skipped"],
        "experts": expert_result["inserted"], "experts_skipped": expert_result["skipped"],
        "tools": tool_result["inserted"], "tools_skipped": tool_result["skipped"],
        "tools_preserved": tool_result["preserved"],
    }
