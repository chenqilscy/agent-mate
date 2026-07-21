"""Verified, lazy Skill resource mounting regression coverage (WB-247)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from config import settings
from agent import skills_store
from agent.sandbox import use_root
from agent.skill_resources import (
    set_active_skill_resources,
    skill_copy_template,
    skill_list_resources,
    skill_read_resource,
)
from storage import db


class SkillRuntimeResourcesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_skills_dir = settings.SKILLS_DIR
        self.old_db = settings.DB_PATH
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        db._local = __import__("threading").local()
        settings.DB_PATH = Path(self.tmp.name) / "test.db"
        settings.SKILLS_DIR = Path(self.tmp.name) / "skills"
        db.init_db()
        self.workspace = Path(self.tmp.name) / "workspace"
        use_root(self.workspace)
        skills_store.install_catalog_skill(
            "ops-kit", "运营工具箱", "运行时资源测试", "按需读取参考资料。", "1",
            files=[
                {"path": "references/guide.md", "content": "# 检查清单\n"},
                {"path": "templates/report.txt", "content": "结论：{{summary}}\n"},
                {"path": "scripts/check.py", "content": "print('read only')\n"},
            ],
        )
        snapshot = skills_store.release_snapshot("ops-kit")
        self.assertIsNotNone(snapshot)
        set_active_skill_resources([snapshot])

    def tearDown(self) -> None:
        set_active_skill_resources([])
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        db._local = __import__("threading").local()
        settings.DB_PATH = self.old_db
        settings.SKILLS_DIR = self.old_skills_dir
        self.tmp.cleanup()

    def test_manifest_resources_are_listed_and_read_lazily(self) -> None:
        listing = skill_list_resources.run({"skill": "ops-kit"}).text
        self.assertIn("references/guide.md", listing)
        self.assertIn("templates/report.txt", listing)
        self.assertIn("scripts/check.py", listing)

        result = skill_read_resource.run({"skill": "ops-kit", "path": "references/guide.md"})
        self.assertEqual("# 检查清单\n", result.text)
        self.assertEqual("skill://ops-kit/references/guide.md", result.trace[0]["path"])

        script = skill_read_resource.run({"skill": "ops-kit", "path": "scripts/check.py"})
        self.assertIn("read only", script.text)

    def test_only_manifest_paths_are_visible_and_traversal_is_rejected(self) -> None:
        package = settings.SKILLS_DIR / "ops-kit"
        (package / "undeclared.txt").write_text("secret", encoding="utf-8")
        undeclared = skill_read_resource.run({"skill": "ops-kit", "path": "undeclared.txt"})
        escaped = skill_read_resource.run({"skill": "ops-kit", "path": "../secret.txt"})
        self.assertIn("未在当前 release manifest 中声明", undeclared.text)
        self.assertIn("非法", escaped.text)

    def test_tampering_is_detected_at_each_read(self) -> None:
        target = settings.SKILLS_DIR / "ops-kit" / "references" / "guide.md"
        target.write_text("tampered", encoding="utf-8")
        result = skill_read_resource.run({"skill": "ops-kit", "path": "references/guide.md"})
        self.assertIn("完整性校验失败", result.text)

    def test_template_copy_is_atomic_and_workspace_scoped(self) -> None:
        result = skill_copy_template.run({
            "skill": "ops-kit", "path": "templates/report.txt", "destination": "reports/today.txt",
        })
        self.assertEqual("结论：{{summary}}\n", (self.workspace / "reports" / "today.txt").read_text(encoding="utf-8"))
        self.assertEqual([{"path": "reports/today.txt", "kind": "skill-template"}], result.artifacts)

        not_template = skill_copy_template.run({
            "skill": "ops-kit", "path": "references/guide.md", "destination": "guide.md",
        })
        escaped = skill_copy_template.run({
            "skill": "ops-kit", "path": "templates/report.txt", "destination": "../outside.txt",
        })
        self.assertIn("只有 templates/", not_template.text)
        self.assertIn("路径越界", escaped.text)
        self.assertFalse((Path(self.tmp.name) / "outside.txt").exists())


if __name__ == "__main__":
    unittest.main()
