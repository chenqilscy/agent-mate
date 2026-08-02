"""Pure project-health calculation shared by Server and local backend (WB-351)."""
from __future__ import annotations

import time
from datetime import date
from typing import Any, Iterable, Mapping


def _value(item: Any, key: str, default: Any = "") -> Any:
    if isinstance(item, Mapping):
        return item.get(key, default)
    return getattr(item, key, default)


def build_project_health(
    work_items: Iterable[Any],
    milestones: Iterable[Any],
    governance: Iterable[Any],
    *,
    source: str,
    stale: bool = False,
    as_of: str | None = None,
    computed_at: float | None = None,
) -> dict[str, Any]:
    """Build one explainable health contract without reading or mutating storage."""
    today = as_of or date.today().isoformat()
    calculated_at = float(computed_at if computed_at is not None else time.time())
    items = list(work_items)
    milestone_rows = list(milestones)
    records = list(governance)
    roots = [item for item in items if not str(_value(item, "parent_id") or "")]
    unfinished = [item for item in roots if _value(item, "status") != "done"]
    overdue = [item for item in unfinished if str(_value(item, "due_date") or "") < today and _value(item, "due_date")]
    blocked = [item for item in unfinished if _value(item, "status") == "paused"]
    risks = [row for row in records if _value(row, "record_type") == "risk" and _value(row, "status") != "closed"]
    critical_risks = [row for row in risks if _value(row, "severity") == "critical"]
    high_risks = [row for row in risks if _value(row, "severity") == "high"]
    pending_decisions = [row for row in records if _value(row, "record_type") == "decision" and _value(row, "status") == "proposed"]

    milestone_health: list[dict[str, Any]] = []
    overdue_milestones = 0
    critical_milestones = 0
    for milestone in milestone_rows:
        milestone_id = str(_value(milestone, "id") or "")
        related = [item for item in roots if str(_value(item, "milestone_id") or "") == milestone_id]
        related_unfinished = [item for item in related if _value(item, "status") != "done"]
        related_blocked = [item for item in related_unfinished if _value(item, "status") == "paused"]
        related_risks = [row for row in risks if str(_value(row, "milestone_id") or "") == milestone_id]
        related_critical = sum(_value(row, "severity") == "critical" for row in related_risks)
        related_high = sum(_value(row, "severity") == "high" for row in related_risks)
        related_pending = sum(
            str(_value(row, "milestone_id") or "") == milestone_id for row in pending_decisions
        )
        due_date = str(_value(milestone, "due_date") or "")
        is_closed = _value(milestone, "status") == "closed"
        is_overdue = bool(due_date and due_date < today and not is_closed)
        if is_overdue:
            overdue_milestones += 1
        reasons: list[str] = []
        if related_critical:
            reasons.append("critical_risk")
        if is_overdue:
            reasons.append("overdue")
        if related_blocked:
            reasons.append("blocked_work")
        if related_high:
            reasons.append("high_risk")
        if related_pending:
            reasons.append("pending_decision")
        health = "healthy"
        if related_critical or (is_overdue and related_unfinished):
            health = "critical"
            critical_milestones += 1
        elif is_overdue or related_blocked or related_high or related_pending:
            health = "attention"
        completed = len(related) - len(related_unfinished)
        milestone_health.append({
            "id": milestone_id,
            "name": str(_value(milestone, "name") or ""),
            "status": str(_value(milestone, "status") or "open"),
            "health": health,
            "reasons": reasons,
            "due_date": due_date,
            "overdue": is_overdue,
            "total_tasks": len(related),
            "completed_tasks": completed,
            "completion_percent": round(completed * 100 / len(related)) if related else 0,
            "blocked_tasks": len(related_blocked),
            "high_risks": related_high,
            "critical_risks": related_critical,
            "pending_decisions": related_pending,
        })

    reasons: list[dict[str, Any]] = []
    reason_values = (
        ("critical_risk", len(critical_risks), "存在未关闭的严重风险"),
        ("critical_milestone", critical_milestones, "里程碑已逾期且仍有未完成任务"),
        ("high_risk", len(high_risks), "存在未关闭的高风险"),
        ("overdue_work", len(overdue), "存在逾期工作项"),
        ("blocked_work", len(blocked), "存在阻塞工作项"),
        ("overdue_milestone", overdue_milestones, "存在逾期里程碑"),
        ("pending_decision", len(pending_decisions), "存在待决策事项"),
    )
    for code, count, label in reason_values:
        if count:
            reasons.append({"code": code, "count": count, "label": label})

    status = "healthy"
    if critical_risks or critical_milestones:
        status = "critical"
    elif reasons:
        status = "attention"
    completed_tasks = len(roots) - len(unfinished)
    return {
        "status": status,
        "source": source,
        "stale": bool(stale),
        "computed_at": calculated_at,
        "as_of": today,
        "summary": {
            "total_tasks": len(roots),
            "completed_tasks": completed_tasks,
            "completion_percent": round(completed_tasks * 100 / len(roots)) if roots else 0,
            "overdue_tasks": len(overdue),
            "blocked_tasks": len(blocked),
            "open_milestones": sum(_value(row, "status") != "closed" for row in milestone_rows),
            "overdue_milestones": overdue_milestones,
            "open_risks": len(risks),
            "high_risks": len(high_risks),
            "critical_risks": len(critical_risks),
            "pending_decisions": len(pending_decisions),
        },
        "reasons": reasons,
        "milestones": milestone_health,
    }


def build_health_portfolio(
    items: Iterable[Mapping[str, Any]],
    *,
    source: str,
    computed_at: float | None = None,
) -> dict[str, Any]:
    """Aggregate already-authorized project health without duplicating UI rules."""
    calculated_at = float(computed_at if computed_at is not None else time.time())
    rows = [dict(item) for item in items]
    rank = {"critical": 0, "attention": 1, "healthy": 2}
    rows.sort(
        key=lambda row: (
            rank.get(str(_value(_value(row, "health", {}), "status") or ""), 3),
            -float(_value(_value(row, "project", {}), "updated_at", 0) or 0),
            str(_value(_value(row, "project", {}), "name") or "").casefold(),
        )
    )

    def health_count(status: str) -> int:
        return sum(str(_value(_value(row, "health", {}), "status") or "") == status for row in rows)

    def summary_total(key: str) -> int:
        return sum(int(_value(_value(_value(row, "health", {}), "summary", {}), key, 0) or 0) for row in rows)

    return {
        "items": rows,
        "summary": {
            "total_projects": len(rows),
            "critical_projects": health_count("critical"),
            "attention_projects": health_count("attention"),
            "healthy_projects": health_count("healthy"),
            "stale_projects": sum(bool(_value(_value(row, "health", {}), "stale", False)) for row in rows),
            "overdue_tasks": summary_total("overdue_tasks"),
            "blocked_tasks": summary_total("blocked_tasks"),
            "critical_risks": summary_total("critical_risks"),
            "pending_decisions": summary_total("pending_decisions"),
        },
        "source": source,
        "stale": any(bool(_value(_value(row, "health", {}), "stale", False)) for row in rows),
        "computed_at": calculated_at,
    }
