"""Regression gate for the local SkillHub / installed-only file boundary (WB-215)."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[2]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from agent import skills_store  # noqa: E402
from routers import skills as skills_router  # noqa: E402


class SkillMarketBoundaryTest(unittest.TestCase):
    def test_app_routes_query_local_market_and_expose_no_preview_endpoint(self) -> None:
        card = {"slug": "demo", "name": "Demo", "description": "metadata only"}
        with patch.object(skills_store, "search", return_value=[card]) as search:
            result = skills_router.search_skills("demo", 6)
        self.assertEqual("app", result["source"])
        self.assertEqual([card], result["results"])
        search.assert_called_once_with("demo", 6)

        with patch.object(skills_store, "rankings", return_value=[card]) as rankings:
            result = skills_router.skills_rankings("hot", "office", 12)
        self.assertEqual("app", result["source"])
        rankings.assert_called_once_with("hot", "office", 12)

        paths = {route.path for route in skills_router.router.routes}
        self.assertNotIn("/api/skills/preview", paths)
        self.assertFalse(hasattr(skills_store, "preview"))

    def test_search_returns_normalized_metadata_without_file_content(self) -> None:
        payload = {"results": [{
            "slug": "demo", "name": "Demo", "description_zh": "商店描述",
            "version": "1.2.3", "downloads": 9, "stars": 2, "tags": ["office"],
            "markdown": "SECRET SKILL CONTENT", "references": ["private.md"],
        }]}
        completed = subprocess.CompletedProcess([], 0, json.dumps(payload, ensure_ascii=False), "")
        with (
            patch.object(skills_store, "cli_available", return_value=True),
            patch.object(skills_store, "_run_cli", return_value=completed),
            patch.object(skills_store, "scan", return_value=[]),
        ):
            cards = skills_store.search("demo", 8)

        self.assertEqual("商店描述", cards[0]["description"])
        self.assertEqual("1.2.3", cards[0]["version"])
        self.assertNotIn("markdown", cards[0])
        self.assertNotIn("references", cards[0])

    def test_server_and_frontend_contain_no_third_party_preview_or_proxy(self) -> None:
        server_main = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
        server_catalog = (ROOT / "server" / "routers" / "catalog.py").read_text(encoding="utf-8")
        detail = (ROOT / "src" / "components" / "skill" / "SkillDetail.tsx").read_text(encoding="utf-8")
        api = (ROOT / "src" / "lib" / "api.ts").read_text(encoding="utf-8")

        self.assertNotIn("skillhub_sync", server_main)
        self.assertNotIn("/catalog/skills/", server_catalog)
        self.assertFalse((ROOT / "server" / "skillhub_client.py").exists())
        self.assertFalse((ROOT / "server" / "skillhub_sync.py").exists())
        self.assertNotIn("skillPreview", detail + api)
        self.assertIn("安装后可查看 SKILL.md、源码、引用文件", detail)


if __name__ == "__main__":
    unittest.main()
