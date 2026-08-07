"""Execute Server-owned Runs through the Local Agent lease/WAL protocol."""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

import local_agent_store
import run_transport
import server_client
from agent import runtime
from config import settings
from storage import db
from storage.models import Message, Project, User


log = logging.getLogger("agentmate.server-runs")


@dataclass
class _ControlState:
    stopped: bool = False
    terminal: bool = False


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


async def _flush(owner_id: str, device_token: str) -> None:
    await asyncio.to_thread(run_transport.flush_wal, owner_id, device_token)


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
            elif command_type == "ask_user_answer":
                answers = payload.get("answers") if isinstance(payload.get("answers"), list) else []
                runtime.submit_answers(local_session_id, [str(item) for item in answers])
                run_transport.append_event(run_id, "run.started", {"resumed_from": "waiting_user"})
            else:
                continue
            run_transport.append_event(run_id, "command.ack", {"command_id": command_id})
            acknowledged.add(command_id)
        await _flush(owner_id, device_token)


async def execute_run(owner_id: str, user_token: str, device_token: str, run: dict[str, Any]) -> None:
    run_id = str(run.get("id") or "")
    session_id = str(run.get("session_id") or "")
    if not run_id or not session_id:
        raise ValueError("leased Run is missing execution identity")

    account, session_record, messages = await asyncio.gather(
        asyncio.to_thread(server_client.verify_token, user_token),
        asyncio.to_thread(server_client.get_business_session, user_token, session_id),
        asyncio.to_thread(server_client.get_business_messages, user_token, session_id),
    )
    if not account or not session_record or messages is None:
        raise RuntimeError("Server execution context is unavailable")
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
    state = _ControlState()
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
    await _flush(owner_id, device_token)
    try:
        async with asyncio.timeout(timeout_seconds if timeout_seconds > 0 else None):
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
                idempotency_key=f"server-run:{run_id}",
                max_total_tokens=max(0, int(permission.get("max_total_tokens") or 0)),
                execution_source=execution_source,
                preauthorized_permissions=[
                    str(item) for item in permission.get("preauthorized_permissions") or []
                ],
                history_override=history, project_override=project_override,
            ):
                for event_type, payload in _frames(chunk):
                    if event_type == "run":
                        continue
                    if event_type == "ask_user":
                        run_transport.append_event(
                            run_id, "run.waiting_user",
                            {"questions": payload.get("questions") if isinstance(payload.get("questions"), list) else []},
                        )
                    elif event_type == "done":
                        continue
                    else:
                        run_transport.append_event(run_id, f"ui.{event_type}", payload)
                        if event_type == "error":
                            stream_error = str(payload.get("message") or "")
                    await _flush(owner_id, device_token)
        terminal_type = "run.cancelled" if state.stopped else "run.failed" if stream_error else "run.completed"
        terminal_payload = (
            {"error_code": "local_execution_failed", "error_message": stream_error}
            if stream_error else {}
        )
        run_transport.append_event(run_id, terminal_type, terminal_payload)
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


async def run_forever() -> None:
    """Claim and execute Server Runs; one local execution at a time per process."""
    if not settings.server_enabled:
        return
    db.init_db()
    while True:
        claimed = False
        for owner_id, user_token in local_agent_store.list_server_identities():
            device_token = await asyncio.to_thread(run_transport.ensure_device, owner_id, user_token)
            if not device_token:
                continue
            await asyncio.to_thread(run_transport.heartbeat, owner_id, device_token)
            await _flush(owner_id, device_token)
            run = await asyncio.to_thread(run_transport.claim_run, owner_id, device_token, lease_seconds=30)
            if run is None:
                continue
            claimed = True
            await execute_run(owner_id, user_token, device_token, run)
        await asyncio.sleep(0.25 if claimed else 2)
