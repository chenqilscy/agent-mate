"""下行同步：本地 backend 从 Hub 拉项目/成员镜像进本地（WB-062 Phase 2）。

Hub 项目落本地 `projects`(origin='hub')，成员落 `project_members`——WB-050 的
`project_access_role` 读同一批表，故镜像后本地访问控制「自动」认它（owner/成员按 Hub 侧 id 对齐，
与鉴权桥镜像的账号 id 一致）。**只拉控制平面元数据**（项目名/指令/loadout/成员），
绝不涉及 LLM 凭据 / 连接器 secret / 沙箱工作区文件（铁律 4/11）。Hub 不可达 → 返回 0、不报错。

这些是**同步阻塞**调用——放在 FastAPI 的**同步路由**里跑（自动走线程池，不占事件循环）。
"""
from __future__ import annotations

import hub_client
from storage import db


def pull(token: str) -> dict:
    """用请求携带的 Hub token 拉该账号在 Hub 的项目 + 成员，幂等镜像进本地。返回 {synced, projects}。"""
    projects = hub_client.list_projects(token)
    if not projects:
        return {"synced": 0, "projects": []}
    synced: list[str] = []
    for p in projects:
        pid = p.get("id")
        if not pid:
            continue
        db.mirror_hub_project(
            id=pid, name=p.get("name", ""), owner_id=p.get("owner_id", ""),
            instruction=p.get("instruction", ""), connectors=p.get("connectors", []),
            experts=p.get("experts", []), skills=p.get("skills", []),
        )
        members = hub_client.list_project_members(token, pid) or []
        db.replace_hub_project_members(pid, members)
        synced.append(pid)
    return {"synced": len(synced), "projects": synced}
