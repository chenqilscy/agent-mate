"""WB-436 Local Agent working-copy and explicit external-file boundaries."""
from __future__ import annotations

import hashlib
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import local_agent_core
import local_agent_ipc
import local_agent_store
from agent import sandbox
from config import settings


class WorkingCopyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_db = settings.LOCAL_AGENT_DB_PATH
        self.old_workspace = settings.WORKSPACE_ROOT
        self.old_base = sandbox.WORKSPACE_BASE
        self.old_default = sandbox.DEFAULT_ROOT
        settings.LOCAL_AGENT_DB_PATH = Path(self.temp.name) / "local-agent.db"
        settings.WORKSPACE_ROOT = (Path(self.temp.name) / "workspace").resolve()
        sandbox.WORKSPACE_BASE = settings.WORKSPACE_ROOT
        sandbox.DEFAULT_ROOT = settings.WORKSPACE_ROOT / "default"
        local_agent_store.close_thread_connection()
        local_agent_store._local = threading.local()
        local_agent_ipc.install_token("b" * 64)
        self.headers = {"X-AgentMate-IPC-Token": "b" * 64}
        self.owner_id = "owner-wb436"
        local_agent_store.set_server_identity(self.owner_id, "server-token", 9999999999)
        self.client = TestClient(local_agent_core.app)

    def tearDown(self) -> None:
        self.client.close()
        local_agent_store.close_thread_connection()
        local_agent_store._local = threading.local()
        local_agent_ipc.clear_token()
        settings.LOCAL_AGENT_DB_PATH = self.old_db
        settings.WORKSPACE_ROOT = self.old_workspace
        sandbox.WORKSPACE_BASE = self.old_base
        sandbox.DEFAULT_ROOT = self.old_default
        self.temp.cleanup()

    def test_workspace_commit_resumes_and_records_committed_version(self) -> None:
        project_id = "project-wb436"
        path = sandbox.project_root(project_id) / "reports" / "result.bin"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = b"working-copy-data"
        path.write_bytes(data)
        sha256 = hashlib.sha256(data).hexdigest()
        uploaded_parts: list[bytes] = []

        def upload_part(_token, _upload_id, _part_number, chunk, _sha):
            uploaded_parts.append(chunk)
            return {"part": {"size": len(chunk)}}

        with (
            patch("server_client.create_server_asset", return_value={"asset": {"id": "asset-wb436"}}),
            patch("server_client.begin_asset_upload", return_value={
                "upload": {"id": "upload-wb436", "state": "uploading", "part_size": 4,
                            "resumed": True, "deduplicated": False},
            }),
            patch("server_client.asset_upload_status", return_value={
                "upload": {"parts": [{"part_number": 0}]},
            }),
            patch("server_client.upload_asset_part", side_effect=upload_part),
            patch("server_client.complete_asset_upload", return_value={
                "object_version": {"id": "version-wb436"},
            }),
        ):
            response = self.client.post(
                "/api/local-agent/assets/commit", headers=self.headers,
                json={
                    "owner_id": self.owner_id, "project_id": project_id,
                    "local_path": "reports/result.bin", "run_id": "run-wb436",
                },
            )
        self.assertEqual(200, response.status_code, response.text)
        copy = response.json()["working_copy"]
        self.assertEqual("committed", copy["state"])
        self.assertEqual("asset-wb436", copy["asset_id"])
        self.assertEqual("version-wb436", copy["object_version_id"])
        self.assertEqual(sha256, copy["sha256"])
        self.assertEqual(data[4:], b"".join(uploaded_parts), "part 0 must be skipped on resume")

    def test_same_path_and_bytes_create_run_scoped_server_assets(self) -> None:
        project_id = "project-run-scope-461"
        path = sandbox.project_root(project_id) / "result.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("same delivery bytes", encoding="utf-8")
        keys: list[str] = []
        payloads: list[dict] = []

        def create(_token, payload, key):
            payloads.append(payload)
            keys.append(key)
            return {"asset": {"id": f"asset-{len(keys)}"}}

        def begin(_token, asset_id, _size, _sha):
            return {
                "upload": {
                    "id": f"upload-{asset_id}", "state": "committed", "part_size": 1024,
                    "resumed": False, "deduplicated": True,
                    "object_version_id": f"version-{asset_id}",
                },
            }

        with (
            patch("server_client.create_server_asset", side_effect=create),
            patch("server_client.begin_asset_upload", side_effect=begin),
        ):
            for run_id in ("run-one-461", "run-two-461"):
                response = self.client.post(
                    "/api/local-agent/assets/commit", headers=self.headers,
                    json={
                        "owner_id": self.owner_id, "project_id": project_id,
                        "local_path": "result.txt", "run_id": run_id,
                    },
                )
                self.assertEqual(200, response.status_code, response.text)

        self.assertEqual(["run-one-461", "run-two-461"], [item["run_id"] for item in payloads])
        self.assertNotEqual(keys[0], keys[1])
        self.assertTrue(all(key.startswith("working-copy:") for key in keys))
        self.assertTrue(all(len(key) <= 120 for key in keys))

    def test_offline_file_stays_local_only_and_external_requires_consent(self) -> None:
        local = sandbox.project_root(None) / "draft.txt"
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text("not uploaded", encoding="utf-8")
        with patch("server_client.create_server_asset", return_value=None):
            offline = self.client.post(
                "/api/local-agent/assets/commit", headers=self.headers,
                json={"owner_id": self.owner_id, "local_path": "draft.txt"},
            )
        self.assertEqual(503, offline.status_code, offline.text)
        copies = local_agent_store.list_working_copies(self.owner_id)
        self.assertEqual(1, len(copies))
        self.assertEqual("local-only", copies[0]["state"])
        self.assertEqual("", copies[0]["asset_id"])

        external = Path(self.temp.name) / "external.txt"
        external.write_text("external original", encoding="utf-8")
        rejected = self.client.post(
            "/api/local-agent/assets/commit", headers=self.headers,
            json={"owner_id": self.owner_id, "local_path": str(external), "external": True},
        )
        self.assertEqual(409, rejected.status_code, rejected.text)
        self.assertTrue(external.is_file())

    def test_verified_download_and_cleanup_never_delete_external_original(self) -> None:
        data = b"restored-on-device-two"
        sha256 = hashlib.sha256(data).hexdigest()

        def stream_to_file(_token, _asset_id, _grant, target):
            target.write_bytes(data)
            return {"x-asset-sha256": sha256}

        with (
            patch("server_client.create_asset_download_grant", return_value={
                "token": "short-grant",
                "object_version": {"id": "version-two", "size": len(data), "sha256": sha256},
            }),
            patch("server_client.download_asset_to_file", side_effect=stream_to_file),
        ):
            response = self.client.post(
                "/api/local-agent/assets/asset-two/download", headers=self.headers,
                json={
                    "owner_id": self.owner_id, "project_id": "project-two",
                    "relative_path": "restored/result.bin",
                },
            )
        self.assertEqual(200, response.status_code, response.text)
        target = sandbox.project_root("project-two") / "restored" / "result.bin"
        self.assertEqual(data, target.read_bytes())

        external = Path(self.temp.name) / "do-not-delete.txt"
        external.write_text("keep me", encoding="utf-8")
        copy = local_agent_store.upsert_working_copy(
            owner_id=self.owner_id, relative_path=str(external), source_kind="external",
            asset_id="asset-external", state="committed",
        )
        cleanup = self.client.delete(
            f"/api/local-agent/assets/working-copies/{copy['id']}",
            params={"owner_id": self.owner_id, "delete_file": True}, headers=self.headers,
        )
        self.assertEqual(409, cleanup.status_code, cleanup.text)
        self.assertTrue(external.is_file())

        workspace_copy = response.json()["working_copy"]
        cleaned = self.client.delete(
            f"/api/local-agent/assets/working-copies/{workspace_copy['id']}",
            params={"owner_id": self.owner_id, "delete_file": True}, headers=self.headers,
        )
        self.assertEqual(200, cleaned.status_code, cleaned.text)
        self.assertTrue(cleaned.json()["file_deleted"])
        audit = local_agent_store.get_conn().execute(
            "SELECT action FROM asset_working_copy_audit WHERE working_copy_id=? ORDER BY created_at DESC LIMIT 1",
            (workspace_copy["id"],),
        ).fetchone()
        self.assertEqual("working-copy.cleanup.file", audit["action"])


if __name__ == "__main__":
    unittest.main()
