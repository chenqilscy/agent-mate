"""Owner/release Skill usage telemetry and advisory governance (WB-337)."""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from agent import skill_discovery, skill_usage, skills_store  # noqa: E402
from config import settings  # noqa: E402
from storage import db  # noqa: E402


class SkillUsageGovernanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = settings.DB_PATH
        self.old_skills = settings.SKILLS_DIR
        self._close()
        root = Path(self.tmp.name)
        settings.DB_PATH = root / "test.db"
        settings.SKILLS_DIR = root / "skills"
        db.init_db()
        skills_store.set_owner("owner-a")
        skills_store._invalidate_cache()

    def tearDown(self) -> None:
        skill_discovery.clear_skill_candidates()
        skill_usage.clear_context()
        skills_store.set_owner(None)
        skills_store._invalidate_cache()
        self._close()
        settings.DB_PATH = self.old_db
        settings.SKILLS_DIR = self.old_skills
        self.tmp.cleanup()

    @staticmethod
    def _close() -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        db._local = threading.local()

    def _install(self, slug: str, name: str = "Usage Skill") -> dict:
        return skills_store.create_skill(
            slug, name, "usage telemetry test", "Follow the verified procedure.",
        )["skill"]

    def test_discovery_and_view_do_not_count_as_load_until_parent_runtime_activates(self) -> None:
        self._install("usage")
        candidates = skill_discovery.build_skill_candidates([])
        skill_discovery.set_skill_candidates(candidates)
        skill_usage.set_context("owner-a", "run-1")

        skill_discovery.skills_list.run({})
        skill_discovery.skills_list.run({})  # same run/release/event is idempotent
        viewed = skill_discovery.skill_view.run({"name": "usage"})
        self.assertIn("Skill：Usage Skill", viewed.text)
        summary = skill_usage.summaries("owner-a")[0]
        self.assertEqual(1, summary["discoveries"])
        self.assertEqual(0, summary["loads"])

        snapshot = {
            "slug": candidates[0]["slug"],
            "release_id": f"local:{candidates[0]['content_hash']}",
            "content_hash": candidates[0]["content_hash"],
        }
        skill_usage.record("loaded", snapshot, owner_id="owner-a", run_id="run-1")
        skill_usage.record("loaded", snapshot, owner_id="owner-a", run_id="run-1")
        skill_usage.record("run_succeeded", snapshot, owner_id="owner-a", run_id="run-1")
        summary = skill_usage.summaries("owner-a")[0]
        self.assertEqual(1, summary["loads"])
        self.assertEqual(1, summary["successes"])
        self.assertEqual(1.0, summary["success_rate"])

    def test_metrics_are_owner_and_release_scoped_and_ratings_are_latest_value(self) -> None:
        first = self._install("scoped")
        item = skills_store.scan("owner-a")[0]
        skill_usage.record("loaded", item, owner_id="owner-a", run_id="run-a")
        skill_usage.record("run_failed", item, owner_id="owner-a", run_id="run-a")
        self.assertEqual(1, skill_usage.summaries("owner-a")[0]["failures"])

        skills_store.set_owner("owner-b")
        db.upsert_skill_installation(
            "owner-b", "scoped", str(first["key"]),
            content_hash=str(first["content_hash"]), enabled=True,
        )
        self.assertEqual(0, skill_usage.summaries("owner-b")[0]["loads"])
        skill_usage.rate("owner-b", skills_store.scan("owner-b")[0], "not_helpful")
        self.assertEqual("not_helpful", skill_usage.summaries("owner-b")[0]["rating"])
        self.assertIsNone(skill_usage.summaries("owner-a")[0]["rating"])

    def test_stale_suggestions_are_explainable_ignorable_and_never_mutate_packages(self) -> None:
        skill = self._install("old-unused")
        meta_path = settings.SKILLS_DIR / str(skill["key"]) / skills_store.SKILLHUB_META
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        old = time.time() - 40 * 86400
        meta["installedAt"] = int(old * 1000)
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        skills_store._invalidate_cache()

        suggestions = skill_usage.suggestions("owner-a", now=time.time())
        self.assertEqual(1, len(suggestions))
        suggestion = suggestions[0]
        self.assertEqual("never_loaded", suggestion["reason"])
        self.assertEqual("disable", suggestion["recommended_action"])
        self.assertFalse(suggestion["automatic_action"])
        self.assertIsNotNone(skills_store.detail("old-unused"))

        skill_usage.ignore_suggestion("owner-a", suggestion["id"])
        self.assertEqual([], skill_usage.suggestions("owner-a", now=time.time()))
        self.assertTrue(skills_store.set_disabled("old-unused", True))
        self.assertIsNotNone(skills_store.detail("old-unused"))
        self.assertTrue(skills_store.set_disabled("old-unused", False))
        self.assertFalse(skills_store.scan("owner-a")[0]["disabled"])

    def test_low_success_and_duplicate_name_are_advisory_only(self) -> None:
        first = self._install("low-one", "Duplicate")
        second = self._install("low-two", "Duplicate")
        item = next(value for value in skills_store.scan("owner-a") if value["slug"] == "low-one")
        for index in range(5):
            skill_usage.record("loaded", item, owner_id="owner-a", run_id=f"run-{index}")
            skill_usage.record(
                "run_succeeded" if index == 0 else "run_failed",
                item,
                owner_id="owner-a",
                run_id=f"run-{index}",
            )
        suggestions = skill_usage.suggestions("owner-a")
        reasons = {item["reason"] for item in suggestions}
        self.assertIn("low_success", reasons)
        self.assertIn("duplicate_name", reasons)
        self.assertTrue(all(not item["automatic_action"] for item in suggestions))
        self.assertTrue((settings.SKILLS_DIR / str(first["key"])).is_dir())
        self.assertTrue((settings.SKILLS_DIR / str(second["key"])).is_dir())


if __name__ == "__main__":
    unittest.main()
