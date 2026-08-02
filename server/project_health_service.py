"""Server-authoritative project-health observation and transition alerts (WB-354)."""
from __future__ import annotations

import sys
from pathlib import Path

import db

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from shared.project_health import build_project_health  # noqa: E402

_STATUS_LABEL = {"healthy": "健康", "attention": "需关注", "critical": "严重风险"}


def calculate_project_health(project_id: str) -> dict:
    return build_project_health(
        db.list_work_items(project_id),
        db.list_milestones(project_id),
        db.list_project_governance(project_id),
        source="server",
    )


def observe_project_health(project_id: str, *, actor_name: str = "AgentMate") -> dict | None:
    health = calculate_project_health(project_id)
    event = db.observe_project_health(project_id, health)
    if event is None or event["direction"] != "worsened":
        return event
    project = db.get_project(project_id)
    project_name = project.name if project else "项目"
    title = f"项目健康升级为{_STATUS_LABEL[event['to_status']]}"
    reasons = health.get("reasons") if isinstance(health.get("reasons"), list) else []
    reason_label = reasons[0].get("label") if reasons and isinstance(reasons[0], dict) else "请及时检查项目风险与计划"
    body = f"{project_name}：{reason_label}"
    for member in db.list_project_members(project_id):
        db.add_notification(
            account_id=member["account_id"], kind="project_health", title=title,
            body=body[:500], project_id=project_id, actor_name=actor_name,
            dedupe_key=f"project-health:{event['id']}",
        )
    return event


def scan_accessible_projects(account_id: str) -> dict:
    events = []
    projects = db.list_projects_for(account_id)
    for project, _role in projects:
        event = observe_project_health(project.id)
        if event is not None:
            events.append(event)
    return {"scanned": len(projects), "events": events}
