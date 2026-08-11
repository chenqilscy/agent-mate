"""Execute Server-owned Runs through the Local Agent lease/WAL protocol."""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any

import local_agent_store
import run_transport
import server_client
from agent import run_resources, runtime, sandbox
from config import settings
from storage import db
from storage.models import Message, Project, User


log = logging.getLogger("agentmate.server-runs")
_STREAM_FLUSH_INTERVAL_SECONDS = 0.25


@dataclass
class _ActiveRun:
    task: asyncio.Task[None]
    run_id: str
    owner_id: str
    device_id: str
    project_id: str
    workspace: str
    phase: str = "leased"
    slot_held: bool = True


_active_runs: dict[str, _ActiveRun] = {}
_active_guard = threading.Lock()
_flush_locks: dict[tuple[int, str, str], asyncio.Lock] = {}
_identity_cursor = 0
_capacity_used = 0
_capacity_by_owner: dict[str, int] = {}
_worker_id = f"server-run-worker:{uuid.uuid4()}"
_is_leader = False


@dataclass
class _ControlState:
    stopped: bool = False
    terminal: bool = False
    paused: bool = False
    pause_requested: bool = False
    pending_pause_commands: list[str] = field(default_factory=list)
    gate: asyncio.Event | None = None


def _frames(chunk: str) -> list[tuple[str, dict[str, Any]]]:
    result: list[tuple[str, dict[str, Any]]] = []
    for frame in chunk.replace("\r\n", "\n").split("\n\n"):
        if not frame.strip():
            continue
        event_type = "message"
        payload_lines: list[str] = []
        for line in frame.splitlines():
            if line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("data:"):
                payload_lines.append(line[5:].strip())
        if not payload_lines:
            continue
        try:
            payload = json.loads("\n".join(payload_lines))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            result.append((event_type, payload))
    return result


async def _commit_artifact(
    *, owner_id: str, project_id: str, session_id: str, run_id: str,
    payload: dict[str, Any],
) -> None:
    """Commit a Run artifact from the Local Agent, independent of any open App page."""
    local_path = str(payload.get("path") or "").strip()
    if not local_path:
        raise ValueError("artifact event is missing its local path")
    # Lazy import avoids the Local Agent Core ↔ worker module initialization cycle.
    from local_agent_core import AssetCommitBody, commit_asset

    await asyncio.to_thread(
        commit_asset,
        AssetCommitBody(
            owner_id=owner_id, project_id=project_id, session_id=session_id,
            run_id=run_id, local_path=local_path, kind="artifact",
        ),
    )


def _project(remote: dict[str, Any], owner_id: str) -> Project:
    return Project(
        id=str(remote["id"]), name=str(remote.get("name") or ""),
        owner_id=str(remote.get("owner_id") or owner_id),
        instruction=str(remote.get("instruction") or ""),
        connectors=[str(value) for value in remote.get("connectors") or []],
        experts=[str(value) for value in remote.get("experts") or []],
        skills=[str(value) for value in remote.get("skills") or []],
        knowledge_ids=[str(value) for value in remote.get("knowledge_ids") or []],
        created_at=float(remote.get("created_at") or 0),
        updated_at=float(remote.get("updated_at") or 0), origin="server",
        org_id=str(remote.get("org_id") or "") or None,
    )


async def _flush(owner_id: str, device_token: str) -> dict[str, int]:
    loop = asyncio.get_running_loop()
    key = (id(loop), owner_id, run_transport.device_id(owner_id))
    lock = _flush_locks.setdefault(key, asyncio.Lock())
    async with lock:
        return await asyncio.to_thread(run_transport.flush_wal, owner_id, device_token)


def _set_phase(run_id: str, phase: str) -> None:
    with _active_guard:
        active = _active_runs.get(run_id)
        if active is not None:
            active.phase = phase


def _reserve_capacity(owner_id: str) -> bool:
    global _capacity_used
    with _active_guard:
        owner_used = _capacity_by_owner.get(owner_id, 0)
        if (
            _capacity_used >= settings.SERVER_RUN_MAX_CONCURRENCY
            or owner_used >= settings.SERVER_RUN_PER_OWNER_CONCURRENCY
        ):
            return False
        _capacity_used += 1
        _capacity_by_owner[owner_id] = owner_used + 1
        return True


def _release_capacity(owner_id: str) -> None:
    global _capacity_used
    with _active_guard:
        owner_used = _capacity_by_owner.get(owner_id, 0)
        if owner_used <= 0:
            return
        _capacity_used = max(0, _capacity_used - 1)
        if owner_used == 1:
            _capacity_by_owner.pop(owner_id, None)
        else:
            _capacity_by_owner[owner_id] = owner_used - 1


def _release_run_slot(run_id: str) -> None:
    with _active_guard:
        active = _active_runs.get(run_id)
        if active is None or not active.slot_held:
            return
        active.slot_held = False
        owner_id = active.owner_id
    _release_capacity(owner_id)


def _try_reacquire_run_slot(run_id: str) -> bool:
    with _active_guard:
        active = _active_runs.get(run_id)
        if active is None:
            return True  # direct unit execution is outside the supervisor pool
        if active.slot_held:
            return True
        owner_id = active.owner_id
    if not _reserve_capacity(owner_id):
        return False
    missing = False
    with _active_guard:
        active = _active_runs.get(run_id)
        if active is None:
            missing = True
        else:
            active.slot_held = True
    if missing:
        _release_capacity(owner_id)
        return False
    return True


def _memory_snapshot(owner_id: str | None = None) -> dict[str, Any]:
    with _active_guard:
        runs = [
            {
                "run_id": item.run_id, "owner_id": item.owner_id,
                "device_id": item.device_id, "project_id": item.project_id,
                "workspace": item.workspace, "phase": item.phase,
                "slot_held": item.slot_held,
            }
            for item in _active_runs.values()
            if owner_id is None or item.owner_id == owner_id
        ]
        used = _capacity_used if owner_id is None else _capacity_by_owner.get(owner_id, 0)
    visible_run_ids = {str(item["run_id"]) for item in runs}
    resources = run_resources.snapshot(owner_id)
    return {
        "max_concurrency": settings.SERVER_RUN_MAX_CONCURRENCY,
        "per_owner_concurrency": settings.SERVER_RUN_PER_OWNER_CONCURRENCY,
        "active": used,
        "resident": len(runs),
        "max_resident": settings.SERVER_RUN_MAX_RESIDENT,
        "available": max(
            0,
            (settings.SERVER_RUN_PER_OWNER_CONCURRENCY if owner_id else settings.SERVER_RUN_MAX_CONCURRENCY)
            - used,
        ),
        "leader": _is_leader,
        "runs": sorted(runs, key=lambda item: str(item["run_id"])),
        "resources": {
            key: [item for item in values if str(item.get("run_id") or "") in visible_run_ids]
            for key, values in resources.items()
        },
    }


def _filter_snapshot(payload: dict[str, Any], owner_id: str | None) -> dict[str, Any]:
    if owner_id is None:
        return payload
    runs = [item for item in payload.get("runs") or [] if str(item.get("owner_id") or "") == owner_id]
    visible = {str(item.get("run_id") or "") for item in runs}
    resources = payload.get("resources") if isinstance(payload.get("resources"), dict) else {}
    return {
        **payload,
        "active": sum(bool(item.get("slot_held")) for item in runs),
        "resident": len(runs),
        "available": max(
            0, int(payload.get("per_owner_concurrency") or settings.SERVER_RUN_PER_OWNER_CONCURRENCY)
            - sum(bool(item.get("slot_held")) for item in runs),
        ),
        "runs": runs,
        "resources": {
            key: [item for item in values if str(item.get("run_id") or "") in visible]
            for key, values in resources.items() if isinstance(values, list)
        },
    }


def snapshot(owner_id: str | None = None) -> dict[str, Any]:
    if _is_leader:
        return _memory_snapshot(owner_id)
    shared = local_agent_store.read_run_worker_snapshot()
    if shared.get("leader_active"):
        payload = shared.get("snapshot")
        if isinstance(payload, dict) and payload:
            return _filter_snapshot(payload, owner_id)
    return _memory_snapshot(owner_id)


def _publish_snapshot() -> None:
    if _is_leader:
        local_agent_store.publish_run_worker_snapshot(_worker_id, _memory_snapshot())


async def _pause_at_boundary(
    *, run_id: str, owner_id: str, device_token: str, state: _ControlState,
    execution_timeout: asyncio.Timeout, deadline: float | None,
) -> float | None:
    """Confirm a requested pause at an execution boundary and freeze its budget."""
    if not state.pause_requested or state.stopped:
        return deadline
    gate = state.gate
    if gate is None:
        raise RuntimeError("pause gate is unavailable")
    state.pause_requested = False
    state.paused = True
    _set_phase(run_id, "paused")
    gate.clear()
    run_transport.append_event(run_id, "run.paused", {"reason": "user_requested"})
    for command_id in state.pending_pause_commands:
        run_transport.append_event(run_id, "command.ack", {"command_id": command_id})
    state.pending_pause_commands.clear()
    await _flush(owner_id, device_token)
    _release_run_slot(run_id)

    loop = asyncio.get_running_loop()
    paused_at = loop.time()
    execution_timeout.reschedule(None)
    await gate.wait()
    if deadline is not None:
        deadline += loop.time() - paused_at
        execution_timeout.reschedule(deadline)
    return deadline


async def _control_loop(
    *, run_id: str, owner_id: str, device_token: str, local_session_id: str,
    state: _ControlState,
) -> None:
    acknowledged: set[str] = set()
    while not state.terminal:
        await asyncio.sleep(5)
        try:
            response = await asyncio.to_thread(
                run_transport.renew_lease, run_id, device_token, lease_seconds=30,
            )
        except run_transport.LeaseFenced:
            runtime.request_stop(local_session_id)
            state.stopped = True
            if state.gate is not None:
                state.gate.set()
            return
        for command in response.get("commands") or []:
            command_id = str(command.get("id") or "")
            if not command_id or command_id in acknowledged:
                continue
            command_type = str(command.get("command_type") or "")
            payload = command.get("payload") if isinstance(command.get("payload"), dict) else {}
            if command_type == "cancel":
                runtime.request_stop(local_session_id)
                state.stopped = True
                if state.gate is not None:
                    state.gate.set()
            elif command_type == "pause":
                if state.paused:
                    run_transport.append_event(run_id, "command.ack", {"command_id": command_id})
                    acknowledged.add(command_id)
                    continue
                # Do not acknowledge pause from the control task.  A model or
                # tool step may still be in flight.  The execution task emits
                # run.paused only after it reaches the next durable boundary.
                state.pause_requested = True
                state.pending_pause_commands.append(command_id)
                acknowledged.add(command_id)
                continue
            elif command_type == "resume":
                if state.paused:
                    if not _try_reacquire_run_slot(run_id):
                        continue
                    state.paused = False
                    _set_phase(run_id, "running")
                    run_transport.append_event(run_id, "run.started", {"resumed_from": "paused"})
                    if state.gate is not None:
                        state.gate.set()
            elif command_type == "ask_user_answer":
                if not _try_reacquire_run_slot(run_id):
                    continue
                answers = payload.get("answers") if isinstance(payload.get("answers"), list) else []
                runtime.submit_answers(local_session_id, [str(item) for item in answers])
                _set_phase(run_id, "running")
                run_transport.append_event(run_id, "run.started", {"resumed_from": "waiting_user"})
            else:
                continue
            run_transport.append_event(run_id, "command.ack", {"command_id": command_id})
            acknowledged.add(command_id)
        await _flush(owner_id, device_token)


async def _execute_run(owner_id: str, user_token: str, device_token: str, run: dict[str, Any]) -> None:
    run_id = str(run.get("id") or "")
    session_id = str(run.get("session_id") or "")
    if not run_id or not session_id:
        raise ValueError("leased Run is missing execution identity")

    _set_phase(run_id, "loading_context")
    account, session_record, messages = await asyncio.gather(
        asyncio.to_thread(server_client.verify_token, user_token),
        asyncio.to_thread(server_client.get_business_session, user_token, session_id),
        asyncio.to_thread(server_client.get_business_messages, user_token, session_id),
    )
    if not account or not session_record or messages is None:
        raise RuntimeError("Server execution context is unavailable")
    _set_phase(run_id, "preparing")
    db.upsert_external_user(owner_id, str(account.get("name") or owner_id))
    user = db.get_user(owner_id)
    if not isinstance(user, User):
        raise RuntimeError("Local execution identity could not be initialized")

    current = next((
        item for item in messages
        if str(item.get("run_id") or "") == run_id and str(item.get("role") or "") == "user"
    ), None)
    if current is None:
        raise RuntimeError("Server Run input message is missing")
    history = [
        Message(
            id=str(item.get("id") or f"server-history-{index}"), session_id="",
            role=str(item.get("role") or ""), content=str(item.get("content") or "")[:1_000_000],
            actor=str(item.get("actor_id") or item.get("role") or "server"),
        )
        for index, item in enumerate(messages)
        if item is not current and item.get("role") in {"user", "assistant"} and item.get("content")
    ]
    project_id = str(run.get("project_id") or "")
    project_override = None
    if project_id:
        remote_project = await asyncio.to_thread(server_client.get_project, user_token, project_id)
        if remote_project is None:
            raise RuntimeError("Server project execution context is unavailable")
        if str(remote_project.get("role") or "").lower() == "viewer":
            raise PermissionError("只读成员不能在此项目中执行")
        project_override = _project(remote_project, owner_id)

    local_session = db.create_session(
        owner_id=owner_id, title=str(session_record.get("title") or "对话"),
        kind=str(session_record.get("kind") or "chat"),
        space=session_record.get("space"), project_id=project_id or None,
    )
    snapshot = run.get("request_snapshot") if isinstance(run.get("request_snapshot"), dict) else {}
    permission = run.get("permission_snapshot") if isinstance(run.get("permission_snapshot"), dict) else {}
    loadout = snapshot.get("loadout") if isinstance(snapshot.get("loadout"), dict) else {}
    mode = str(run.get("mode") or "exec")
    ref_metadata = snapshot.get("refs") if isinstance(snapshot.get("refs"), list) else []
    local_input_key = str(snapshot.get("local_input_key") or "")
    staged = local_agent_store.take_run_input(owner_id, local_input_key) if local_input_key else None
    refs = staged.get("refs") if isinstance(staged, dict) and isinstance(staged.get("refs"), list) else []
    if ref_metadata and not refs:
        raise RuntimeError("Local Agent input staging is missing for this device")
    server_work_item_id = str(run.get("work_item_id") or "")
    if server_work_item_id and not any(
        isinstance(item, dict)
        and item.get("kind") == "todo"
        and str(item.get("itemId") or "") == server_work_item_id
        for item in refs
    ):
        raise RuntimeError("Local Agent task input does not match the Server Run work item")
    gate = asyncio.Event()
    gate.set()
    state = _ControlState(gate=gate)
    control = asyncio.create_task(_control_loop(
        run_id=run_id, owner_id=owner_id, device_token=device_token,
        local_session_id=local_session.id, state=state,
    ))
    stream_error = ""
    execution_source = (
        str(permission.get("execution_source") or "interactive")
        if str(permission.get("execution_source") or "interactive") in {"interactive", "background", "external"}
        else "interactive"
    )
    timeout_seconds = max(0, int(permission.get("timeout_sec") or 0))
    run_transport.append_event(run_id, "run.started", {"source": "local_agent"})
    _set_phase(run_id, "running")
    await _flush(owner_id, device_token)
    try:
        loop = asyncio.get_running_loop()
        last_stream_flush = loop.time()
        deadline = loop.time() + timeout_seconds if timeout_seconds > 0 else None
        async with asyncio.timeout_at(deadline) as execution_timeout:
            workspace_key = str(sandbox.workspace_root(
                str(run.get("workspace") or "default"), project_id or None,
            ).resolve())
            with run_resources.bind(
                run_id=run_id, owner_id=owner_id, workspace_key=workspace_key,
            ):
                async for chunk in runtime.run_chat(
                    local_session, user, str(current.get("content") or ""),
                    model=str(run.get("model_ref") or "") or None,
                    plan=mode == "plan", ask=mode == "ask",
                    experts=[str(item) for item in loadout.get("experts") or []],
                    skills=[str(item) for item in loadout.get("skills") or []],
                    bundle_ids=[str(item) for item in loadout.get("skill_bundles") or []],
                    connectors=[str(item) for item in loadout.get("connectors") or []],
                    knowledge_ids=[str(item) for item in loadout.get("knowledge_ids") or []],
                    refs=[item for item in refs if isinstance(item, dict)],
                    workspace=str(run.get("workspace") or "default"),
                    # A recovered Server lease is a new execution attempt. Reusing
                    # the old local key would make runtime.run_chat return the
                    # crashed attempt as an idempotent duplicate and falsely emit a
                    # successful terminal event without executing again.
                    idempotency_key=f"server-run:{run_id}:epoch:{int(run.get('_lease_epoch') or 0)}",
                    max_total_tokens=max(0, int(permission.get("max_total_tokens") or 0)),
                    execution_source=execution_source,
                    preauthorized_permissions=[
                        str(item) for item in permission.get("preauthorized_permissions") or []
                    ],
                    history_override=history, project_override=project_override,
                    server_token_override=user_token,
                    authoritative_run_context={
                        "session_id": session_id,
                        "run_id": run_id,
                        "work_item_id": server_work_item_id,
                    },
                ):
                    for event_type, payload in _frames(chunk):
                        if event_type == "run":
                            continue
                        if event_type == "ask_user":
                            _set_phase(run_id, "waiting_user")
                            run_transport.append_event(
                                run_id, "run.waiting_user",
                                {"questions": payload.get("questions") if isinstance(payload.get("questions"), list) else []},
                            )
                        elif event_type == "done":
                            continue
                        else:
                            run_transport.append_event(run_id, f"ui.{event_type}", payload)
                            if event_type == "artifact":
                                await _commit_artifact(
                                    owner_id=owner_id, project_id=project_id,
                                    session_id=session_id, run_id=run_id, payload=payload,
                                )
                            if event_type == "error":
                                stream_error = str(payload.get("message") or "")
                        must_flush = event_type in {"ask_user", "artifact", "error", "usage"}
                        if must_flush or loop.time() - last_stream_flush >= _STREAM_FLUSH_INTERVAL_SECONDS:
                            await _flush(owner_id, device_token)
                            last_stream_flush = loop.time()
                        else:
                            # Token streams may already be buffered in memory and
                            # yield without I/O. Give lease/control tasks an
                            # explicit scheduling boundary while the WAL remains
                            # durable and is flushed within the bounded interval.
                            await asyncio.sleep(0)
                        if event_type == "ask_user":
                            _release_run_slot(run_id)
                    # Finish the already in-flight model/tool step and all of its
                    # frames before confirming pause.  Once run.paused is durable,
                    # this body blocks before async-for can request another step.
                    deadline = await _pause_at_boundary(
                        run_id=run_id, owner_id=owner_id, device_token=device_token,
                        state=state, execution_timeout=execution_timeout, deadline=deadline,
                    )
                    if state.stopped:
                        break
        terminal_type = "run.cancelled" if state.stopped else "run.failed" if stream_error else "run.completed"
        terminal_payload = (
            {"error_code": "local_execution_failed", "error_message": stream_error}
            if stream_error else {}
        )
        run_transport.append_event(run_id, terminal_type, terminal_payload)
        _set_phase(run_id, terminal_type.removeprefix("run."))
        await _flush(owner_id, device_token)
    except Exception as exc:  # noqa: BLE001 - terminal failure must be durable
        message = str(exc)[:20000]
        try:
            run_transport.append_event(run_id, "ui.error", {"message": message})
            run_transport.append_event(
                run_id, "run.failed", {"error_code": "local_agent_worker", "error_message": message},
            )
            await _flush(owner_id, device_token)
        except Exception:  # noqa: BLE001 - the existing lease/WAL error remains observable
            log.exception("failed to persist terminal event for Run %s", run_id)
    finally:
        state.terminal = True
        control.cancel()
        await asyncio.gather(control, return_exceptions=True)
        if run_transport.lease_status(run_id) == "completed" and local_input_key:
            local_agent_store.clear_run_input(owner_id, local_input_key)


async def execute_run(owner_id: str, user_token: str, device_token: str, run: dict[str, Any]) -> None:
    """Execute one claimed Run without ever letting its preparation kill the worker."""
    try:
        await _execute_run(owner_id, user_token, device_token, run)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - a claimed Run needs a durable terminal state
        run_id = str(run.get("id") or "")
        message = str(exc)[:20000]
        log.exception("failed to prepare claimed Server Run %s", run_id or "<missing>")
        if not run_id:
            return
        try:
            run_transport.append_event(run_id, "ui.error", {"message": message})
            run_transport.append_event(
                run_id, "run.failed",
                {"error_code": "local_agent_preflight", "error_message": message},
            )
            await _flush(owner_id, device_token)
            snapshot = run.get("request_snapshot") if isinstance(run.get("request_snapshot"), dict) else {}
            local_input_key = str(snapshot.get("local_input_key") or "")
            if run_transport.lease_status(run_id) == "completed" and local_input_key:
                local_agent_store.clear_run_input(owner_id, local_input_key)
        except Exception:  # noqa: BLE001 - WAL/lease failure is retained in local status
            log.exception("failed to persist preparation failure for Run %s", run_id)


async def _execute_claimed(
    owner_id: str, user_token: str, device_token: str, run: dict[str, Any],
) -> None:
    try:
        await execute_run(owner_id, user_token, device_token, run)
    finally:
        _release_run_slot(str(run.get("id") or ""))


async def run_forever() -> None:
    """Claim Server Runs into a bounded, supervised per-owner task pool."""
    if not settings.server_enabled:
        return
    global _identity_cursor, _is_leader
    db.init_db()
    try:
        while True:
            _is_leader = await asyncio.to_thread(
                local_agent_store.acquire_run_worker_leader, _worker_id, ttl_seconds=60,
            )
            if not _is_leader:
                await asyncio.sleep(0.5 if _active_runs else 2)
                continue
            with _active_guard:
                completed = [run_id for run_id, item in _active_runs.items() if item.task.done()]
                completed_tasks = [_active_runs[run_id].task for run_id in completed]
                for run_id in completed:
                    _active_runs.pop(run_id, None)
            if completed_tasks:
                await asyncio.gather(*completed_tasks, return_exceptions=True)
            _publish_snapshot()

            claimed = False
            identities = local_agent_store.list_server_identities()
            if identities:
                offset = _identity_cursor % len(identities)
                identities = identities[offset:] + identities[:offset]
                _identity_cursor = (_identity_cursor + 1) % len(identities)
            for owner_id, user_token in identities:
                reserved = False
                try:
                    _is_leader = await asyncio.to_thread(
                        local_agent_store.acquire_run_worker_leader, _worker_id, ttl_seconds=60,
                    )
                    if not _is_leader:
                        break
                    device_token = await asyncio.to_thread(run_transport.ensure_device, owner_id, user_token)
                    if not device_token:
                        continue
                    if not await asyncio.to_thread(run_transport.heartbeat, owner_id, device_token):
                        continue
                    await _flush(owner_id, device_token)
                    with _active_guard:
                        resident_full = len(_active_runs) >= settings.SERVER_RUN_MAX_RESIDENT
                    if resident_full or not _reserve_capacity(owner_id):
                        continue
                    reserved = True
                    run = await asyncio.to_thread(
                        run_transport.claim_run, owner_id, device_token, lease_seconds=30,
                    )
                    if run is None:
                        _release_capacity(owner_id)
                        reserved = False
                        continue
                    run_id = str(run.get("id") or "")
                    if not run_id:
                        _release_capacity(owner_id)
                        reserved = False
                        continue
                    task = asyncio.create_task(
                        _execute_claimed(owner_id, user_token, device_token, run),
                        name=f"server-run:{run_id}",
                    )
                    active = _ActiveRun(
                        task=task, run_id=run_id, owner_id=owner_id,
                        device_id=run_transport.device_id(owner_id),
                        project_id=str(run.get("project_id") or ""),
                        workspace=str(run.get("workspace") or "default"),
                    )
                    with _active_guard:
                        _active_runs[run_id] = active
                    reserved = False
                    claimed = True
                except asyncio.CancelledError:
                    if reserved:
                        _release_capacity(owner_id)
                    raise
                except Exception:  # noqa: BLE001 - isolate one identity/network failure
                    if reserved:
                        _release_capacity(owner_id)
                    log.exception("Local Agent worker poll failed for owner %s", owner_id)
            with _active_guard:
                has_active = bool(_active_runs)
            _publish_snapshot()
            await asyncio.sleep(0.25 if claimed else 0.5 if has_active else 2)
    finally:
        with _active_guard:
            remaining = list(_active_runs.values())
        for item in remaining:
            item.task.cancel()
        if remaining:
            await asyncio.gather(*(item.task for item in remaining), return_exceptions=True)
        with _active_guard:
            _active_runs.clear()
            _capacity_by_owner.clear()
            global _capacity_used
            _capacity_used = 0
        if _is_leader:
            await asyncio.to_thread(local_agent_store.release_run_worker_leader, _worker_id)
        _is_leader = False
