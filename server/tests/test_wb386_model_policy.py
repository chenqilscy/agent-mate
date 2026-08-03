"""WB-386 Server organization model-policy authority and role gates."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import threading
import unittest

from fastapi import HTTPException

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

import db  # noqa: E402
from config import settings  # noqa: E402
from models import Role  # noqa: E402
from routers.orgs import (  # noqa: E402
    OrgModelPolicyBody, get_model_policy, list_model_policies, set_model_policy,
)


class OrganizationModelPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = settings.DB_PATH
        settings.DB_PATH = Path(self.tmp.name) / "server.db"
        db._local = threading.local()
        db.init_db()
        self.owner = db.create_account(name="owner", password="password123")
        self.admin = db.create_account(name="admin", password="password123")
        self.member = db.create_account(name="member", password="password123")
        self.outsider = db.create_account(name="outsider", password="password123")
        self.org = db.create_org(name="governed", owner_id=self.owner.id)
        db.add_org_member(self.org.id, self.admin.id, Role.ADMIN)
        db.add_org_member(self.org.id, self.member.id, Role.MEMBER)

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_path
        db._local = threading.local()
        self.tmp.cleanup()

    def test_owner_and_admin_write_member_reads_and_revision_increments(self) -> None:
        body = OrgModelPolicyBody(
            allowlist=["@deepseek:deepseek-v4-flash", "@deepseek:deepseek-v4-flash"],
            fallback_chain=["@openai:gpt-4o-mini"], daily_hard_tokens=100_000,
        )
        first = set_model_policy(self.org.id, body, self.owner)
        self.assertEqual(1, first["revision"])
        self.assertEqual(["@deepseek:deepseek-v4-flash"], first["policy"]["allowlist"])
        self.assertEqual(first, get_model_policy(self.org.id, self.member))

        second = set_model_policy(
            self.org.id, OrgModelPolicyBody(monthly_hard_tokens=500_000), self.admin,
        )
        self.assertEqual(2, second["revision"])
        self.assertEqual(self.admin.id, second["updated_by"])
        self.assertEqual([second], list_model_policies(self.member)["policies"])

    def test_member_cannot_write_and_outsider_cannot_read(self) -> None:
        with self.assertRaisesRegex(HTTPException, "Admin/Owner"):
            set_model_policy(self.org.id, OrgModelPolicyBody(), self.member)
        with self.assertRaisesRegex(HTTPException, "org not found"):
            get_model_policy(self.org.id, self.outsider)

    def test_policy_contract_contains_no_credentials_or_endpoints(self) -> None:
        result = set_model_policy(
            self.org.id,
            OrgModelPolicyBody(allowlist=["@openai:gpt-4o-mini"]),
            self.owner,
        )
        serialized = repr(result).lower()
        self.assertNotIn("api_key", serialized)
        self.assertNotIn("base_url", serialized)
        self.assertNotIn("secret", serialized)


if __name__ == "__main__":
    unittest.main()
