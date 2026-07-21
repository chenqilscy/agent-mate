"""Skill 不可变发布、客户端测试、审核、灰度与回滚契约（WB-250）。"""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

import db  # noqa: E402
from config import settings  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from routers.catalog import (  # noqa: E402
    CatalogPullBody, SkillMetricBody, SkillPublishBody, SkillReleaseBody,
    SkillReleaseTestBody, _skill_bucket, approve_release, create_release,
    pause_release, publish_release, pull_catalog, record_release_metric,
    record_release_test, rollback_release, withdraw_release,
)


class SkillReleaseLifecycleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = settings.DB_PATH
        settings.DB_PATH = Path(self.tmp.name) / "server.db"
        db._local = threading.local()
        db.init_db()
        conn = db.get_conn()
        conn.execute("DELETE FROM catalog_items WHERE category='APP_SKILLS'")
        conn.execute("DELETE FROM skill_release_audit")
        conn.execute("DELETE FROM skill_release_metrics")
        conn.execute("DELETE FROM skill_releases")
        conn.commit()
        self.author = SimpleNamespace(id="author", is_platform_admin=True)
        self.reviewer = SimpleNamespace(id="reviewer", is_platform_admin=True)
        self.runner = SimpleNamespace(id="client-runner", is_platform_admin=False)

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_path
        db._local = threading.local()
        self.tmp.cleanup()

    @staticmethod
    def data(name: str = "Web Access", instructions: str = "Fetch then answer.") -> dict:
        return {
            "slug": "web-access", "name": name, "description": "浏览网页",
            "instructions": instructions, "tools": ["web_fetch"], "files": [],
        }

    def draft(self, *, data: dict | None = None, base: str = "", item_id: str = "", min_app_version: str = "0.0.0") -> dict:
        return create_release(SkillReleaseBody(
            data=data or self.data(), base_release_id=base, catalog_item_id=item_id,
            min_app_version=min_app_version,
        ), self.author)["release"]

    def pass_test_and_approve(self, release_id: str) -> dict:
        tested = record_release_test(release_id, SkillReleaseTestBody(
            passed=True, client_run_id=f"run-{release_id}", app_version="1.0.0",
            supported_tools={"web_fetch": "1"}, trace_id="trace-safe",
        ), self.runner)["release"]
        self.assertEqual("passed", tested["test_status"])
        return approve_release(release_id, self.reviewer)["release"]

    def test_draft_and_failed_test_never_reach_downlink_or_publish(self) -> None:
        release = self.draft(min_app_version="2.0.0")
        payload = pull_catalog(
            CatalogPullBody(app_version="1.0.0", supported_tools={"web_fetch": "1"}),
            SimpleNamespace(id="account-a", is_platform_admin=False),
        )
        self.assertFalse(any(row["category"] == "APP_SKILLS" for row in payload["items"]))

        tested = record_release_test(release["id"], SkillReleaseTestBody(
            passed=True, client_run_id="incompatible-run", app_version="1.0.0",
            supported_tools={"web_fetch": "1"},
        ), self.runner)["release"]
        self.assertEqual("failed", tested["test_status"])
        self.assertIn("requires app 2.0.0+", tested["test_report"]["compatibility_error"])
        with self.assertRaisesRegex(HTTPException, "passing client test"):
            approve_release(release["id"], self.reviewer)
        with self.assertRaisesRegex(HTTPException, "approved release"):
            publish_release(release["id"], SkillPublishBody(), self.reviewer)

    def test_author_reviewer_separation_publish_audit_diff_and_metrics(self) -> None:
        release = self.draft()
        record_release_test(release["id"], SkillReleaseTestBody(
            passed=True, client_run_id="real-client-run", app_version="1.0.0",
            supported_tools={"web_fetch": "1"}, trace_id="trace-1", artifacts=["result.md"],
        ), self.runner)
        with self.assertRaisesRegex(HTTPException, "cannot approve"):
            approve_release(release["id"], self.author)
        approved = approve_release(release["id"], self.reviewer)["release"]
        self.assertEqual("approved", approved["state"])
        published = publish_release(release["id"], SkillPublishBody(), self.reviewer)["release"]
        self.assertEqual("published", published["state"])
        self.assertEqual("reviewer", published["reviewer_id"])
        self.assertIn("published", [entry["action"] for entry in published["audit"]])

        metrics = record_release_metric(
            release["id"], SkillMetricBody(event="run_succeeded"), self.runner,
        )["metrics"]
        self.assertEqual(1, metrics["runs"])
        payload = pull_catalog(
            CatalogPullBody(app_version="1.0.0", supported_tools={"web_fetch": "1"}),
            SimpleNamespace(id="account-a", is_platform_admin=False),
        )
        skill = next(row for row in payload["items"] if row["category"] == "APP_SKILLS")
        self.assertEqual(release["id"], skill["release_id"])
        self.assertEqual(release["content_hash"], skill["data"]["content_hash"])

    def test_stable_canary_pause_withdraw_and_rollback(self) -> None:
        first = self.draft()
        self.pass_test_and_approve(first["id"])
        first = publish_release(first["id"], SkillPublishBody(), self.reviewer)["release"]

        second = self.draft(
            data=self.data(name="Web Access v2", instructions="Use guarded fetch."),
            base=first["id"], item_id=first["catalog_item_id"],
        )
        self.pass_test_and_approve(second["id"])
        second = publish_release(
            second["id"], SkillPublishBody(rollout_percent=10, rollout_channel="stable"), self.reviewer,
        )["release"]
        self.assertEqual("rolling_out", second["state"])

        inside = next(f"account-{i}" for i in range(1000) if _skill_bucket(f"account-{i}", "web-access") < 10)
        outside = next(f"account-{i}" for i in range(1000) if _skill_bucket(f"account-{i}", "web-access") >= 10)
        report = CatalogPullBody(app_version="1.0.0", supported_tools={"web_fetch": "1"})
        inside_skill = next(row for row in pull_catalog(report, SimpleNamespace(id=inside, is_platform_admin=False))["items"] if row["category"] == "APP_SKILLS")
        outside_skill = next(row for row in pull_catalog(report, SimpleNamespace(id=outside, is_platform_admin=False))["items"] if row["category"] == "APP_SKILLS")
        self.assertEqual(second["id"], inside_skill["release_id"])
        self.assertEqual(first["id"], outside_skill["release_id"])
        self.assertEqual(inside_skill["release_id"], next(
            row for row in pull_catalog(report, SimpleNamespace(id=inside, is_platform_admin=False))["items"]
            if row["category"] == "APP_SKILLS"
        )["release_id"])

        paused = pause_release(second["id"], self.reviewer)["release"]
        self.assertEqual("approved", paused["state"])
        paused_skill = next(row for row in pull_catalog(report, SimpleNamespace(id=inside, is_platform_admin=False))["items"] if row["category"] == "APP_SKILLS")
        self.assertEqual(first["id"], paused_skill["release_id"])

        publish_release(second["id"], SkillPublishBody(rollout_percent=10), self.reviewer)
        withdrawn = withdraw_release(second["id"], self.reviewer)["release"]
        self.assertEqual("withdrawn", withdrawn["state"])
        tombstone = next(row for row in pull_catalog(report, SimpleNamespace(id=inside, is_platform_admin=False))["items"] if row["category"] == "APP_SKILLS")
        self.assertTrue(tombstone["withdrawn"])

        restored = rollback_release(first["id"], self.reviewer)["release"]
        self.assertEqual("published", restored["state"])
        self.assertGreater(restored["version"], second["version"])
        self.assertEqual(1, restored["metrics"]["rollbacks"])


if __name__ == "__main__":
    unittest.main()
