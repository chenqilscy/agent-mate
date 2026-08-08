"""WB-446/WB-448/WB-449 App-side Server-first reconnect boundaries."""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class AppRunReconnectContractTest(unittest.TestCase):
    def test_run_follow_uses_epoch_cursor_and_navigation_detaches_without_cancel(self) -> None:
        sse = (ROOT / "src/lib/sse.ts").read_text(encoding="utf-8")
        store = (ROOT / "src/stores/chatStore.ts").read_text(encoding="utf-8")
        self.assertIn("export async function followServerRun", sse)
        self.assertIn("after_epoch: String(afterEpoch)", sse)
        self.assertIn("after_sequence: String(afterSequence)", sse)
        self.assertIn("type: 'run_recovered'", sse)
        self.assertNotIn("cancelServerTurn", sse)
        self.assertIn("ACTIVE_SERVER_RUNS", store)
        self.assertIn("void followServerRun", store)
        self.assertIn("if (get().streaming) get().detach()", store)
        self.assertIn("api.stopRun(runId)", store)

    def test_identity_binding_and_console_handoff_fail_honestly(self) -> None:
        auth = (ROOT / "src/stores/authStore.ts").read_text(encoding="utf-8")
        settings = (ROOT / "src/components/settings/SettingsModal.tsx").read_text(encoding="utf-8")
        self.assertIn("if (!bound) throw new Error", auth)
        self.assertGreaterEqual(auth.count("localStorage.removeItem(TOKEN_KEY)"), 4)
        self.assertNotIn("openServerConsole('/account')", settings)

    def test_webhook_management_uses_server_channel(self) -> None:
        api = (ROOT / "src/lib/api.ts").read_text(encoding="utf-8")
        section = api[api.index("getAutomationWebhook"):api.index("listAllAutomationRuns")]
        self.assertIn("serverGet<AutomationWebhookConfig>", section)
        self.assertEqual(3, section.count("serverSend<"))
        self.assertNotIn("send<AutomationWebhookConfig>", section.replace("serverSend", ""))


if __name__ == "__main__":
    unittest.main()
