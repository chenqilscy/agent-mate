"""WB-193: knowledge_add URL import and fail-closed WeKnora security gate."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import call, patch

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from agent import runtime, tools, weknora  # noqa: E402
from agent.sandbox import use_root  # noqa: E402


class WeKnoraURLClientTest(unittest.TestCase):
    def test_url_import_requires_known_stable_safe_version(self) -> None:
        unsafe = (
            ({}, "无法可靠识别"),
            ({"version": "0.2.11"}, "低于安全最低版本"),
            ({"version": "0.2.12-rc1"}, "无法可靠识别"),
        )
        for info, expected in unsafe:
            with self.subTest(info=info), patch.object(weknora, "system_info", return_value=info):
                with self.assertRaisesRegex(weknora.WeKnoraError, expected):
                    weknora.require_safe_url_import("owner-a")

        with patch.object(weknora, "system_info", return_value={"version": "v0.2.12"}):
            self.assertEqual("v0.2.12", weknora.require_safe_url_import("owner-a"))

        with patch.object(weknora, "system_info", side_effect=weknora.WeKnoraError("403")):
            with self.assertRaisesRegex(weknora.WeKnoraError, "无法通过 WeKnora /api/v1/system/info"):
                weknora.require_safe_url_import("owner-a")

    def test_create_from_url_checks_version_then_posts_same_owner_credentials(self) -> None:
        with patch.object(weknora, "system_info", return_value={"version": "0.6.2"}), patch.object(
            weknora, "_request", return_value={"id": "doc-1"},
        ) as request:
            result = weknora.create_from_url("owner-a", "kb-1", url="https://docs.example.com/guide")
        self.assertEqual("doc-1", result["id"])
        request.assert_called_once_with(
            "owner-a", "POST", "/knowledge-bases/kb-1/knowledge/url",
            json={"url": "https://docs.example.com/guide"},
        )

    def test_ssrf_rejection_is_actionable(self) -> None:
        with patch.object(weknora, "system_info", return_value={"version": "0.6.2"}), patch.object(
            weknora, "_request", side_effect=weknora.WeKnoraError("URL failed SSRF whitelist validation"),
        ):
            with self.assertRaises(weknora.WeKnoraError) as raised:
                weknora.create_from_url("owner-a", "kb-1", url="https://blocked.example.com")
        message = str(raised.exception)
        self.assertIn("系统设置 → SSRF 白名单", message)
        self.assertIn("SSRF_WHITELIST_EXTRA", message)
        self.assertIn("不要", message)

    def test_invalid_url_is_rejected_before_network(self) -> None:
        for raw in ("ftp://example.com/x", "https://user:pass@example.com/x", "not a url"):
            with self.subTest(raw=raw), patch.object(weknora, "system_info") as info:
                with self.assertRaisesRegex(weknora.WeKnoraError, "URL 格式非法"):
                    weknora.create_from_url("owner-a", "kb-1", url=raw)
                info.assert_not_called()


class KnowledgeAddToolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "workspace"
        use_root(self.root)
        tools.set_knowledge_context("owner-a", [])

    def tearDown(self) -> None:
        self.tmp.cleanup()

    @patch.object(weknora, "configured", return_value=False)
    def test_unconfigured_weknora_keeps_actionable_setup_error(self, _configured) -> None:
        self.assertEqual(weknora.NOT_CONFIGURED, tools._knowledge_add_run({"url": "https://example.com"}).text)

    @patch.object(weknora, "configured", return_value=True)
    def test_path_and_url_are_exactly_one(self, _configured) -> None:
        missing = tools._knowledge_add_run({})
        both = tools._knowledge_add_run({"path": "a.md", "url": "https://example.com"})
        self.assertIn("恰好提供一个", missing.text)
        self.assertIn("恰好提供一个", both.text)

    @patch.object(weknora, "create_from_url")
    @patch.object(weknora, "upload_file")
    @patch.object(weknora, "list_kb", return_value=[{"id": "kb-1", "name": "Docs"}])
    @patch.object(weknora, "configured", return_value=True)
    def test_legacy_path_still_uploads_file(self, _configured, _list_kb, upload, create_url) -> None:
        target = self.root / "old-path.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("legacy path regression", encoding="utf-8")

        outcome = tools._knowledge_add_run({"path": "old-path.md"})

        self.assertIn("已把「old-path.md」加入知识库", outcome.text)
        upload.assert_called_once()
        self.assertEqual(("owner-a", "kb-1"), upload.call_args.args)
        self.assertEqual("old-path.md", upload.call_args.kwargs["filename"])
        self.assertEqual(b"legacy path regression", upload.call_args.kwargs["content"])
        self.assertTrue(upload.call_args.kwargs["content_type"])
        create_url.assert_not_called()

    @patch.object(weknora, "create_from_url")
    @patch.object(weknora, "list_kb", return_value=[{"id": "kb-1", "name": "Docs"}])
    @patch.object(weknora, "configured", return_value=True)
    def test_url_uses_same_target_resolution_and_owner(self, _configured, _list_kb, create_url) -> None:
        outcome = tools._knowledge_add_run({"url": "https://docs.example.com/guide"})

        self.assertIn("URL「https://docs.example.com/guide」", outcome.text)
        self.assertEqual([call("owner-a", "kb-1", url="https://docs.example.com/guide")], create_url.call_args_list)

    def test_schema_no_longer_requires_path(self) -> None:
        params = tools.knowledge_add.parameters
        self.assertNotIn("required", params)
        self.assertEqual({"path", "url"}, {k for k in params["properties"] if k in ("path", "url")})

    def test_runtime_registers_add_from_owner_level_configuration(self) -> None:
        with patch.object(runtime.weknora, "configured", return_value=True) as configured:
            selected = runtime._knowledge_tools("owner-db", [], ask=False)
        self.assertEqual([tools.knowledge_add], selected)
        configured.assert_called_once_with("owner-db")
        self.assertEqual([], runtime._knowledge_tools("owner-db", [], ask=True))


if __name__ == "__main__":
    unittest.main()
