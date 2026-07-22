"""WB-290: central project WeKnora authorization, mapping and legacy migration."""
from __future__ import annotations

import asyncio
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

import db  # noqa: E402
from config import settings  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from models import Role  # noqa: E402
from routers import knowledge, projects  # noqa: E402
from starlette.requests import Request  # noqa: E402


class ProjectWeKnoraGatewayTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = settings.DB_PATH
        self.old_storage = settings.STORAGE_DIR
        self.old_url = settings.WEKNORA_URL
        self.old_key = settings.WEKNORA_API_KEY
        self.old_model = settings.WEKNORA_EMBEDDING_MODEL_ID
        settings.DB_PATH = Path(self.tmp.name) / "server.db"
        settings.STORAGE_DIR = Path(self.tmp.name) / "storage"
        settings.WEKNORA_URL = "http://weknora.internal"
        settings.WEKNORA_API_KEY = "server-secret"
        settings.WEKNORA_EMBEDDING_MODEL_ID = "embedding-1"
        db._local = threading.local(); db.init_db()
        self.owner = db.create_account(name="owner", password="password123")
        self.member = db.create_account(name="member", password="password123")
        self.viewer = db.create_account(name="viewer", password="password123")
        self.project = db.create_project(name="Shared", owner_id=self.owner.id)
        db.add_project_member(self.project.id, self.member.id, Role.MEMBER)
        db.add_project_member(self.project.id, self.viewer.id, Role.VIEWER)

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_db
        settings.STORAGE_DIR = self.old_storage
        settings.WEKNORA_URL = self.old_url
        settings.WEKNORA_API_KEY = self.old_key
        settings.WEKNORA_EMBEDDING_MODEL_ID = self.old_model
        db._local = threading.local(); self.tmp.cleanup()

    @patch.object(knowledge.weknora, "create_kb", return_value={"id": "provider-kb-secret"})
    def test_create_keeps_provider_id_private_and_downlinks_stable_id(self, create_remote) -> None:
        result = knowledge.create_kb(
            self.project.id, knowledge.CreateKbBody(name="Team docs"), self.owner,
        )
        self.assertEqual("weknora", result["provider"])
        self.assertEqual("ready", result["provider_status"])
        self.assertNotIn("provider_id", result)
        self.assertNotEqual("provider-kb-secret", result["id"])
        project = projects.get_project(self.project.id, self.owner)
        self.assertEqual([result["id"]], project["knowledge_ids"])
        create_remote.assert_called_once()

        with self.assertRaisesRegex(HTTPException, "Admin/Owner"):
            knowledge.create_kb(
                self.project.id, knowledge.CreateKbBody(name="Denied"), self.viewer,
            )

    @patch.object(knowledge.weknora, "search", return_value=[{
        "text": "grounded", "score": 0.9, "metadata": {"doc_name": "guide.md", "doc_id": "doc-1"},
    }])
    @patch.object(knowledge.weknora, "create_kb", return_value={"id": "provider-kb-1"})
    def test_search_resolves_only_project_stable_ids(self, _create_remote, search_remote) -> None:
        created = knowledge.create_kb(
            self.project.id, knowledge.CreateKbBody(name="Docs"), self.owner,
        )
        result = knowledge.search_project_knowledge(
            self.project.id,
            knowledge.SearchBody(query="answer", knowledge_ids=[created["id"]], top_k=3),
            self.viewer,
        )
        self.assertEqual("grounded", result["hits"][0]["text"])
        search_remote.assert_called_once_with(
            query="answer", provider_ids=["provider-kb-1"], top_k=3,
        )
        with self.assertRaisesRegex(HTTPException, "knowledge base not found"):
            knowledge.search_project_knowledge(
                self.project.id,
                knowledge.SearchBody(query="answer", knowledge_ids=["provider-kb-1"]),
                self.viewer,
            )

    @patch.object(knowledge.weknora, "upload_file", return_value={
        "id": "provider-doc-1", "file_name": "shared.md", "parse_status": "completed",
    })
    @patch.object(knowledge.weknora, "create_kb", return_value={"id": "provider-kb-1"})
    def test_member_can_upload_but_viewer_is_read_only(self, _create_remote, upload_remote) -> None:
        created = knowledge.create_kb(
            self.project.id, knowledge.CreateKbBody(name="Docs"), self.owner,
        )

        async def receive() -> dict:
            return {"type": "http.request", "body": b"central content", "more_body": False}

        def request() -> Request:
            return Request({"type": "http", "method": "POST", "path": "/", "headers": []}, receive)

        uploaded = asyncio.run(knowledge.upload_document(
            self.project.id, created["id"], request(), "shared.md", self.member,
        ))
        self.assertEqual("completed", uploaded["parse_status"])
        upload_remote.assert_called_once()
        with self.assertRaisesRegex(HTTPException, "read-only"):
            asyncio.run(knowledge.upload_document(
                self.project.id, created["id"], request(), "shared.md", self.viewer,
            ))

    @patch.object(knowledge.weknora, "upload_file", return_value={"id": "provider-doc-1"})
    @patch.object(knowledge.weknora, "create_kb", return_value={"id": "provider-kb-migrated"})
    def test_legacy_migration_is_explicit_and_retains_source_bytes(self, _create_remote, upload_remote) -> None:
        legacy = db.create_kb(project_id=self.project.id, name="Legacy")
        source = settings.STORAGE_DIR / "kb" / legacy["id"] / "doc-local"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"legacy content")
        local_doc = db.create_kb_document(
            kb_id=legacy["id"], project_id=self.project.id, filename="legacy.md",
            size=14, content_type="text/markdown", storage_path=str(source),
        )
        before = knowledge.list_kbs(self.project.id, self.owner)["items"][0]
        self.assertEqual("legacy_pending", before["provider_status"])
        self.assertEqual([], projects.get_project(self.project.id, self.owner)["knowledge_ids"])
        legacy_doc = knowledge.list_documents(self.project.id, legacy["id"], self.owner)["items"][0]
        self.assertEqual("legacy_pending", legacy_doc["parse_status"])
        self.assertNotIn("storage_path", legacy_doc)
        self.assertNotIn("provider_id", legacy_doc)
        self.assertNotIn(str(source), repr(legacy_doc))

        migrated = knowledge.migrate_legacy_kb(self.project.id, legacy["id"], self.owner)

        self.assertEqual("ready", migrated["provider_status"])
        self.assertTrue(source.is_file(), "migration must retain rollback bytes")
        self.assertEqual("provider-doc-1", db.get_kb_document(local_doc["id"])["provider_id"])
        self.assertEqual([legacy["id"]], projects.get_project(self.project.id, self.owner)["knowledge_ids"])
        upload_remote.assert_called_once()

    def test_config_status_never_returns_secret(self) -> None:
        self.owner.is_platform_admin = True
        status = knowledge.knowledge_config(self.owner)
        self.assertTrue(status["configured"])
        self.assertNotIn("api_key", status)
        self.assertNotIn("server-secret", repr(status))

        settings.WEKNORA_API_KEY = ""
        unavailable = knowledge.knowledge_config(self.owner)
        self.assertFalse(unavailable["configured"])
        with self.assertRaisesRegex(HTTPException, "尚未配置") as raised:
            knowledge.create_kb(
                self.project.id, knowledge.CreateKbBody(name="Unavailable"), self.owner,
            )
        self.assertEqual(502, raised.exception.status_code)


if __name__ == "__main__":
    unittest.main()
