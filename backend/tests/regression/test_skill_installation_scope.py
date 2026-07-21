"""Owner-scoped Skill installation, locking and recovery coverage (WB-249)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import tempfile
import threading
import unittest
from pathlib import Path

from agent import skills_store
from config import settings
from storage import db
from storage.models import LOCAL_USER_ID


class SkillInstallationScopeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = settings.DB_PATH
        self.old_skills = settings.SKILLS_DIR
        self._close()
        settings.DB_PATH = Path(self.tmp.name) / "test.db"
        settings.SKILLS_DIR = Path(self.tmp.name) / "skills"
        db.init_db()
        self.other = db.create_user(name="other", password="pw")
        skills_store.set_owner(LOCAL_USER_ID)

    def tearDown(self) -> None:
        skills_store.set_owner(LOCAL_USER_ID)
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

    @staticmethod
    def _install(version: str, instruction: str = "执行技能。") -> dict:
        return skills_store.install_catalog_skill(
            "shared-skill", "共享技能", "共享安装测试", instruction, version,
            tools=["analyze_csv"],
        )

    def _packages(self) -> list[Path]:
        return sorted(
            path for path in settings.SKILLS_DIR.iterdir()
            if path.is_dir() and (path / skills_store.SKILL_MD).is_file()
        )

    def test_two_owners_share_package_but_keep_independent_enabled_state(self) -> None:
        first = self._install("1")
        skills_store.set_owner(self.other.id)
        second = self._install("1")
        self.assertTrue(second.get("reused"))
        self.assertEqual(1, len(self._packages()))

        self.assertTrue(skills_store.set_disabled("shared-skill", True))
        self.assertTrue(skills_store.scan(self.other.id)[0]["disabled"])
        self.assertFalse(skills_store.scan(LOCAL_USER_ID)[0]["disabled"])
        self.assertEqual(first["skill"]["content_hash"], second["skill"]["content_hash"])

    def test_shared_upgrade_pins_each_owner_to_its_release(self) -> None:
        self._install("1", "版本一。")
        v1 = skills_store.release_snapshot("shared-skill")
        skills_store.set_owner(self.other.id)
        self._install("1", "版本一。")

        skills_store.set_owner(LOCAL_USER_ID)
        skills_store.upgrade_catalog_skill(
            "shared-skill", "共享技能", "共享安装测试", "版本二。", "2",
            tools=["analyze_csv"],
        )
        local_v2 = skills_store.release_snapshot("shared-skill")
        skills_store.set_owner(self.other.id)
        other_v1 = skills_store.release_snapshot("shared-skill")
        self.assertEqual("2", local_v2["version"])
        self.assertEqual("1", other_v1["version"])
        self.assertEqual(v1["content_hash"], other_v1["content_hash"])
        self.assertEqual(2, len(self._packages()))

    def test_last_uninstall_moves_to_trash_and_restore_recovers(self) -> None:
        self._install("1")
        self.assertTrue(skills_store.uninstall("shared-skill"))
        self.assertEqual([], self._packages())
        trash = settings.SKILLS_DIR / ".trash"
        self.assertEqual(1, len([path for path in trash.iterdir() if path.is_dir()]))
        self.assertTrue(skills_store.restore("shared-skill"))
        self.assertEqual(1, len(self._packages()))
        self.assertFalse(skills_store.scan()[0]["disabled"])

    def test_project_reference_prevents_physical_collection(self) -> None:
        self._install("1")
        project = db.create_project(owner_id=LOCAL_USER_ID, name="referencing")
        db.get_conn().execute(
            "UPDATE projects SET skills='[\"shared-skill\"]' WHERE id=?", (project.id,),
        )
        db.get_conn().commit()
        self.assertTrue(skills_store.uninstall("shared-skill"))
        self.assertEqual(1, len(self._packages()))

    def test_concurrent_install_is_deterministic_and_has_no_half_package(self) -> None:
        barrier = threading.Barrier(2)

        def install_for(owner: str) -> dict:
            try:
                skills_store.set_owner(owner)
                barrier.wait()
                return self._install("1")
            finally:
                conn = getattr(db._local, "conn", None)
                if conn is not None:
                    conn.close()
                    db._local.conn = None

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(install_for, [LOCAL_USER_ID, self.other.id]))
        self.assertTrue(all(result["ok"] for result in results))
        self.assertEqual(1, len(self._packages()))
        self.assertTrue((self._packages()[0] / skills_store.RELEASE_MANIFEST).is_file())
        self.assertEqual(1, len(skills_store.scan(LOCAL_USER_ID)))
        self.assertEqual(1, len(skills_store.scan(self.other.id)))


if __name__ == "__main__":
    unittest.main()
