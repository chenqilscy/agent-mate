"""Headless WorkItem → Session → Run execution bridge (WB-255)."""
from __future__ import annotations

import asyncio
from typing import Optional

import server_client
import server_sync
from agent import runtime
from storage import db
from storage.models import User, WorkItem

_tasks: dict[str, asyncio.Task] = {}


def _prompt(item: WorkItem) -> str:
    details = item.description.strip()
    text = f"完成项目工作项：{item.title}"
    if details:
        text += f"\n\n要求：\n{details}"
    return text + "\n\n请真实执行并生成可验收交付物；在产物被人工验收前不要把工作项标记为完成。"


async def _execute(
    launch_id: str, item: WorkItem, user: User, model: Optional[str], server_token: str,
) -> None:
    launch = db.get_work_item_launch(launch_id)
    if not launch or not launch.get("session_id"):
        return
    session = db.get_session(launch["session_id"])
    if not session:
        db.finish_work_item_launch(
            launch_id, status="failed", error_code="session_missing",
            error_message="执行会话不存在",
        )
        return
    try:
        async for _ in runtime.run_chat(
            session, user, _prompt(item), model=model,
            refs=[{
                "kind": "todo", "itemId": item.id, "name": item.title,
                "content": item.description or item.title,
            }],
            idempotency_key=launch["idempotency_key"],
        ):
            pass
        run = db.get_run_by_idempotency(user.id, launch["idempotency_key"])
        if run:
            role = db.project_access_role(item.project_id, user.id)
            db.update_run_runtime(
                run.id,
                permission_snapshot={
                    **run.permission_snapshot,
                    "project_role": role.value if role else "",
                    "work_item_id": item.id,
                    "initiated_by": user.id,
                },
            )
            run = db.get_run(run.id)
        if run and run.status in {"completed", "accepted"}:
            db.finish_work_item_launch(launch_id, status="completed", run_id=run.id)
        else:
            code = run.error_code if run else "run_missing"
            message = (run.error_message if run else "执行未产生 Run 记录") or "执行失败"
            db.finish_work_item_launch(
                launch_id, status="failed", run_id=run.id if run else None,
                error_code=code, error_message=message,
            )
            db.update_work_item(item.id, status="paused")
            if server_token:
                await asyncio.to_thread(
                    server_client.update_work_item,
                    server_token, item.project_id, item.id, {"status": "paused"},
                )
            db.create_notification(
                user_id=user.id, kind="work_item_run", title=f"工作项执行失败：{item.title}",
                body=f"{code or 'run_failed'}，可在工作项中查看并重跑。",
                project_id=item.project_id, actor_name="AgentMate",
            )
    except BaseException as exc:
        run = db.get_run_by_idempotency(user.id, launch["idempotency_key"])
        db.finish_work_item_launch(
            launch_id, status="cancelled" if isinstance(exc, asyncio.CancelledError) else "failed",
            run_id=run.id if run else None,
            error_code="cancelled" if isinstance(exc, asyncio.CancelledError) else "runner_error",
            error_message=str(exc)[:500],
        )
        db.update_work_item(item.id, status="paused")
        if isinstance(exc, asyncio.CancelledError):
            raise
    finally:
        current = db.get_work_item_launch(launch_id) or {}
        final_run = db.get_run(current.get("run_id")) if current.get("run_id") else None
        server_sync.enqueue_work_item_event(
            project_id=item.project_id, work_item_id=item.id, launch_id=launch_id,
            actor_id=user.id, status=current.get("status", "failed"),
            artifact_count=len(db.list_artifacts(final_run.id)) if final_run else 0,
        )
        _tasks.pop(launch_id, None)


async def start(
    item: WorkItem, user: User, idempotency_key: str, *, model: Optional[str] = None,
    server_token: str = "",
) -> tuple[dict, bool]:
    key = f"work-item:{item.id}:{idempotency_key.strip()[:120]}"
    launch, created = db.create_work_item_launch(
        work_item_id=item.id, owner_id=user.id, idempotency_key=key,
    )
    if not created:
        return launch, False
    session = db.create_session(
        owner_id=user.id, title=item.title[:80], kind="projexec", project_id=item.project_id,
    )
    launch = db.attach_work_item_launch_session(launch["id"], session.id)
    db.update_work_item(item.id, status="doing")
    task = asyncio.create_task(_execute(launch["id"], item, user, model, server_token))
    _tasks[launch["id"]] = task
    return launch, True
