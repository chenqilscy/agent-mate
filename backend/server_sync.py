"""下行同步：本地 backend 从 Server 拉项目/成员镜像进本地（WB-062 Phase 2）。

Server 项目落本地 `projects`(origin='server')，成员落 `project_members`——WB-050 的
`project_access_role` 读同一批表，故镜像后本地访问控制「自动」认它（owner/成员按 Server 侧 id 对齐，
与鉴权桥镜像的账号 id 一致）。**只拉控制平面元数据**（项目名/指令/loadout/成员），
绝不涉及 LLM 凭据 / 连接器 secret / 沙箱工作区文件（铁律 4/11）。Server 不可达 → 返回 0、不报错。

这些是**同步阻塞**调用——放在 FastAPI 的**同步路由**里跑（自动走线程池，不占事件循环）。
"""
from __future__ import annotations

import server_client
from agent.skills import canonical_skill_keys
from config import settings
from storage import db
from storage.models import LOCAL_USER_ID


def pull(token: str) -> dict:
    """用请求携带的 Server token 拉该账号在 Server 的项目 + 成员，幂等镜像进本地。返回 {synced, projects}。"""
    projects = server_client.list_projects(token)
    if not projects:
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
        )
        members = server_client.list_project_members(token, pid) or []
        db.replace_server_project_members(pid, members)
        synced.append(pid)
    return {"synced": len(synced), "projects": synced}


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


def flush_outbox(limit: int = 50) -> dict:
    """后台补推：把 pending outbox 推给 Server（用各 actor 缓存的 Server token）。成功标 synced，
    失败留待下轮（断线/离线自动补推）。未接 Server → 直接返回。"""
    if not settings.server_enabled:
        return {"pushed": 0, "pending": 0}
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
    """从 Server 拉全量 builtin 目录，幂等镜像进本地 catalog_downlink（覆盖本地 showcase 分类）。
    Server 不可达 → 保留上次下发（不清空）；Server 空 → 清空 → 本地 builtin 兜底。"""
    if not settings.server_enabled:
        return {"downlinked": 0, "reachable": False}
    items = server_client.list_all_catalog(token)
    if items is None:  # 不可达：保留上次下发，别清成空
        return {"downlinked": 0, "reachable": False}
    skill_rows = [
        {**it["data"], "sort": it.get("sort", 0)}
        for it in items
        if it.get("category") == "APP_SKILLS" and isinstance(it.get("data"), dict)
    ]
    showcase_rows = [it for it in items if it.get("category") != "APP_SKILLS"]
    skill_result = db.replace_server_skill_catalog(skill_rows)
    db.replace_all_downlink(showcase_rows)
    return {
        "downlinked": len(items), "reachable": True,
        "skills": skill_result["inserted"], "skills_skipped": skill_result["skipped"],
    }
