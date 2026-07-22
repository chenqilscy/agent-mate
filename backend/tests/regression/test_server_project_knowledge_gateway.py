"""WB-290: Server-origin projects use central KB routes without local credential fallback."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

import server_sync  # noqa: E402
from agent import runtime, tools, weknora  # noqa: E402
from agent.sandbox import use_root  # noqa: E402


class ServerKnowledgeSyncTest(unittest.TestCase):
    @patch.object(server_sync.db, "list_server_sync_conflicts", return_value=[])
    @patch.object(server_sync.db, "reconcile_server_project_access")
    @patch.object(server_sync.db, "user_id_for_token", return_value=None)
    @patch.object(server_sync.db, "replace_server_project_members")
    @patch.object(server_sync.db, "mirror_server_project")
    @patch.object(server_sync.server_client, "list_project_members", return_value=[])
    @patch.object(server_sync.server_client, "list_projects", return_value=[{
        "id": "project-1", "name": "Shared", "owner_id": "owner-1",
        "instruction": "", "connectors": [], "experts": [], "skills": [],
        "knowledge_ids": ["kb-stable-1"], "updated_at": 10,
    }])
    def test_pull_forwards_central_stable_ids(self, _projects, _members, mirror, *_rest) -> None:
        result = server_sync.pull("server-token")
        self.assertEqual(1, result["synced"])
        self.assertEqual(["kb-stable-1"], mirror.call_args.kwargs["knowledge_ids"])


class ServerKnowledgeToolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "workspace"
        use_root(self.root)
        tools.set_knowledge_context(
            "owner-a", ["kb-stable-1"],
            server_project_id="project-1", server_token="server-token",
        )

    def tearDown(self) -> None:
        tools.set_knowledge_context(None, None)
        self.tmp.cleanup()

    @patch.object(weknora, "search")
    @patch.object(tools.server_client, "search_project_knowledge", return_value=[{
        "text": "central fact", "score": 0.8, "metadata": {"doc_name": "team.md"},
    }])
    def test_retrieve_uses_server_and_never_local_weknora(self, central_search, local_search) -> None:
        outcome = tools._knowledge_retrieve_run({"query": "fact"})
        self.assertIn("central fact", outcome.text)
        central_search.assert_called_once_with(
            "server-token", "project-1", query="fact", knowledge_ids=["kb-stable-1"], top_k=8,
        )
        local_search.assert_not_called()

    @patch.object(weknora, "search")
    @patch.object(tools.server_client, "search_project_knowledge", return_value=None)
    def test_remote_failure_is_truthful_without_local_fallback(self, _central_search, local_search) -> None:
        outcome = tools._knowledge_retrieve_run({"query": "fact"})
        self.assertIn("未回退到本地知识库", outcome.text)
        local_search.assert_not_called()

    @patch.object(weknora, "upload_file")
    @patch.object(weknora, "configured", return_value=False)
    @patch.object(tools.server_client, "upload_project_knowledge_file", return_value={"id": "doc-1"})
    @patch.object(tools.server_client, "list_project_knowledge", return_value=[{
        "id": "kb-stable-1", "name": "Team", "provider_status": "ready",
    }])
    def test_add_uploads_explicit_file_via_server_without_owner_config(
        self, _list_kbs, central_upload, _configured, local_upload,
    ) -> None:
        target = self.root / "team.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("shared", encoding="utf-8")
        outcome = tools._knowledge_add_run({"path": "team.md"})
        self.assertIn("已把「team.md」加入知识库", outcome.text)
        central_upload.assert_called_once()
        local_upload.assert_not_called()

    def test_runtime_registers_remote_tools_without_local_weknora_key(self) -> None:
        with patch.object(runtime.weknora, "configured", return_value=False) as configured:
            selected = runtime._knowledge_tools(
                "owner-a", ["kb-stable-1"], ask=False, remote_project=True,
            )
        self.assertEqual([tools.knowledge_retrieve, tools.knowledge_add], selected)
        configured.assert_not_called()


if __name__ == "__main__":
    unittest.main()
