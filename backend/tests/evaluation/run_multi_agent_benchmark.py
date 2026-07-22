"""Real-LLM single-vs-multi benchmark for the WB-258 admission gate.

This is intentionally not part of the offline regression suite: it consumes the configured
provider and records model output, token cost and elapsed time into an explicit JSON report.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent import orchestrator, runtime, telemetry
from config import settings
from storage import db, orchestration_store as store
from storage.models import LOCAL_USER_ID


SCENARIOS = [
    {
        "id": "incident_synthesis",
        "team": "深度研究团队",
        "goal": """请基于以下冻结事实写一份可执行的支付事故复盘，不能补造数据：
1. 08:55 将 payment_v2 从 10% 放量到 100%；2. 09:05 checkout 错误率从 2.1% 升到 18.4%；
3. 只有 Android 5.8.0 明显异常，iOS 和 Web 稳定；4. EU 区 PSP timeout 最集中；
5. 09:22 回滚 payment_v2，09:31 错误率恢复；6. 自动重试造成 43 笔重复预授权，但没有资金损失；
7. 客服收到 27 个工单；8. 现有告警只看全局错误率，未按客户端版本/地区切分。
输出时间线、证据支持的根因、影响、不确定性、短期止血、长期行动项（负责人类型与验收指标）。""",
        "criteria": [
            ["payment_v2"], ["08:55"], ["09:05"], ["18.4"], ["android", "5.8.0"],
            ["ios", "web"], ["eu", "psp"], ["09:22"], ["09:31"], ["43", "重复"],
            ["27", "工单"], ["没有资金损失|无资金损失"], ["幂等|去重"],
            ["版本", "地区", "告警"], ["不确定"], ["验收", "指标"],
        ],
    },
    {
        "id": "product_strategy",
        "team": "产品战略团队",
        "goal": """为团队自动化审批功能给出一页发布决策，事实如下：
用户访谈 18 人，其中 11 人要求高风险外部写先审批，7 人分不清“草稿”和“已执行”；
现有自动化激活率 42%，第 4 周留存 19%，失败后人工接管率 31%；
Viewer 必须只读，审计日志不得含 prompt/secret；法务要求审计导出保留 180 天；
竞品 A 默认全自动但事故投诉高，竞品 B 全部逐步确认导致完成率低；
本季度只能投入 2 名前端、2 名后端、1 名设计，六周内试点，首批 3 家设计伙伴。
请输出目标用户/JTBD、范围与非目标、关键流程、分级审批策略、指标、实验、风险和六周排期，明确事实与假设。""",
        "criteria": [
            ["18"], ["11", "审批"], ["7", "草稿"], ["42"], ["19"], ["31"],
            ["viewer", "只读"], ["prompt", "secret"], ["180"], ["竞品 a", "竞品 b"],
            ["2名前端", "2名后端"], ["六周|6周"], ["3家"],
            ["分级", "风险"], ["非目标"], ["假设"], ["实验"], ["指标"],
        ],
    },
]


def score(text: str, criteria: list[list[str]]) -> dict[str, Any]:
    normalized = "".join(text.lower().split())
    def present(term: str) -> bool:
        return any("".join(option.lower().split()) in normalized for option in term.split("|"))
    hits = [all(present(term) for term in group) for group in criteria]
    return {"hits": sum(hits), "total": len(hits), "ratio": round(sum(hits) / len(hits), 4), "detail": hits}


async def single_agent(user, scenario: dict[str, Any], budget: int) -> dict[str, Any]:
    started = time.perf_counter()
    total_prompt = 0
    total_completion = 0
    run = None
    text = ""
    error = ""
    for attempt in range(1, 4):
        session = db.create_session(owner_id=user.id, title=f"baseline · {scenario['id']} · {attempt}")
        output: list[str] = []
        error = ""
        async for chunk in runtime.run_chat(
            session, user, scenario["goal"], ask=True,
            system_extra="你是单 Agent 对照组。独立完成完整交付，明确事实、假设、风险和可验证行动。",
            idempotency_key=f"benchmark:single:{scenario['id']}:{attempt}", max_total_tokens=budget,
        ):
            event, data = orchestrator._sse(chunk)
            if event == "text":
                output.append(str(data.get("md") or ""))
            elif event == "error":
                error = str(data.get("message") or "")
        run = db.list_runs(user.id, session_id=session.id, limit=1)[0]
        total_prompt += run.prompt_tokens
        total_completion += run.completion_tokens
        text = "".join(output)
        error = error or run.error_message or ""
        if run.status == "completed" or not orchestrator._is_transient(error) or attempt == 3:
            break
        await asyncio.sleep(orchestrator._retry_delay(error, attempt - 1))
    assert run is not None
    return {
        "status": run.status, "error": error or run.error_message or "", "output": text,
        "prompt_tokens": total_prompt, "completion_tokens": total_completion,
        "seconds": round(time.perf_counter() - started, 3), "score": score(text, scenario["criteria"]),
    }


async def multi_agent(user, scenario: dict[str, Any], budget: int) -> dict[str, Any]:
    team = orchestrator.resolve_team(scenario["team"])
    item, _ = store.create(
        owner_id=user.id, project_id=None, team_name=scenario["team"], goal=scenario["goal"],
        idempotency_key=f"benchmark:multi:v2:{scenario['id']}", max_nodes=5, max_parallel=3,
        max_total_tokens=budget,
    )
    started = time.perf_counter()
    await orchestrator.run_orchestration(item["id"], user, team)
    result = store.get(item["id"], user.id)
    reviewer = next((node for node in result["nodes"] if node["node_key"] == "reviewer"), None)
    text = reviewer["output"] if reviewer else ""
    intervals = sorted(
        (float(node["started_at"]), float(node["ended_at"]))
        for node in result["nodes"]
        if node["node_key"] != "reviewer" and node.get("started_at") and node.get("ended_at")
    )
    peak_parallel = 0
    active = 0
    for _, delta in sorted(
        [(started, 1) for started, _ in intervals] + [(ended, -1) for _, ended in intervals],
        key=lambda event: (event[0], event[1]),
    ):
        active += delta
        peak_parallel = max(peak_parallel, active)
    return {
        "status": result["status"], "error": result["error"], "output": text,
        "prompt_tokens": result["prompt_tokens"], "completion_tokens": result["completion_tokens"],
        "seconds": round(time.perf_counter() - started, 3), "score": score(text, scenario["criteria"]),
        "peak_parallel": peak_parallel,
        "nodes": [
            {
                **{key: node.get(key) for key in ("node_key", "role", "status", "run_id", "prompt_tokens", "completion_tokens", "error")},
                "attempts": [
                    {key: attempt.get(key) for key in ("attempt", "status", "run_id", "prompt_tokens", "completion_tokens", "error")}
                    for attempt in node.get("attempts", [])
                ],
            }
            for node in result["nodes"]
        ],
        "artifact_id": result.get("artifact_id"),
    }


async def main(
    output: Path, budget: int, *, resume: bool = False,
    rerun_scenarios: set[str] | None = None,
) -> int:
    original_db = settings.DB_PATH
    original_workspace = settings.WORKSPACE_ROOT
    original_langfuse_enabled = settings.LANGFUSE_ENABLED
    source_user = db.get_user(LOCAL_USER_ID)
    default_ref = db.get_default_model(source_user.id)
    if not default_ref:
        raise RuntimeError("当前用户未设置默认模型，无法运行真实准入评测")
    provider_seed: dict[str, Any] | None = None
    custom_seed: dict[str, Any] | None = None
    if default_ref.startswith("@") and ":" in default_ref:
        provider_id = default_ref[1:].partition(":")[0]
        provider_seed = {
            "id": provider_id,
            "key": db.get_provider_key(source_user.id, provider_id),
            "config": db.get_provider_config(source_user.id, provider_id),
        }
    else:
        custom_seed = db.get_custom_model_by_name(source_user.id, default_ref, include_secrets=True)

    with tempfile.TemporaryDirectory() as temp:
        try:
            settings.DB_PATH = Path(temp) / "agentmate.db"
            settings.WORKSPACE_ROOT = Path(temp) / "workspace"
            # A model-quality benchmark must not wait on an optional local trace sink.
            settings.LANGFUSE_ENABLED = False
            telemetry._client = None
            telemetry._client_initialized = False
            db._local = threading.local()
            db.init_db(); store.ensure_tables()
            user = db.get_user(LOCAL_USER_ID)
            if provider_seed:
                if not provider_seed["key"]:
                    raise RuntimeError("默认模型对应的厂商密钥不可用")
                db.set_provider_key(user.id, provider_seed["id"], provider_seed["key"])
                config = provider_seed["config"] or {}
                db.set_provider_config(user.id, provider_seed["id"], config.get("base_url"), config.get("chat_path"))
            elif custom_seed:
                db.create_custom_model(
                    user.id, name=custom_seed["name"], model_id=custom_seed["model_id"],
                    api_base=custom_seed.get("api_base"), api_key=custom_seed.get("api_key"),
                    icon=custom_seed.get("icon") or "🧩", color=custom_seed.get("color") or "",
                    mult=custom_seed.get("mult") or "",
                )
            else:
                raise RuntimeError("默认自定义模型已不存在")
            db.set_default_model(user.id, default_ref)

            prior_by_scenario: dict[str, dict[str, Any]] = {}
            if resume and output.exists():
                prior_report = json.loads(output.read_text(encoding="utf-8"))
                if (
                    prior_report.get("gate") != "multi-agent-admission-v2"
                    or prior_report.get("provider_model") != default_ref
                ):
                    raise RuntimeError("续跑报告的门禁或模型与当前评测不一致")
                prior_by_scenario = {
                    str(item.get("scenario")): item
                    for item in prior_report.get("results", []) if isinstance(item, dict)
                }

            results = []
            for scenario in SCENARIOS:
                force_rerun = scenario["id"] in (rerun_scenarios or set())
                prior = prior_by_scenario.get(scenario["id"], {})
                prior_baseline = prior.get("baseline", {})
                prior_multi = prior.get("multi", {})
                baseline = (
                    prior_baseline if prior_baseline.get("status") == "completed"
                    else await single_agent(user, scenario, budget)
                )
                multi = (
                    prior_multi if not force_rerun and prior.get("passed") and prior_multi.get("status") == "completed"
                    else await multi_agent(user, scenario, budget * 5)
                )
                base_ratio = baseline["score"]["ratio"]
                multi_ratio = multi["score"]["ratio"]
                quality_gain = round(multi_ratio - base_ratio, 4)
                token_ratio = round(
                    (multi["prompt_tokens"] + multi["completion_tokens"])
                    / max(1, baseline["prompt_tokens"] + baseline["completion_tokens"]), 3,
                )
                ceiling = base_ratio >= 0.90
                quality_passed = (
                    multi_ratio >= 0.98 and multi_ratio >= base_ratio
                    if ceiling else
                    quality_gain >= 0.10 and multi["score"]["hits"] >= baseline["score"]["hits"] + 2
                )
                passed = (
                    baseline["status"] == "completed" and multi["status"] == "completed"
                    and quality_passed
                    and multi.get("peak_parallel", 0) >= 3
                    and token_ratio <= 5.0
                )
                results.append({
                    "scenario": scenario["id"], "baseline": baseline, "multi": multi,
                    "quality_gain": quality_gain, "token_ratio": token_ratio, "ceiling_rule": ceiling,
                    "quality_passed": quality_passed, "passed": passed,
                })
            report = {
                "gate": "multi-agent-admission-v2", "provider_model": default_ref,
                "threshold": {
                    "standard": {"quality_gain": 0.10, "minimum_extra_hits": 2},
                    "ceiling_when_baseline_at_least": 0.90,
                    "ceiling_rule": {"minimum_multi_score": 0.98, "must_not_regress": True},
                    "maximum_token_ratio": 5.0,
                    "minimum_peak_parallel": 3,
                },
                "passed": all(item["passed"] for item in results), "results": results,
            }
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({
                "passed": report["passed"],
                "results": [{"scenario": item["scenario"], "quality_gain": item["quality_gain"],
                             "token_ratio": item["token_ratio"], "passed": item["passed"],
                             "baseline_status": item["baseline"]["status"], "multi_status": item["multi"]["status"]}
                            for item in results],
                "report": str(output),
            }, ensure_ascii=False))
            return 0 if report["passed"] else 2
        finally:
            conn = getattr(db._local, "conn", None)
            if conn is not None:
                conn.close()
            settings.DB_PATH = original_db
            settings.WORKSPACE_ROOT = original_workspace
            settings.LANGFUSE_ENABLED = original_langfuse_enabled
            db._local = threading.local()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--single-budget", type=int, default=5000)
    parser.add_argument("--resume", action="store_true", help="reuse completed arms from an existing report")
    parser.add_argument("--rerun-scenario", action="append", choices=[item["id"] for item in SCENARIOS], default=[])
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(
        args.output, args.single_budget, resume=args.resume,
        rerun_scenarios=set(args.rerun_scenario),
    )))
