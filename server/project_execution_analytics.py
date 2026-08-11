"""Versioned, permission-neutral aggregation of project Run and Delivery data (WB-503)."""
from __future__ import annotations

import json
import math
import time
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import db
import run_protocol_store


METRIC_VERSION = "project-execution-v2"
SUCCESS = {"completed", "succeeded"}
TERMINAL = SUCCESS | {"failed", "cancelled"}
ACTIVE = {"queued", "recoverable", "leased", "running", "planning", "waiting_user", "paused"}


def _json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return fallback


def _seconds(start: Any, end: Any) -> float | None:
    if start is None or end is None:
        return None
    return max(0.0, float(end) - float(start))


def _round(value: float | int) -> float:
    return round(float(value), 3)


def _average(values: list[float]) -> float | None:
    return _round(sum(values) / len(values)) if values else None


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return _round(ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)])


def _run_view(
    run: dict[str, Any], titles: dict[str, str], *, as_of: float,
) -> dict[str, Any]:
    queue_seconds = _seconds(run.get("created_at"), run.get("started_at"))
    queue_live = False
    if queue_seconds is None and str(run.get("status") or "") in {"queued", "recoverable"}:
        queue_seconds = _seconds(run.get("created_at"), as_of)
        queue_live = queue_seconds is not None
    execution_seconds = _seconds(run.get("started_at"), run.get("ended_at"))
    return {
        "run_id": str(run["id"]),
        "work_item_id": str(run.get("work_item_id") or ""),
        "work_item_title": titles.get(str(run.get("work_item_id") or ""), "未绑定任务"),
        "status": str(run.get("status") or "queued"),
        "error_code": str(run.get("error_code") or ""),
        "queue_seconds": queue_seconds,
        "queue_live": queue_live,
        "execution_seconds": execution_seconds,
        "tokens": int(run.get("prompt_tokens") or 0) + int(run.get("completion_tokens") or 0),
        "estimated_cost": (float(run["estimated_cost"]) if run.get("estimated_cost") is not None else None),
        "cost_currency": str(run.get("cost_currency") or ""),
        "device_id": str(run.get("device_id") or run.get("target_device_id") or ""),
        "device_name": str(run.get("device_name") or ""),
        "created_at": float(run.get("created_at") or 0),
    }


def build_project_execution_analytics(
    project_id: str, *, days: int = 7, timezone_name: str = "UTC", now: float | None = None,
) -> dict[str, Any]:
    """Aggregate only Server-owned project rows; authorization is enforced by the router."""
    if days not in {7, 30, 90}:
        raise ValueError("days must be one of 7, 30, 90")
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("invalid timezone") from exc

    window_end = float(now if now is not None else time.time())
    window_start = window_end - days * 86400
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT r.*,l.device_id,d.name AS device_name FROM business_runs r "
        "LEFT JOIN run_leases l ON l.id=(SELECT l2.id FROM run_leases l2 WHERE l2.run_id=r.id "
        "ORDER BY l2.lease_epoch DESC,l2.issued_at DESC LIMIT 1) "
        "LEFT JOIN agent_devices d ON d.id=l.device_id "
        "WHERE r.project_id=? AND r.deleted_at=0 AND r.created_at>=? AND r.created_at<? "
        "ORDER BY r.created_at,r.id",
        (project_id, window_start, window_end),
    ).fetchall()
    runs: list[dict[str, Any]] = []
    for row in rows:
        run = dict(row)
        run["required_capabilities"] = _json(run.get("required_capabilities"), [])
        runs.append(run)

    title_rows = conn.execute(
        "SELECT id,title FROM work_items WHERE project_id=?", (project_id,),
    ).fetchall()
    titles = {str(row["id"]): str(row["title"]) for row in title_rows}
    queue_values = [
        value for run in runs
        if (value := _seconds(run.get("created_at"), run.get("started_at"))) is not None
    ]
    execution_values = [
        value for run in runs if str(run.get("status")) in TERMINAL
        if (value := _seconds(run.get("started_at"), run.get("ended_at"))) is not None
    ]
    completed = [run for run in runs if str(run.get("status")) in SUCCESS]
    failed = [run for run in runs if str(run.get("status")) == "failed"]
    cancelled = [run for run in runs if str(run.get("status")) == "cancelled"]
    decided = len(completed) + len(failed)

    asset_rows = conn.execute(
        "SELECT a.* FROM business_assets a JOIN business_runs r ON r.id=a.run_id "
        "WHERE r.project_id=? AND r.deleted_at=0 AND r.created_at>=? AND r.created_at<? "
        "AND a.deleted_at=0",
        (project_id, window_start, window_end),
    ).fetchall()
    assets = [dict(row) for row in asset_rows]
    verified_assets = [
        asset for asset in assets
        if str(asset.get("storage_state")) == "committed"
        and str(asset.get("validation_status")) == "verified"
    ]
    acceptance_rows = conn.execute(
        "SELECT a.* FROM work_item_acceptances a "
        "WHERE a.project_id=? AND a.accepted_at>=? AND a.accepted_at<?",
        (project_id, window_start, window_end),
    ).fetchall()
    acceptance_by_item = {str(row["work_item_id"]): str(row["run_id"]) for row in acceptance_rows}

    # Delivery quality is an event-time cohort, not a slice of runs created in
    # the window. Looking at the complete success history prevents a retry just
    # inside the window from being relabelled as the WorkItem's first success.
    success_history = [dict(row) for row in conn.execute(
        "SELECT id,work_item_id,created_at,ended_at FROM business_runs "
        "WHERE project_id=? AND deleted_at=0 AND work_item_id IS NOT NULL AND work_item_id!='' "
        "AND status IN ('completed','succeeded') "
        "ORDER BY COALESCE(ended_at,created_at),id",
        (project_id,),
    ).fetchall()]
    first_success_by_item: dict[str, dict[str, Any]] = {}
    for run in success_history:
        first_success_by_item.setdefault(str(run["work_item_id"]), run)
    first_pass_cohort = {
        work_item_id: run for work_item_id, run in first_success_by_item.items()
        if window_start <= float(run.get("ended_at") or run.get("created_at") or 0) < window_end
    }
    first_pass_total = len(first_pass_cohort)
    first_pass_accepted = sum(
        acceptance_by_item.get(work_item_id) == str(run["id"])
        for work_item_id, run in first_pass_cohort.items()
    )
    rework_runs = sum(
        first_success_by_item.get(str(run["work_item_id"]), {}).get("id") != run["id"]
        and window_start <= float(run.get("ended_at") or run.get("created_at") or 0) < window_end
        for run in success_history
    )

    blocker_counter: Counter[tuple[str, str]] = Counter()
    for run in runs:
        if str(run.get("status")) not in {"queued", "recoverable"}:
            continue
        context = run_protocol_store.queue_context(run)
        if context:
            blocker_counter[(str(context.get("reason") or "unknown"), str(context.get("message") or ""))] += 1

    error_counter = Counter(str(run.get("error_code") or "unknown") for run in failed)
    costs: dict[str, float] = defaultdict(float)
    unpriced_runs = 0
    for run in runs:
        if run.get("estimated_cost") is None:
            unpriced_runs += 1
        else:
            costs[str(run.get("cost_currency") or "unspecified")] += float(run["estimated_cost"])

    trend: dict[str, dict[str, Any]] = {}
    for run in runs:
        day = datetime.fromtimestamp(float(run.get("created_at") or 0), timezone).date().isoformat()
        bucket = trend.setdefault(day, {"date": day, "runs": 0, "completed": 0, "failed": 0, "tokens": 0, "estimated_cost": {}})
        bucket["runs"] += 1
        status = str(run.get("status") or "")
        if status in SUCCESS:
            bucket["completed"] += 1
        elif status == "failed":
            bucket["failed"] += 1
        bucket["tokens"] += int(run.get("prompt_tokens") or 0) + int(run.get("completion_tokens") or 0)
        if run.get("estimated_cost") is not None:
            currency = str(run.get("cost_currency") or "unspecified")
            bucket["estimated_cost"][currency] = _round(bucket["estimated_cost"].get(currency, 0) + float(run["estimated_cost"]))

    device_ids = {
        str(run.get("device_id") or run.get("target_device_id") or "")
        for run in runs if run.get("device_id") or run.get("target_device_id")
    }
    device_snapshots: dict[str, dict[str, Any]] = {}
    owner_ids = {str(run.get("owner_id") or "") for run in runs}
    for owner_id in owner_ids:
        if not owner_id:
            continue
        for device in run_protocol_store.list_devices(owner_id):
            if str(device["id"]) in device_ids:
                device_snapshots[str(device["id"])] = device
    device_runs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        device_id = str(run.get("device_id") or run.get("target_device_id") or "")
        if device_id:
            device_runs[device_id].append(run)
    devices = []
    for device_id, values in device_runs.items():
        snapshot = device_snapshots.get(device_id, {})
        devices.append({
            "device_id": device_id,
            "device_name": str(snapshot.get("name") or values[-1].get("device_name") or "Local Agent"),
            "readiness": str(snapshot.get("readiness") or "unknown"),
            "runs": len(values),
            "completed": sum(str(run.get("status")) in SUCCESS for run in values),
            "failed": sum(str(run.get("status")) == "failed" for run in values),
            "tokens": sum(int(run.get("prompt_tokens") or 0) + int(run.get("completion_tokens") or 0) for run in values),
            "capacity": snapshot.get("capacity") or {"active": 0, "parallel": 0, "resident": 0, "resident_limit": 0},
        })
    devices.sort(key=lambda item: (-int(item["runs"]), str(item["device_name"])))

    run_views = [_run_view(run, titles, as_of=window_end) for run in runs]
    slow_runs = sorted(
        [view for view in run_views if view["queue_seconds"] is not None or view["execution_seconds"] is not None],
        key=lambda view: float(view["queue_seconds"] or 0) + float(view["execution_seconds"] or 0),
        reverse=True,
    )[:10]
    costly_runs = sorted(
        [view for view in run_views if view["estimated_cost"] is not None],
        key=lambda view: float(view["estimated_cost"] or 0), reverse=True,
    )[:10]

    return {
        "metric_version": METRIC_VERSION,
        "project_id": project_id,
        "window": {"days": days, "timezone": timezone_name, "start": window_start, "end": window_end},
        "definitions": {
            "scope": "按当前可访问 project_id 过滤，统计 Server business_runs.created_at 落在 [start,end) 的记录",
            "success_rate": "成功或完成 Run /（成功或完成 Run + 失败 Run）；取消不进入分母",
            "queue_seconds": "started_at - created_at；尚未启动的排队 Run 不进入耗时分位数",
            "execution_seconds": "仅终态 Run 计算 ended_at - started_at",
            "first_pass_acceptance": "全历史首次成功发生在窗口内的任务中，且验收也在窗口内并指向该首次成功 Run 的任务占比；后续验收不回写历史窗口",
            "rework_runs": "成功完成时间落在窗口内、且不是该 WorkItem 全历史首次成功的 Run 数",
            "cost": "按记录币种汇总 estimated_cost；空成本单独计为未定价，不按零成本处理",
            "queue_blockers": "当前持久化队列、设备和租约快照；活跃排队 Run 的明细时长按窗口结束时刻计算，但不进入已启动 Run 的耗时分位数",
            "privacy": "不聚合凭据、提示词、消息、事件载荷、本机路径或私密文件内容",
        },
        "summary": {
            "runs": len(runs),
            "completed": len(completed),
            "failed": len(failed),
            "cancelled": len(cancelled),
            "active": sum(str(run.get("status")) in ACTIVE for run in runs),
            "success_rate": (_round(len(completed) / decided) if decided else None),
            "retry_runs": sum(bool(run.get("retry_of")) for run in runs),
            "work_items_executed": len({str(run.get("work_item_id")) for run in runs if run.get("work_item_id")}),
            "queue_avg_seconds": _average(queue_values),
            "queue_p95_seconds": _p95(queue_values),
            "execution_avg_seconds": _average(execution_values),
            "execution_p95_seconds": _p95(execution_values),
            "prompt_tokens": sum(int(run.get("prompt_tokens") or 0) for run in runs),
            "cached_prompt_tokens": sum(int(run.get("cached_prompt_tokens") or 0) for run in runs),
            "completion_tokens": sum(int(run.get("completion_tokens") or 0) for run in runs),
            "estimated_cost": {key: _round(value) for key, value in sorted(costs.items())},
            "unpriced_runs": unpriced_runs,
        },
        "delivery": {
            "artifacts": len(assets),
            "verified_artifacts": len(verified_assets),
            "artifact_verification_rate": (_round(len(verified_assets) / len(assets)) if assets else None),
            "accepted_deliveries": len(acceptance_rows),
            "first_pass_total": first_pass_total,
            "first_pass_accepted": first_pass_accepted,
            "first_pass_acceptance_rate": (_round(first_pass_accepted / first_pass_total) if first_pass_total else None),
            "rework_runs": rework_runs,
        },
        "trend": [trend[key] for key in sorted(trend)],
        "queue_blockers": [
            {"reason": reason, "message": message, "runs": count}
            for (reason, message), count in blocker_counter.most_common()
        ],
        "failures": [{"error_code": code, "runs": count} for code, count in error_counter.most_common()],
        "devices": devices,
        "slow_runs": slow_runs,
        "costly_runs": costly_runs,
    }
