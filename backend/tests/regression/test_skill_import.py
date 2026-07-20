"""Local skill upload/import regression coverage (WB-206)."""
from __future__ import annotations

import base64
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from agent import skills_store  # noqa: E402
from config import settings  # noqa: E402


def skill_md(name: str = "本地测试技能", slug: str = "local-test", newline: str = "\n") -> bytes:
    text = newline.join([
        "---",
        f"name: {name}",
        f"slug: {slug}",
        "description: 验证真实本地技能导入",
        "---",
        "",
        "# Instructions",
        "Do the real thing.",
    ])
    return text.encode("utf-8")


class SkillImportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_dir = settings.SKILLS_DIR
        settings.SKILLS_DIR = Path(self.tmp.name) / "skills"
        skills_store._invalidate_cache()

    def tearDown(self) -> None:
        settings.SKILLS_DIR = self.old_dir
        skills_store._invalidate_cache()
        self.tmp.cleanup()

    def test_import_markdown_with_crlf_is_installed_and_injectable(self) -> None:
        result = skills_store.import_skill_file("anything.md", skill_md(newline="\r\n"))
        self.assertTrue(result["ok"])
        self.assertEqual("local-test", result["skill"]["slug"])
        self.assertEqual("local", result["skill"]["source"])
        self.assertTrue((settings.SKILLS_DIR / "local-test" / "SKILL.md").is_file())
        self.assertIn("Do the real thing", skills_store.instructions_for("local-test") or "")

    def test_zip_preserves_skill_subtree_and_folder_payload_imports(self) -> None:
        archive_bytes = io.BytesIO()
        with zipfile.ZipFile(archive_bytes, "w") as archive:
            archive.writestr("wrapper/demo/SKILL.md", skill_md(slug="zip-demo"))
            archive.writestr("wrapper/demo/references/guide.txt", "guide")
            archive.writestr("wrapper/readme.txt", "outside skill root")
        result = skills_store.import_skill_file("demo.zip", archive_bytes.getvalue())
        self.assertEqual("zip-demo", result["skill"]["slug"])
        self.assertTrue((settings.SKILLS_DIR / "zip-demo" / "references" / "guide.txt").is_file())
        self.assertFalse((settings.SKILLS_DIR / "zip-demo" / "readme.txt").exists())

        folder = skills_store.import_skill_directory([
            {"path": "folder/SKILL.md", "content": base64.b64encode(skill_md(slug="folder-demo")).decode()},
            {"path": "folder/scripts/run.py", "content": base64.b64encode(b"print('ok')\n").decode()},
        ])
        self.assertEqual("folder-demo", folder["skill"]["slug"])
        self.assertTrue((settings.SKILLS_DIR / "folder-demo" / "scripts" / "run.py").is_file())

    def test_rejects_missing_or_multiple_manifest_traversal_and_duplicate_slug(self) -> None:
        with self.assertRaisesRegex(skills_store.SkillImportError, "只能包含一个"):
            skills_store.import_skill_directory([{"path": "readme.md", "content": base64.b64encode(b"x").decode()}])
        with self.assertRaisesRegex(skills_store.SkillImportError, "只能包含一个"):
            skills_store.import_skill_directory([
                {"path": "a/SKILL.md", "content": base64.b64encode(skill_md(slug="a")).decode()},
                {"path": "b/SKILL.md", "content": base64.b64encode(skill_md(slug="b")).decode()},
            ])
        with self.assertRaisesRegex(skills_store.SkillImportError, "非法路径"):
            skills_store.import_skill_directory([
                {"path": "../SKILL.md", "content": base64.b64encode(skill_md(slug="escape")).decode()},
            ])
        skills_store.import_skill_file("first.md", skill_md(slug="duplicate"))
        with self.assertRaisesRegex(skills_store.SkillImportError, "已存在") as caught:
            skills_store.import_skill_file("second.md", skill_md(slug="duplicate"))
        self.assertEqual(409, caught.exception.status_code)
        self.assertEqual([], list(settings.SKILLS_DIR.glob(".skill-import-*")))

    def test_creator_tool_installs_a_real_skill(self) -> None:
        from agent.skills import create_local_skill

        outcome = create_local_skill.run({
            "slug": "created-by-agent",
            "name": "Agent 创建技能",
            "description": "验证技能创建工具真实落盘",
            "instructions": "收到内容后先提炼三条要点。",
        })
        self.assertIn("已创建并安装", outcome.text)
        detail = skills_store.detail("created-by-agent")
        self.assertIsNotNone(detail)
        self.assertEqual("Agent 创建技能", detail["name"])
        self.assertIn("先提炼三条要点", detail["body"])


if __name__ == "__main__":
    unittest.main()
