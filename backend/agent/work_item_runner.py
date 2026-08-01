"""Durable WorkItem → Session → Run execution bridge (WB-255/WB-345)."""
from __future__ import annotations

import asyncio
from typing import Optional

import server_client
import server_sync
from agent import background_worker, runtime
from storage import db
from storage.models import User, WorkItem

JOB_KIND = "work_item_run"
# Compatibility for existing internal tests/diagnostics. Durable truth lives in background_jobs.
_tasks: dict[str, asyncio.Task[None]] = {}
_server_tokens: dict[str, str] = {}


def _prompt(item: WorkItem) -> str:
    details = item.description.strip()
    text = f"完成项目工作项：{item.title}"
    if details:
        text += f"\n\n要求：\n{details}"
    return text + "\n\n请真实执行并生成可验收交付物；在产物被人工验收前不要把工作项标记为完成。"


def _run_key(launch: dict, attempt: int) -> str:
    return launch["idempotency_key"] if attempt <= 1 else f"{launch['idempotency_key']}:attempt:{attempt}"


def _attempt_run(job: dict, launch: dict, attempt: int | None = None):
    number = int(job.get("attempt") or 1) if attempt is None else attempt
    return db.get_run_by_idempotency(launch["owner_id"], _run_key(launch, number))


async def _emit_final(launch: dict, item: WorkItem, user: User) -> None:
    run = db.get_run(launch.get("run_id") or "") if launch.get("run_id") else None
    server_sync.enqueue_work_item_event(
        project_id=item.project_id, work_item_id=item.id, launch_id=launch["id"],
        actor_id=user.id, status=launch.get("status", "failed"),
        artifact_count=len(db.list_artifacts(run.id)) if run else 0,
    )


async def _fail_launch(job: dict) -> None:
    launch = db.get_work_item_launch(str(job.get("entity_id") or ""))
    if not launch or launch["status"] in {"completed", "failed", "cancelled"}:
        return
    item = db.get_work_item(launch["work_item_id"])
    user = db.get_user(launch["owner_id"])
    if not item or not user:
        db.finish_work_item_launch(
            launch["id"], status="failed", error_code=str(job.get("error_code") or "scope_missing"),
            error_message=str(job.get("error_message") or "工作项或运行账户不存在"),
        )
        return
    run = _attempt_run(job, launch)
    code = (run.error_code if run else None) or str(job.get("error_code") or "runner_error")
    message = (run.error_message if run else None) or str(job.get("error_message") or "执行失败")
    launch = db.finish_work_item_launch(
        launch["id"], status="failed", run_id=run.id if run else None,
        error_code=code, error_message=message,
    )
    db.update_work_item(item.id, status="paused")
    token = _server_tokens.pop(launch["id"], "") or db.get_server_identity(user.id) or ""
    if token:
        try:
            await asyncio.to_thread(
                server_client.update_work_item, token, item.project_id, item.id, {"status": "paused"},
            )
        except Exception:  # local failure evidence must survive an unavailable Server
            pass
    db.create_notification(
        user_id=user.id, kind="work_item_run", title=f"工作项执行失败：{item.title}",
        body=f"{code or 'run_failed'}，可在工作项中查看并重跑。",
        project_id=item.project_id, actor_name="AgentMate",
    )
    await _emit_final(launch, item, user)


async def _execute_job(job: dict) -> None:
    launch_id = str(job["entity_id"])
    launch = db.get_work_item_launch(launch_id)
    if not launch:
        raise background_worker.TerminalJobError("工作项执行记录不存在", code="launch_missing")
    item = db.get_work_item(launch["work_item_id"])
    user = db.get_user(launch["owner_id"])
    session = db.get_session(launch.get("session_id") or "")
    if not item or not user or not session or session.owner_id != user.id:
        raise background_worker.TerminalJobError("工作项、运行账户或执行会话不存在", code="scope_missing")

    attempt = int(job["attempt"])
    retry_of = None
    if attempt > 1:
        previous = _attempt_run(job, launch, attempt - 1)
        if previous and previous.status in {"completed", "accepted"}:
            launch = db.finish_work_item_launch(launch_id, status="completed", run_id=previous.id)
            await _emit_final(launch, item, user)
            return
        if previous and previous.status in {"running", "planning", "waiting_approval"}:
            previous = db.set_run_status(
                previous.id, "failed", error_code="worker_restarted",
                error_message="后台任务租约失效，已由恢复尝试接管",
            )
        if previous and previous.status in {"failed", "cancelled", "paused"}:
            retry_of = previous.id

    key = _run_key(launch, attempt)
    async for _ in runtime.run_chat(
        session, user, _prompt(item), model=job.get("payload", {}).get("model"),
        refs=[{
            "kind": "todo", "itemId": item.id, "name": item.title,
            "content": item.description or item.title,
        }],
        idempotency_key=key, retry_of=retry_of,
    ):
        pass
    run = db.get_run_by_idempotency(user.id, key)
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
        launch = db.finish_work_item_launch(launch_id, status="completed", run_id=run.id)
        _server_tokens.pop(launch_id, None)
        await _emit_final(launch, item, user)
        return
    code = run.error_code if run else "run_missing"
    message = (run.error_message if run else "执行未产生 Run 记录") or "执行失败"
    if attempt >= int(job["max_attempts"]):
        raise background_worker.TerminalJobError(message, code=code or "run_failed")
    db.mark_work_item_launch_retry(
        launch_id, run_id=run.id if run else None,
        error_code=code or "run_failed", error_message=message,
    )
    raise RuntimeError(f"{code or 'run_failed'}: {message}")


async def _recover(_job: dict) -> None:
    for launch in db.list_active_work_item_launches():
        background_worker.enqueue(
            owner_id=launch["owner_id"], kind=JOB_KIND, entity_id=launch["id"],
            idempotency_key=f"work-item-launch:{launch['id']}", payload={}, max_attempts=3,
        )


background_worker.register_handler(JOB_KIND, _execute_job, recover=_recover, failed=_fail_launch)


async def start(
    item: WorkItem, user: User, idempotency_key: str, *, model: Optional[str] = None,
    server_token: str = "",
) -> tuple[dict, bool]:
    key = f"work-item:{item.id}:{idempotency_key.strip()[:120]}"
    launch, created = db.create_work_item_launch(
        work_item_id=item.id, owner_id=user.id, idempotency_key=key,
    )
    if not created:
        if launch.get("status") in {"queued", "running"}:
            _, _, task = background_worker.enqueue(
                owner_id=user.id, kind=JOB_KIND, entity_id=launch["id"],
                idempotency_key=f"work-item-launch:{launch['id']}",
                payload={"model": model} if model else {}, max_attempts=3,
            )
            if task:
                _tasks[launch["id"]] = task
                task.add_done_callback(
                    lambda _done, launch_id=launch["id"]: _tasks.pop(launch_id, None)
                )
        return launch, False
    session = db.create_session(
        owner_id=user.id, title=item.title[:80], kind="projexec", project_id=item.project_id,
    )
    launch = db.attach_work_item_launch_session(launch["id"], session.id)
    db.update_work_item(item.id, status="doing")
    if server_token:
        _server_tokens[launch["id"]] = server_token
    _, _, task = background_worker.enqueue(
        owner_id=user.id, kind=JOB_KIND, entity_id=launch["id"],
        idempotency_key=f"work-item-launch:{launch['id']}",
        payload={"model": model} if model else {}, max_attempts=3,
    )
    if task:
        _tasks[launch["id"]] = task
        task.add_done_callback(lambda _done, launch_id=launch["id"]: _tasks.pop(launch_id, None))
    return launch, True
