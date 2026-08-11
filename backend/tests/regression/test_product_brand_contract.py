"""Product-brand regression contract for the AgentMate rename (WB-208)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class ProductBrandContractTest(unittest.TestCase):
    def test_user_facing_surfaces_use_agentmate(self) -> None:
        expected = {
            "index.html": "<title>AgentMate · 你的智能工作伙伴</title>",
            "src/views/HomeView.tsx": '<b>Desktop Companion</b>',
            "src/components/layout/Sidebar.tsx": "<b>AgentMate Desktop</b>",
            "src/components/chat/MessageList.tsx": '<div className="bot-nm">AgentMate</div>',
            "src/lib/exportChat.ts": "_由 AgentMate 导出_",
            "backend/agent/runtime.py": "你是 AgentMate",
            "console/index.html": "<title>AgentMate Console · Web 管理控制台</title>",
            "src-tauri/src/lib.rs": 'tooltip("AgentMate")',
        }
        for relative, marker in expected.items():
            with self.subTest(path=relative):
                self.assertIn(marker, read(relative))

        tauri = json.loads(read("src-tauri/tauri.conf.json"))
        self.assertEqual("AgentMate", tauri["productName"])
        self.assertEqual("AgentMate", tauri["app"]["windows"][0]["title"])
        self.assertEqual("agentmate", json.loads(read("package.json"))["name"])

    def test_technical_identifiers_are_agentmate_only(self) -> None:
        tauri = json.loads(read("src-tauri/tauri.conf.json"))
        self.assertEqual("com.agentmate.app", tauri["identifier"])
        self.assertEqual(["binaries/agentmate-local-agent"], tauri["bundle"]["externalBin"])
        config = read("backend/config.py")
        self.assertIn('base / "AgentMate"', config)
        self.assertIn('os.getenv("AGENTMATE_DB"', config)
        self.assertIn('Path.home() / ".agentmate" / "skills"', config)
        legacy = "WORK" + "BUDDY"
        self.assertNotIn(legacy + "_", config)
        self.assertNotIn(legacy.lower() + "-backend", read("backend/build_sidecar.py"))

    def test_server_and_console_names_match_their_roles(self) -> None:
        backend_config = read("backend/config.py")
        server_config = read("server/config.py")
        server_main = read("server/main.py")
        app_api = read("src/lib/api.ts")
        app_channels = read("src/lib/channels.ts")
        old_env = "HUB" + "_URL"

        self.assertIn('AGENTMATE_SERVER_URL: str = ""', backend_config)
        self.assertNotIn('os.getenv("AGENTMATE_SERVER_URL"', backend_config)
        self.assertNotIn(old_env, backend_config)
        self.assertIn('str(SERVER_DIR / "server.db")', server_config)
        self.assertIn('title="AgentMate Server API"', server_main)
        self.assertIn("serverGet", app_api)
        self.assertIn("VITE_SERVER_API_BASE", app_channels)
        self.assertNotIn("'/server/status'", app_api)
        self.assertNotIn("'/hub/status'", app_api)

    def test_product_version_is_1_0_0_everywhere(self) -> None:
        expected = "1.0.0"
        self.assertEqual(expected, json.loads(read("package.json"))["version"])
        self.assertEqual(expected, json.loads(read("src-tauri/tauri.conf.json"))["version"])
        self.assertIn(f'version = "{expected}"', read("src-tauri/Cargo.toml"))
        self.assertIn(f'version="{expected}"', read("backend/main.py"))
        self.assertIn(f'version="{expected}"', read("server/main.py"))

    def test_local_stack_ports_are_consistent(self) -> None:
        self.assertIn('os.getenv("AGENTMATE_SERVER_PORT", "8100")', read("server/config.py"))
        self.assertIn('os.getenv("PORT", "8101")', read("backend/config.py"))
        vite = read("vite.config.ts")
        self.assertIn("port: 8102", vite)
        self.assertIn("strictPort: true", vite)
        self.assertIn("target: 'http://127.0.0.1:8101'", vite)
        channels = read("src/lib/channels.ts")
        self.assertIn("http://127.0.0.1:8101/api", channels)
        self.assertIn("'/server-api'", channels)
        self.assertIn("target: 'http://127.0.0.1:8100'", vite)
        self.assertEqual(
            "http://localhost:8102",
            json.loads(read("src-tauri/tauri.conf.json"))["build"]["devUrl"],
        )


if __name__ == "__main__":
    unittest.main()
