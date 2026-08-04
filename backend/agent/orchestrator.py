"""Evidence-gated multi-agent DAG execution with independent real Runs (WB-258)."""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

from agent import background_worker, runtime
from config import settings
from storage import db, orchestration_store as store
from storage.models import User

_NODE_KEY_RE = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")
JOB_KIND = "orchestration"
_TASKS: dict[str, asyncio.Task[None]] = {}
_ACTIVE_SESSIONS: dict[str, set[str]] = {}


def _is_transient(error: str) -> bool:
    lowered = error.lower()
    return any(marker in lowered for marker in (
        " 429", "llm 429", " 500", "llm 500", " 502", "llm 502", " 503", "llm 503",
        " 504", "llm 504", "访问量过大", "网络错误", "timeout", "temporarily unavailable",
    ))


def _retry_delay(error: str, retry_index: int) -> float:
    lowered = error.lower()
    if "429" in lowered or "访问量过大" in error or "速率限制" in error:
        return (10.0, 30.0)[retry_index]
    return (2.0, 5.0)[retry_index]


def resolve_team(team_name: str) -> dict[str, Any] | None:
    teams = db.showcase_all().get("EXP_TEAMS", [])
    return next(
        (team for team in teams if isinstance(team, dict) and str(team.get("name")) == team_name), None,
    )


def validate_plan(raw: dict[str, Any], team: dict[str, Any], max_tasks: int) -> list[dict[str, Any]]:
    tasks = raw.get("tasks")
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= max_tasks:
        raise ValueError(f"planner must return 1..{max_tasks} tasks")
    members = {
        str(member.get("expert_slug")): str(member.get("role") or member.get("name") or "成员")
        for member in team.get("members", []) if isinstance(member, dict) and member.get("expert_slug")
    }
    normalized: list[dict[str, Any]] = []
    keys: set[str] = set()
    for item in tasks:
        if not isinstance(item, dict):
            raise ValueError("planner task must be an object")
        key = str(item.get("id") or "").strip()
        title = str(item.get("title") or "").strip()
        instruction = str(item.get("instruction") or "").strip()
        expert_slug = str(item.get("expert_slug") or "").strip()
        depends_on = item.get("depends_on", [])
        if not _NODE_KEY_RE.fullmatch(key) or key in keys:
            raise ValueError("planner task id is invalid or duplicated")
        if not title or not instruction or expert_slug not in members:
            raise ValueError("planner task title/instruction/expert is invalid")
        if not isinstance(depends_on, list) or any(not isinstance(dep, str) for dep in depends_on):
            raise ValueError("planner task dependencies must be strings")
        keys.add(key)
        normalized.append({
            "id": key, "title": title[:160], "instruction": instruction[:12000],
            "expert_slug": expert_slug, "role": members[expert_slug],
            "depends_on": list(dict.fromkeys(depends_on)),
        })
    for item in normalized:
        if item["id"] in item["depends_on"] or any(dep not in keys for dep in item["depends_on"]):
            raise ValueError("planner returned an unknown or self dependency")
    # Kahn validation rejects all cycles before any specialist Run starts.
    remaining = {item["id"]: set(item["depends_on"]) for item in normalized}
    resolved: set[str] = set()
    while remaining:
        ready = {key for key, deps in remaining.items() if deps <= resolved}
        if not ready:
            raise ValueError("planner returned a cyclic DAG")
        resolved.update(ready)
        for key in ready:
            remaining.pop(key)
    return normalized


def build_role_plan(team: dict[str, Any], max_tasks: int = 3) -> list[dict[str, Any]]:
    """Build a low-variance DAG from the authoritative team catalog.

    The goal is supplied at execution time; routing itself should not spend an LLM call or
    hallucinate member slugs. The lead is reserved for review, while the configured number of
    catalog members independently examine the goal from complementary roles.
    """
    members = [
        member for member in team.get("members", [])
        if isinstance(member, dict) and member.get("expert_slug") and not member.get("lead")
    ]
    selected = members[:max(1, min(max_tasks, len(members)))]
    if not selected:
        raise ValueError("expert team has no specialist members")
    return [
        {
            "id": f"specialist_{index}",
            "title": str(member.get("role") or member.get("name") or f"专家 {index}"),
            "instruction": (
                f"以{member.get('role') or '专家'}职责独立审视目标：逐项核对事实、约束和交付要求，"
                "指出证据、假设、风险与可验证建议。控制在 1200 字内，不重复原始目标。"
            ),
            "expert_slug": str(member["expert_slug"]),
            "role": str(member.get("role") or member.get("name") or "成员"),
            "depends_on": [],
        }
        for index, member in enumerate(selected, start=1)
    ]


def _sse(chunk: str) -> tuple[str, dict[str, Any]]:
    event = ""
    data: dict[str, Any] = {}
    for line in chunk.splitlines():
        if line.startswith("event: "):
            event = line[7:]
        elif line.startswith("data: "):
            try:
                parsed = json.loads(line[6:])
                data = parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                data = {}
    return event, data


def _build_handoff(
    *, run_id: str | None, status: str, output: str = "", error: str = "",
) -> dict[str, Any]:
    """Build a versioned handoff only from persisted Run/Artifact evidence."""
    run = db.get_run(run_id or "") if run_id else None
    artifacts = db.list_artifacts(run.id) if run else []
    artifact_items = [
        {
            "id": artifact.id,
            "path": artifact.path,
            "name": artifact.name,
            "kind": artifact.kind,
            "sha256": artifact.sha256,
            "size": artifact.size,
            "is_primary": artifact.is_primary,
            "display_order": artifact.display_order,
            "validation_status": artifact.validation_status,
            "validation": artifact.validation,
            "acceptance_status": artifact.acceptance_status,
        }
        for artifact in artifacts
    ]
    risks: list[str] = []
    if error:
        risks.append(error)
    for artifact in artifact_items:
        if artifact["validation_status"] != "passed":
            risks.append(f"产物 {artifact['path']} 校验状态为 {artifact['validation_status']}")
        if artifact["acceptance_status"] != "accepted":
            risks.append(f"产物 {artifact['path']} 尚未验收（{artifact['acceptance_status']}）")
    return {
        "schema_version": 1,
        "summary": output,
        "claims": [],
        "run": {
            "id": run.id if run else run_id,
            "status": run.status if run else status,
            "error_code": run.error_code if run else "",
            "prompt_tokens": run.prompt_tokens if run else 0,
            "completion_tokens": run.completion_tokens if run else 0,
            "tool_calls": run.tool_calls if run else 0,
        },
        "artifacts": artifact_items,
        "evidence": [
            {"type": "run", "id": run.id, "status": run.status}
            for _ in [0] if run
        ] + [
            {
                "type": "artifact", "id": item["id"], "path": item["path"],
                "sha256": item["sha256"], "validation_status": item["validation_status"],
            }
            for item in artifact_items
        ],
        "side_effects": [
            {"type": "artifact_write", "artifact_id": item["id"], "path": item["path"]}
            for item in artifact_items
        ],
        "open_questions": [],
        "risks": list(dict.fromkeys(risks)),
    }


async def _execute_node(
    orchestration: dict[str, Any], user: User, node: dict[str, Any], prompt: str,
    *, token_budget: int, max_attempts: int = 3,
) -> dict[str, Any]:
    workspace = f"projects/{orchestration['project_id']}" if orchestration.get("project_id") else "default"
    remaining_budget = max(256, token_budget)
    bounded_attempts = max(1, min(max_attempts, 3))
    for attempt_index in range(bounded_attempts):
        session = db.create_session(
            owner_id=user.id, title=f"{orchestration['team_name']} · {node['title']}",
            kind="projexec" if orchestration.get("project_id") else "chat",
            project_id=orchestration.get("project_id"),
        )
        attempt = store.start_attempt(orchestration["id"], node["node_key"], session.id)
        _ACTIVE_SESSIONS.setdefault(orchestration["id"], set()).add(session.id)
        output: list[str] = []
        event_error = ""
        cancelled = False
        try:
            async for chunk in runtime.run_chat(
                session, user, prompt, ask=True, experts=[node["expert_slug"]],
                system_extra=(
                    f"你是多 Agent 编排中的独立成员。角色：{node['role']}。"
                    "只完成分配给你的子任务；明确事实、假设、冲突与建议，不假装看过未提供的资料。"
                ),
                workspace=workspace,
                idempotency_key=(
                    f"orchestration:{orchestration['id']}:{node['node_key']}:{attempt['attempt']}"
                ),
                max_total_tokens=remaining_budget,
                # Specialists provide bounded evidence briefs; the reviewer keeps more
                # room for the user-facing synthesis. This avoids paying four full-size
                # answers while keeping three-way orchestration below the 5x gate.
                max_output_tokens=max(64, min(
                    2800 if node["node_key"] == "reviewer" else 2200,
                    remaining_budget // 2,
                )),
            ):
                event, data = _sse(chunk)
                if event == "text":
                    output.append(str(data.get("md") or ""))
                elif event == "error":
                    event_error = str(data.get("message") or "execution failed")
        except asyncio.CancelledError:
            cancelled = True
            current = store.get(orchestration["id"], user.id) or {}
            event_error = "cancelled_by_user" if current.get("cancel_requested") else "worker_stopped"
        except Exception as exc:  # noqa: BLE001
            event_error = str(exc)
        finally:
            _ACTIVE_SESSIONS.get(orchestration["id"], set()).discard(session.id)
        runs = db.list_runs(user.id, session_id=session.id, limit=5)
        run = runs[0] if runs else None
        text = "".join(output).strip()
        status = "completed" if run and run.status == "completed" and not event_error and text else "failed"
        if cancelled:
            current = store.get(orchestration["id"], user.id) or {}
            status = "cancelled" if current.get("cancel_requested") else "failed"
        error = event_error or (run.error_message if run else "run was not created") or ""
        if status == "failed" and run and run.status == "completed" and not text and not error:
            error = "agent completed without deliverable output"
        attempt_tokens = (run.prompt_tokens + run.completion_tokens) if run else 0
        remaining_budget = max(0, remaining_budget - attempt_tokens)
        retryable = status == "failed" and attempt_index + 1 < bounded_attempts and _is_transient(error)
        if retryable and remaining_budget < 256:
            error = f"{error}; node token budget exhausted".strip("; ")
        store.finish_attempt(
            attempt["id"], status=status, run_id=run.id if run else None, error=error,
            prompt_tokens=run.prompt_tokens if run else 0,
            completion_tokens=run.completion_tokens if run else 0,
        )
        if cancelled:
            current = store.get(orchestration["id"], user.id) or {}
            if current.get("cancel_requested"):
                store.finish_node(
                    orchestration["id"], node["node_key"], status="cancelled",
                    run_id=run.id if run else None, error=error,
                )
            else:
                store.reset_node(orchestration["id"], node["node_key"])
            raise asyncio.CancelledError
        if retryable and remaining_budget >= 256:
            await asyncio.sleep(_retry_delay(error, attempt_index))
            continue
        store.finish_node(
            orchestration["id"], node["node_key"], status=status, run_id=run.id if run else None,
            output=text, error=error,
            handoff=_build_handoff(
                run_id=run.id if run else None, status=status, output=text, error=error,
            ),
        )
        return store.get_node(orchestration["id"], node["node_key"]) or {}
    return store.get_node(orchestration["id"], node["node_key"]) or {}


def _planner_prompt(goal: str, team: dict[str, Any], max_tasks: int) -> str:
    members = [
        {"role": member.get("role"), "expert_slug": member.get("expert_slug")}
        for member in team.get("members", []) if isinstance(member, dict)
    ]
    return (
        "把目标拆成有依赖关系的专家任务 DAG。只返回 JSON，不要 Markdown。\n"
        f"目标：{goal}\n可用成员：{json.dumps(members, ensure_ascii=False)}\n"
        f"最多 {max_tasks} 个 tasks；优先用最少且互补的任务覆盖目标。schema："
        '{"tasks":[{"id":"lowercase_key","title":"...","instruction":"...",'
        '"expert_slug":"必须来自可用成员","depends_on":["task_id"]}]}。'
        "任务应互补、可独立验证；无依赖任务允许并行，不要安排外部写操作。"
        "不要解释、不要思维过程，JSON 总长度不超过 6000 字符。"
    )


def _json_object(text: str) -> dict[str, Any]:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("planner did not return JSON")
    value = json.loads(text[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("planner JSON must be an object")
    return value


def _dependency_context(node: dict[str, Any], nodes: list[dict[str, Any]]) -> str:
    by_key = {item["node_key"]: item for item in nodes}
    blocks: list[str] = []
    remaining = 24000
    for dep in node["depends_on"]:
        source = by_key[dep]
        handoff = source.get("handoff") if isinstance(source.get("handoff"), dict) else {}
        run = handoff.get("run") if isinstance(handoff.get("run"), dict) else {}
        artifacts = handoff.get("artifacts") if isinstance(handoff.get("artifacts"), list) else []
        evidence_lines = [
            f"Run：{run.get('id') or source.get('run_id') or '-'} · {run.get('status') or source['status']}"
        ]
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            evidence_lines.append(
                f"产物：{'主产物 · ' if artifact.get('is_primary') else ''}{artifact.get('path') or '-'}"
                f" · sha256 {artifact.get('sha256') or '-'} · 校验 {artifact.get('validation_status') or '-'}"
                f" · 验收 {artifact.get('acceptance_status') or '-'}"
            )
        risks = handoff.get("risks") if isinstance(handoff.get("risks"), list) else []
        if risks:
            evidence_lines.append("风险：" + "；".join(str(item) for item in risks))
        body = str(handoff.get("summary") or source.get("output") or "")[:remaining]
        remaining -= len(body)
        blocks.append(
            f"【上游 {dep} · {source['role']} · 结构化交接 v{handoff.get('schema_version') or 0}】\n"
            + "\n".join(evidence_lines)
            + f"\n摘要：\n{body}"
        )
        if remaining <= 0:
            break
    return "\n\n".join(blocks)


def _review_prompt(orchestration: dict[str, Any], nodes: list[dict[str, Any]]) -> str:
    blocks = []
    remaining = 48000
    for node in nodes:
        if node["node_key"] in {"planner", "reviewer"}:
            continue
        handoff = node.get("handoff") if isinstance(node.get("handoff"), dict) else {}
        evidence = json.dumps({
            "schema_version": handoff.get("schema_version", 0),
            "run": handoff.get("run") or {"id": node.get("run_id"), "status": node["status"]},
            "artifacts": handoff.get("artifacts") or [],
            "risks": handoff.get("risks") or ([node.get("error")] if node.get("error") else []),
            "open_questions": handoff.get("open_questions") or [],
        }, ensure_ascii=False, sort_keys=True)
        body = str(handoff.get("summary") or node.get("output") or node.get("error") or "")[:remaining]
        remaining -= len(body)
        blocks.append(
            f"【{node['node_key']} · {node['role']} · {node['status']} · 结构化证据】\n"
            f"{evidence}\n摘要：\n{body}"
        )
        if remaining <= 0:
            break
    return (
        f"你是专家团主编。原始目标：{orchestration['goal']}\n\n"
        "下面是独立成员的真实执行结果。识别冲突和缺口，保留可验证事实，明确不确定性，"
        "逐项核对原始目标中的数字、限制与交付要求，确保没有遗漏，再给出结构化最终交付；"
        "涉及重复副作用时必须给出幂等或去重控制；失败成员不能被描述为成功。\n\n"
        + "\n\n".join(blocks)
    )


def _artifact(orchestration: dict[str, Any], reviewer: dict[str, Any], nodes: list[dict[str, Any]]) -> str:
    run = db.get_run(reviewer.get("run_id") or "")
    if not run:
        raise RuntimeError("reviewer run missing")
    root = settings.WORKSPACE_ROOT.resolve()
    workspace = (root / run.workspace).resolve()
    if workspace != root and root not in workspace.parents:
        raise RuntimeError("orchestration workspace escaped root")
    workspace.mkdir(parents=True, exist_ok=True)
    relative = f"orchestration-{orchestration['id']}.md"
    target = (workspace / relative).resolve()
    if target.parent != workspace:
        raise RuntimeError("invalid orchestration artifact path")
    trace_lines = []
    for node in nodes:
        attempts = ", ".join(
            f"#{attempt['attempt']} `{attempt.get('run_id') or '-'}` {attempt['status']}"
            for attempt in node.get("attempts", [])
        ) or "无 Run"
        trace_lines.append(
            f"- `{node['node_key']}` {node['role']} · {node['status']} · {attempts} · "
            f"{node['prompt_tokens'] + node['completion_tokens']} tokens"
        )
    trace = "\n".join(trace_lines)
    content = (
        f"# {orchestration['team_name']}交付\n\n{reviewer['output'].strip()}\n\n"
        f"## 执行追溯\n\n{trace}\n"
    )
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(content, encoding="utf-8")
    temp.replace(target)
    artifact = db.upsert_artifact(
        run_id=run.id, path=relative, full_path=target, source_tool="multi_agent_orchestrator",
        validation={"nodes": len(nodes), "trace_complete": all(node.get("run_id") or node["status"] == "skipped" for node in nodes)},
    )
    return artifact.id


async def run_orchestration(orchestration_id: str, user: User, team: dict[str, Any]) -> None:
    orchestration = store.get(orchestration_id, user.id)
    if not orchestration:
        return
    try:
        members = [m for m in team.get("members", []) if isinstance(m, dict) and m.get("expert_slug")]
        lead = next((m for m in members if m.get("lead")), members[0] if members else None)
        if not lead:
            raise ValueError("expert team has no executable members")
        if orchestration["status"] == "planning":
            specialist_limit = min(
                orchestration["max_parallel"], max(1, orchestration["max_nodes"] - 1),
            )
            plan = build_role_plan(team, specialist_limit)
            existing = {node["node_key"] for node in store.list_nodes(orchestration_id)}
            for item in plan:
                if item["id"] not in existing:
                    store.add_node(
                        orchestration_id, node_key=item["id"], title=item["title"], role=item["role"],
                        expert_slug=item["expert_slug"], instruction=item["instruction"],
                        depends_on=item["depends_on"],
                    )
            store.set_status(orchestration_id, "running")
        while (store.get(orchestration_id, user.id) or {}).get("status") == "running":
            current = store.get(orchestration_id, user.id) or {}
            if current.get("cancel_requested"):
                store.set_status(orchestration_id, "cancelled", error="cancelled_by_user")
                return
            nodes = store.list_nodes(orchestration_id)
            pending = [node for node in nodes if node["status"] == "pending"]
            if not pending:
                break
            by_key = {node["node_key"]: node for node in nodes}
            for node in pending:
                dependencies = [by_key[key] for key in node["depends_on"]]
                if any(dep["status"] in {"failed", "skipped", "cancelled"} for dep in dependencies):
                    store.finish_node(
                        orchestration_id, node["node_key"], status="skipped", run_id=None,
                        error="dependency_failed",
                    )
            nodes = store.list_nodes(orchestration_id)
            pending = [node for node in nodes if node["status"] == "pending"]
            by_key = {node["node_key"]: node for node in nodes}
            ready = [
                node for node in pending
                if all(by_key.get(dep, {}).get("status") == "completed" for dep in node["depends_on"])
            ]
            if not ready:
                if pending:
                    raise RuntimeError("DAG made no progress")
                break
            total = current.get("prompt_tokens", 0) + current.get("completion_tokens", 0)
            remaining = orchestration["max_total_tokens"] - total
            if remaining < 256:
                raise RuntimeError("orchestration token budget exhausted")
            batch = ready[:orchestration["max_parallel"]]
            per_node = max(256, remaining // (len(batch) + 1))
            batch_results = await asyncio.gather(*(
                _execute_node(
                    orchestration, user, node,
                    f"原始目标：{orchestration['goal']}\n\n你的子任务：{node['instruction']}\n\n"
                    + _dependency_context(node, nodes),
                    token_budget=per_node, max_attempts=1,
                )
                for node in batch
            ))
            # A provider may reject simultaneous requests even though the DAG supports
            # parallelism. Once the successful sibling has released its slot, recover a
            # transiently failed node sequentially and preserve every earlier attempt.
            for failed in batch_results:
                if failed.get("status") == "failed" and _is_transient(str(failed.get("error") or "")):
                    latest = store.get(orchestration_id, user.id) or {}
                    recovery_remaining = (
                        orchestration["max_total_tokens"]
                        - latest.get("prompt_tokens", 0) - latest.get("completion_tokens", 0)
                    )
                    # Keep half of the remaining global budget for the mandatory reviewer.
                    recovery_budget = recovery_remaining // 2
                    if recovery_budget < 256:
                        continue
                    store.reset_node(orchestration_id, failed["node_key"])
                    await _execute_node(
                        orchestration, user, failed,
                        f"原始目标：{orchestration['goal']}\n\n你的子任务：{failed['instruction']}\n\n"
                        + _dependency_context(failed, store.list_nodes(orchestration_id)),
                        token_budget=recovery_budget,
                    )
        current_status = (store.get(orchestration_id, user.id) or {}).get("status")
        if current_status == "running":
            store.set_status(orchestration_id, "reviewing")
        current = store.get(orchestration_id, user.id) or {}
        if current.get("cancel_requested"):
            store.set_status(orchestration_id, "cancelled", error="cancelled_by_user")
            return
        nodes = store.list_nodes(orchestration_id)
        reviewer = store.get_node(orchestration_id, "reviewer")
        if reviewer is None:
            reviewer = store.add_node(
                orchestration_id, node_key="reviewer", title="主编审稿", role=str(lead.get("role") or "主编"),
                expert_slug=str(lead["expert_slug"]), instruction="冲突审查与最终综合",
                depends_on=[node["node_key"] for node in nodes if node["node_key"] != "planner"],
            )
        current = store.get(orchestration_id, user.id) or {}
        remaining = orchestration["max_total_tokens"] - current.get("prompt_tokens", 0) - current.get("completion_tokens", 0)
        if remaining < 256:
            raise RuntimeError("orchestration token budget exhausted before review")
        if reviewer["status"] == "pending":
            reviewer = await _execute_node(
                orchestration, user, reviewer, _review_prompt(orchestration, nodes), token_budget=remaining,
            )
        if reviewer["status"] == "failed" and _is_transient(str(reviewer.get("error") or "")):
            # The reviewer is the only node without a later sibling that can trigger
            # the sequential provider-recovery path. Give it one fresh round while
            # retaining all failed attempts and their cost in the audit trail.
            latest = store.get(orchestration_id, user.id) or {}
            retry_budget = (
                orchestration["max_total_tokens"]
                - latest.get("prompt_tokens", 0) - latest.get("completion_tokens", 0)
            )
            if retry_budget >= 256:
                store.reset_node(orchestration_id, "reviewer")
                reviewer = await _execute_node(
                    orchestration, user, reviewer, _review_prompt(orchestration, nodes),
                    token_budget=retry_budget,
                )
        if reviewer["status"] != "completed" or not reviewer["output"]:
            raise RuntimeError(f"reviewer failed: {reviewer['error']}")
        final_output = (
            reviewer["output"].rstrip()
            + "\n\n## 输入事实与约束快照\n\n"
            + orchestration["goal"].strip()
        )
        store.finish_node(
            orchestration_id, "reviewer", status="completed", run_id=reviewer.get("run_id"),
            output=final_output,
            handoff=_build_handoff(
                run_id=reviewer.get("run_id"), status="completed", output=final_output,
            ),
        )
        reviewer = store.get_node(orchestration_id, "reviewer") or reviewer
        final_nodes = store.list_nodes(orchestration_id)
        artifact_id = _artifact(orchestration, reviewer, final_nodes)
        store.set_status(orchestration_id, "completed", artifact_id=artifact_id)
    except asyncio.CancelledError:
        current = store.get(orchestration_id, user.id) or {}
        if current.get("cancel_requested"):
            store.set_status(orchestration_id, "cancelled", error="cancelled_by_user")
        else:
            store.prepare_resume(orchestration_id, "worker_stopped")
        raise
    except Exception as exc:  # noqa: BLE001
        store.set_status(orchestration_id, "failed", error=str(exc))
    finally:
        _ACTIVE_SESSIONS.pop(orchestration_id, None)
        _TASKS.pop(orchestration_id, None)


async def _execute_job(job: dict[str, Any]) -> None:
    orchestration_id = str(job["entity_id"])
    item = store.get(orchestration_id, str(job["owner_id"]))
    user = db.get_user(str(job["owner_id"]))
    if not item or not user:
        raise background_worker.TerminalJobError("编排或运行账户不存在", code="scope_missing")
    team = resolve_team(item["team_name"])
    if not team:
        raise background_worker.TerminalJobError("专家团队不存在", code="team_missing")
    if int(job["attempt"]) > 1:
        store.prepare_resume(orchestration_id)
    await run_orchestration(orchestration_id, user, team)
    current = store.get(orchestration_id, user.id) or {}
    if current.get("status") == "completed":
        return
    if current.get("status") == "failed":
        raise background_worker.TerminalJobError(
            str(current.get("error") or "编排失败"), code="orchestration_failed",
        )
    if current.get("status") == "cancelled":
        raise background_worker.TerminalJobError("编排已取消", code="cancelled_by_user")
    raise RuntimeError("编排未进入终态")


async def _recover(_job: dict[str, Any]) -> None:
    store.ensure_tables()
    for item in store.list_active():
        background_worker.enqueue(
            owner_id=item["owner_id"], kind=JOB_KIND, entity_id=item["id"],
            idempotency_key=f"orchestration:{item['id']}", payload={}, max_attempts=3,
        )


def _fail_job(job: dict[str, Any]) -> None:
    store.fail_nonterminal(
        str(job.get("entity_id") or ""),
        str(job.get("error_message") or job.get("error_code") or "background_job_failed"),
    )


background_worker.register_handler(JOB_KIND, _execute_job, recover=_recover, failed=_fail_job)


def start(orchestration_id: str, user: User, team: dict[str, Any]) -> None:
    _ = team  # the durable handler resolves the authoritative catalog again at execution time
    _, _, task = background_worker.enqueue(
        owner_id=user.id, kind=JOB_KIND, entity_id=orchestration_id,
        idempotency_key=f"orchestration:{orchestration_id}", payload={}, max_attempts=3,
    )
    if task:
        _TASKS[orchestration_id] = task
        task.add_done_callback(lambda _done: _TASKS.pop(orchestration_id, None))


def cancel(orchestration_id: str) -> asyncio.Task[None] | None:
    store.request_cancel(orchestration_id)
    for session_id in list(_ACTIVE_SESSIONS.get(orchestration_id, set())):
        runtime.request_stop(session_id)
    item = store.get(orchestration_id)
    task = background_worker.cancel_entity(item["owner_id"], JOB_KIND, orchestration_id) if item else None
    if task is None:
        task = _TASKS.get(orchestration_id)
        if task and not task.done():
            task.cancel()
    return task


async def cancel_and_wait(orchestration_id: str, timeout: float = 5.0) -> dict[str, Any] | None:
    """Cancel active child Runs and return only after durable state has converged."""
    task = _TASKS.get(orchestration_id)
    task = cancel(orchestration_id) or task
    if task and not task.done():
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=max(0.1, timeout))
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
    store.cancel_nonterminal(orchestration_id)
    return store.get(orchestration_id)
