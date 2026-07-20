"""Server 专家团稳定身份与默认目录契约（WB-231）。"""
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
from routers.catalog import _validate_expert_team, delete_item  # noqa: E402


class ExpertTeamContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = settings.DB_PATH
        settings.DB_PATH = Path(self.tmp.name) / "server.db"
        db._local = threading.local()
        db.init_db()

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_path
        db._local = threading.local()
        self.tmp.cleanup()

    def test_default_teams_reference_real_expert_definitions(self) -> None:
        definitions = {
            row["data"]["slug"]
            for row in db.list_catalog_items("EXPERT_DEFS", scope="builtin")
        }
        teams = db.list_catalog_items("EXP_TEAMS", scope="builtin")
        self.assertEqual(3, len(teams))
        members = [member for team in teams for member in team["data"]["members"]]
        self.assertEqual(17, len(members))
        self.assertTrue(all(member["expert_slug"] in definitions for member in members))
        for team in teams:
            _validate_expert_team(team["data"], ignore_id=team["id"])

    def test_invalid_and_duplicate_references_are_rejected(self) -> None:
        base = {
            "name": "测试团队",
            "members": [{"role": "负责人", "name": "测试", "expert_slug": "senior-software-engineer"}],
        }
        _validate_expert_team(base)
        with self.assertRaisesRegex(HTTPException, "does not exist"):
            _validate_expert_team({**base, "members": [{"role": "负责人", "name": "测试", "expert_slug": "missing"}]})
        with self.assertRaisesRegex(HTTPException, "duplicate expert"):
            _validate_expert_team({**base, "members": [base["members"][0], {**base["members"][0], "role": "成员"}]})

    def test_referenced_expert_cannot_be_deleted(self) -> None:
        expert = next(
            row for row in db.list_catalog_items("EXPERT_DEFS", scope="builtin")
            if row["data"]["slug"] == "senior-software-engineer"
        )
        with self.assertRaisesRegex(HTTPException, "recommendation or team"):
            delete_item(expert["id"], SimpleNamespace(is_platform_admin=True))


if __name__ == "__main__":
    unittest.main()
