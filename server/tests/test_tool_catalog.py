"""数据库权威内置工具目录回归（WB-266）。"""
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
    UpdateToolBody, _validate_app_skill, list_skill_tools, list_tools, update_tool,
)


class ToolCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = settings.DB_PATH
        settings.DB_PATH = Path(self.tmp.name) / "server.db"
        db._local = threading.local()
        db.init_db()
        self.admin = SimpleNamespace(id="admin", is_platform_admin=True)

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_path
        db._local = threading.local()
        self.tmp.cleanup()

    def test_full_inventory_and_bindable_projection_are_separate(self) -> None:
        all_tools = list_tools(True, self.admin)["tools"]
        selectable = list_skill_tools(self.admin)["tools"]
        self.assertEqual(25, len(all_tools))
        self.assertEqual(16, len(selectable))
        names = {item["name"] for item in selectable}
        self.assertIn("read_file", names)
        self.assertIn("create_docx", names)
        self.assertIn("browser_navigate", names)
        self.assertNotIn("create_local_skill", names)
        self.assertNotIn("knowledge_add", names)
        self.assertNotIn("ask_user", names)

    def test_console_updates_database_without_bootstrap_overwrite_and_writes_audit(self) -> None:
        result = update_tool(
            "read_file",
            UpdateToolBody(label="读取工作区文件", category="文件", enabled=False, sort=7),
            self.admin,
        )["tool"]
        self.assertEqual("读取工作区文件", result["label"])
        self.assertFalse(result["enabled"])
        self.assertNotIn("read_file", {item["name"] for item in list_skill_tools(self.admin)["tools"]})
        db.init_db()
        self.assertEqual("读取工作区文件", db.get_tool_catalog("read_file")["label"])
        audit = db.list_tool_catalog_audit("read_file")
        self.assertEqual("admin", audit[0]["actor_id"])
        self.assertTrue(audit[0]["before_data"]["enabled"])
        self.assertFalse(audit[0]["after_data"]["enabled"])

    def test_unknown_disabled_and_non_bindable_tools_are_rejected(self) -> None:
        base = {
            "slug": "managed-tool", "name": "Managed Tool", "description": "工具校验",
            "instructions": "执行工具。", "tools": ["read_file"], "files": [],
        }
        _validate_app_skill(base)
        update_tool("read_file", UpdateToolBody(enabled=False), self.admin)
        with self.assertRaisesRegex(HTTPException, "disabled or not bindable"):
            _validate_app_skill(base)
        with self.assertRaisesRegex(HTTPException, "disabled or not bindable"):
            _validate_app_skill({**base, "tools": ["knowledge_retrieve"]})
        with self.assertRaisesRegex(HTTPException, "unknown skill tools"):
            _validate_app_skill({**base, "tools": ["does_not_exist"]})
        with self.assertRaisesRegex(HTTPException, "only skill exposure"):
            update_tool("ask_user", UpdateToolBody(bindable=True), self.admin)

    def test_existing_system_skill_can_retain_internal_tool_only(self) -> None:
        item = next(
            row for row in db.list_catalog_items("APP_SKILLS", scope="builtin", include_disabled=True)
            if row["data"].get("slug") == "skill-creator-guide"
        )
        _validate_app_skill(item["data"], ignore_id=item["id"])
        with self.assertRaisesRegex(HTTPException, "disabled or not bindable"):
            _validate_app_skill({
                "slug": "other", "name": "Other", "description": "Other",
                "instructions": "Other", "tools": ["create_local_skill"], "files": [],
            })


if __name__ == "__main__":
    unittest.main()
