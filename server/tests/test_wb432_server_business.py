"""WB-432 durable Server business-plane API and isolation contracts."""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

import db  # noqa: E402
from config import settings  # noqa: E402
from models import Role  # noqa: E402
from routers import business  # noqa: E402


class DurableBusinessPlaneTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_path = settings.DB_PATH
        self._close()
        settings.DB_PATH = Path(self.temp.name) / "server.db"
        db.init_db()
        self.owner = db.create_account(name="owner-432", password="password123")
        self.member = db.create_account(name="member-432", password="password123")
        self.viewer = db.create_account(name="viewer-432", password="password123")
        self.outsider = db.create_account(name="outsider-432", password="password123")
        self.project = db.create_project(name="Shared business", owner_id=self.owner.id)
        db.add_project_member(self.project.id, self.member.id, Role.MEMBER)
        db.add_project_member(self.project.id, self.viewer.id, Role.VIEWER)
        self.tokens = {
            account.id: db.create_token(account.id)[0]
            for account in (self.owner, self.member, self.viewer, self.outsider)
        }
        app = FastAPI()
        app.include_router(business.router)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        self._close()
        settings.DB_PATH = self.old_path
        db._local = threading.local()
        self.temp.cleanup()

    @staticmethod
    def _close() -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
            db._local.conn = None

    def _auth(self, account) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.tokens[account.id]}"}

    def test_complete_graph_is_idempotent_visible_and_durable(self) -> None:
        headers = {**self._auth(self.owner), "Idempotency-Key": "desktop-a-session-1"}
        payload = {"title": "Architecture", "project_id": self.project.id, "kind": "chat"}
        first = self.client.post("/api/sessions", headers=headers, json=payload)
        duplicate = self.client.post("/api/sessions", headers=headers, json=payload)
        self.assertEqual(200, first.status_code, first.text)
        self.assertEqual(first.json()["session"]["id"], duplicate.json()["session"]["id"])
        self.assertTrue(duplicate.json()["duplicate"])
        session_id = first.json()["session"]["id"]
        mismatch = self.client.post(
            "/api/sessions", headers=headers,
            json={"title": "Different", "project_id": self.project.id, "kind": "chat"},
        )
        self.assertEqual(409, mismatch.status_code, mismatch.text)

        message = self.client.post(
            f"/api/sessions/{session_id}/messages",
            headers={**self._auth(self.owner), "Idempotency-Key": "desktop-a-message-1"},
            json={"role": "user", "content": "ship it"},
        )
        self.assertEqual(200, message.status_code, message.text)
        self.assertEqual(1, message.json()["message"]["sequence"])
        run = self.client.post(
            "/api/runs", headers={**self._auth(self.owner), "Idempotency-Key": "desktop-a-run-1"},
            json={"session_id": session_id, "mode": "exec", "workspace": "project"},
        )
        self.assertEqual(200, run.status_code, run.text)
        run_id = run.json()["run"]["id"]
        step = self.client.post(
            f"/api/runs/{run_id}/steps",
            headers={**self._auth(self.owner), "Idempotency-Key": "desktop-a-step-1"},
            json={"kind": "tool", "status": "succeeded", "payload": {"tool": "read_file"}},
        )
        self.assertEqual(200, step.status_code, step.text)
        asset = self.client.post(
            "/api/assets", headers={**self._auth(self.owner), "Idempotency-Key": "desktop-a-asset-1"},
            json={
                "project_id": self.project.id, "session_id": session_id, "run_id": run_id,
                "name": "report.md", "mime_type": "text/markdown", "size": 12,
                "sha256": "a" * 64,
            },
        )
        self.assertEqual(200, asset.status_code, asset.text)

        assistant = self.client.post(
            "/api/assistants",
            headers={**self._auth(self.owner), "Idempotency-Key": "desktop-a-assistant-1"},
            json={"name": "Delivery", "project_id": self.project.id, "skills": []},
        )
        self.assertEqual(200, assistant.status_code, assistant.text)
        assistant_id = assistant.json()["assistant"]["id"]
        channel = self.client.post(
            f"/api/assistants/{assistant_id}/channels",
            headers={**self._auth(self.owner), "Idempotency-Key": "desktop-a-channel-1"},
            json={
                "type": "telegram", "public_config": {"chat_ids": ["42"]},
                "credential_ref": "device://credentials/telegram-main", "enabled": True,
            },
        )
        self.assertEqual(200, channel.status_code, channel.text)
        automation = self.client.post(
            "/api/automations",
            headers={**self._auth(self.owner), "Idempotency-Key": "desktop-a-automation-1"},
            json={
                "name": "Daily", "prompt": "Summarize", "project_id": self.project.id,
                "trigger_kind": "daily", "at_time": "09:30",
            },
        )
        self.assertEqual(200, automation.status_code, automation.text)

        member_headers = self._auth(self.member)
        for path, key in (
            (f"/api/sessions/{session_id}", "id"),
            (f"/api/runs/{run_id}", "id"),
            (f"/api/assistants/{assistant_id}", "id"),
        ):
            response = self.client.get(path, headers=member_headers)
            self.assertEqual(200, response.status_code, response.text)
            self.assertTrue(response.json()[key])
        self.assertEqual(
            1,
            len(self.client.get(
                "/api/automations", params={"project_id": self.project.id}, headers=member_headers,
            ).json()["automations"]),
        )

        # Closing and reopening the SQLite connection simulates a second Server
        # process/client reading the committed authority rather than local state.
        self._close()
        db.init_db()
        restored = self.client.get(f"/api/runs/{run_id}", headers=self._auth(self.owner))
        self.assertEqual(200, restored.status_code, restored.text)
        self.assertEqual(session_id, restored.json()["session_id"])
        self.assertEqual(
            1,
            len(self.client.get(f"/api/runs/{run_id}/steps", headers=self._auth(self.owner)).json()["steps"]),
        )
        self.assertGreaterEqual(
            len(self.client.get(
                "/api/business/audit", params={"project_id": self.project.id}, headers=self._auth(self.owner),
            ).json()["audit"]),
            7,
        )
        self.assertEqual([], db.get_conn().execute("PRAGMA foreign_key_check").fetchall())
        counts = db.project_delete_counts(self.project.id)
        self.assertEqual(1, counts["sessions"])
        self.assertEqual(1, counts["runs"])
        self.assertEqual(1, counts["assistants"])
        self.assertEqual(1, counts["automations"])
        self.assertEqual(1, counts["assets"])

    def test_role_revocation_secret_and_cursor_gates(self) -> None:
        owner_headers = self._auth(self.owner)
        created_ids: list[str] = []
        for index in range(4):
            response = self.client.post(
                "/api/sessions", headers={**owner_headers, "Idempotency-Key": f"personal-{index}"},
                json={"title": f"Session {index}", "kind": "chat"},
            )
            self.assertEqual(200, response.status_code, response.text)
            created_ids.append(response.json()["session"]["id"])
        first = self.client.get("/api/sessions", params={"limit": 2}, headers=owner_headers).json()
        second = self.client.get(
            "/api/sessions", params={"limit": 2, "cursor": first["next_cursor"]}, headers=owner_headers,
        ).json()
        self.assertEqual(2, len(first["sessions"]))
        self.assertFalse({item["id"] for item in first["sessions"]} & {item["id"] for item in second["sessions"]})

        project_session = self.client.post(
            "/api/sessions", headers=owner_headers,
            json={"title": "Shared", "project_id": self.project.id},
        ).json()["session"]
        viewer_read = self.client.get(
            f"/api/sessions/{project_session['id']}", headers=self._auth(self.viewer),
        )
        self.assertEqual(200, viewer_read.status_code, viewer_read.text)
        viewer_write = self.client.post(
            "/api/sessions", headers=self._auth(self.viewer),
            json={"title": "Forbidden", "project_id": self.project.id},
        )
        self.assertEqual(403, viewer_write.status_code, viewer_write.text)
        outsider_read = self.client.get(
            f"/api/sessions/{project_session['id']}", headers=self._auth(self.outsider),
        )
        self.assertEqual(404, outsider_read.status_code, outsider_read.text)

        stale = self.client.patch(
            f"/api/sessions/{project_session['id']}", headers=owner_headers,
            json={"expected_version": 999, "title": "stale"},
        )
        self.assertEqual(409, stale.status_code, stale.text)

        assistant = self.client.post(
            "/api/assistants", headers=owner_headers,
            json={"name": "Secret gate", "project_id": self.project.id},
        ).json()["assistant"]
        secret = self.client.post(
            f"/api/assistants/{assistant['id']}/channels", headers=owner_headers,
            json={"type": "telegram", "public_config": {"bot_token": "must-not-upload"}},
        )
        self.assertEqual(400, secret.status_code, secret.text)
        rows = db.get_conn().execute("SELECT public_config FROM business_channels").fetchall()
        self.assertFalse(any("must-not-upload" in row[0] for row in rows))
        camel_case_secret = self.client.post(
            f"/api/assistants/{assistant['id']}/channels", headers=owner_headers,
            json={"type": "telegram", "public_config": {"botToken": "must-not-upload"}},
        )
        self.assertEqual(400, camel_case_secret.status_code, camel_case_secret.text)
        impersonation = self.client.post(
            f"/api/sessions/{project_session['id']}/messages", headers=owner_headers,
            json={"role": "user", "content": "forged", "actor_id": self.member.id},
        )
        self.assertEqual(403, impersonation.status_code, impersonation.text)

        db.remove_project_member(self.project.id, self.member.id)
        revoked_member = self.client.get(
            f"/api/sessions/{project_session['id']}", headers=self._auth(self.member),
        )
        self.assertEqual(404, revoked_member.status_code, revoked_member.text)
        viewer_token = self.tokens[self.viewer.id]
        db.delete_token(viewer_token)
        revoked_token = self.client.get("/api/sessions", headers=self._auth(self.viewer))
        self.assertEqual(401, revoked_token.status_code, revoked_token.text)


if __name__ == "__main__":
    unittest.main()
