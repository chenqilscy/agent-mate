"""Repeatable orchestration snapshot benchmark (WB-299).

Uses an isolated SQLite database and synthetic lifecycle rows; it never calls an LLM or
writes the user's workspace. The result guards the API/SSE read path against N+1 regressions.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import settings
from storage import db, orchestration_store as store
from storage.models import LOCAL_USER_ID


def main(iterations: int, nodes: int, attempts: int, output: Path | None) -> int:
    original_db = settings.DB_PATH
    original_workspace = settings.WORKSPACE_ROOT
    with tempfile.TemporaryDirectory() as temp:
        try:
            settings.DB_PATH = Path(temp) / "agentmate.db"
            settings.WORKSPACE_ROOT = Path(temp) / "workspace"
            db._local = threading.local()
            db.init_db()
            store.ensure_tables()
            item, _ = store.create(
                owner_id=LOCAL_USER_ID, project_id=None, team_name="benchmark", goal="benchmark",
                idempotency_key="snapshot-benchmark", max_nodes=max(3, nodes + 1), max_parallel=3,
                max_total_tokens=120000,
            )
            for node_index in range(nodes):
                node_key = f"node_{node_index}"
                store.add_node(
                    item["id"], node_key=node_key, title=node_key, role="benchmark",
                    expert_slug="benchmark", instruction="benchmark", depends_on=[],
                )
                for attempt_index in range(attempts):
                    session = db.create_session(
                        owner_id=LOCAL_USER_ID, title=f"{node_key}-{attempt_index}",
                    )
                    attempt = store.start_attempt(item["id"], node_key, session.id)
                    store.finish_attempt(
                        attempt["id"], status="failed", run_id=None, error="benchmark",
                    )
                store.finish_node(
                    item["id"], node_key, status="failed", run_id=None, error="benchmark",
                )

            statements: list[str] = []
            conn = db.get_conn()
            conn.set_trace_callback(statements.append)
            try:
                snapshot = store.get(item["id"], LOCAL_USER_ID)
            finally:
                conn.set_trace_callback(None)
            select_count = sum(sql.lstrip().upper().startswith("SELECT") for sql in statements)
            attempt_select_count = sum(
                sql.lstrip().upper().startswith("SELECT") and "orchestration_attempts" in sql
                for sql in statements
            )

            samples = []
            for _ in range(max(1, iterations)):
                started = time.perf_counter()
                store.get(item["id"], LOCAL_USER_ID)
                samples.append((time.perf_counter() - started) * 1000)
            ordered = sorted(samples)
            p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
            result = {
                "gate": "orchestration-snapshot-v1",
                "iterations": len(samples),
                "nodes": len(snapshot["nodes"] if snapshot else []),
                "attempts_per_node": attempts,
                "selects_per_snapshot": select_count,
                "attempt_selects_per_snapshot": attempt_select_count,
                "average_ms": round(statistics.fmean(samples), 4),
                "p95_ms": round(p95, 4),
                "passed": select_count <= 3 and attempt_select_count == 1 and p95 < 20,
            }
            payload = json.dumps(result, ensure_ascii=False, indent=2)
            if output:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(payload, encoding="utf-8")
            print(payload)
            return 0 if result["passed"] else 2
        finally:
            conn = getattr(db._local, "conn", None)
            if conn is not None:
                conn.close()
            settings.DB_PATH = original_db
            settings.WORKSPACE_ROOT = original_workspace
            db._local = threading.local()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--nodes", type=int, default=10)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    raise SystemExit(main(args.iterations, args.nodes, args.attempts, args.output))
