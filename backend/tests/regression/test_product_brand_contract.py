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
            "src/views/HomeView.tsx": "AgentMate<br />",
            "src/components/layout/Sidebar.tsx": "<b>AgentMate</b>",
            "src/components/chat/MessageList.tsx": '<div className="bot-nm">AgentMate</div>',
            "src/lib/exportChat.ts": "_由 AgentMate 导出_",
            "backend/agent/runtime.py": "你是 AgentMate",
            "hub/web/console.html": "AgentMate Manager",
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
        self.assertEqual(["binaries/agentmate-backend"], tauri["bundle"]["externalBin"])
        config = read("backend/config.py")
        self.assertIn('base / "AgentMate"', config)
        self.assertIn('os.getenv("AGENTMATE_DB"', config)
        self.assertIn('Path.home() / ".agentmate" / "skills"', config)
        legacy = "WORK" + "BUDDY"
        self.assertNotIn(legacy + "_", config)
        self.assertNotIn(legacy.lower() + "-backend", read("backend/build_sidecar.py"))


if __name__ == "__main__":
    unittest.main()
