from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class ServerWorkspaceHandoffRegressionTest(unittest.TestCase):
    def test_workspace_uses_atomic_turn_contract_and_real_routing_inputs(self) -> None:
        api = (ROOT / "console/src/workspaceApi.ts").read_text(encoding="utf-8")
        page = (ROOT / "console/src/pages/WorkspacePage.tsx").read_text(encoding="utf-8")

        self.assertIn('fetch("/api/turns"', api)
        self.assertIn('"Idempotency-Key": idempotencyKey', api)
        self.assertIn('workspaceApi.createTurn({', page)
        self.assertIn('project_id: projectId || null', page)
        self.assertIn('target_device_id: targetDeviceId', page)
        self.assertIn('"run_events_v1"', page)
        self.assertIn('"llm.chat"', page)
        self.assertIn('...(mode === "ask" ? [] : ["agent.tools"])', page)
        self.assertNotIn("/api/chat", page)

    def test_handoff_has_one_strict_scheme_and_two_existing_desktop_routes(self) -> None:
        producer = (ROOT / "console/src/desktopHandoff.ts").read_text(encoding="utf-8")
        consumer = (ROOT / "src/platform/deepLinks.ts").read_text(encoding="utf-8")
        router = (ROOT / "src/lib/router.ts").read_text(encoding="utf-8")
        config = (ROOT / "src-tauri/tauri.conf.json").read_text(encoding="utf-8")

        self.assertIn("agentmate://open/run?", producer)
        self.assertIn('url.protocol !== "agentmate:"', consumer)
        self.assertIn('url.hostname !== "open"', consumer)
        self.assertIn('url.pathname !== "/run"', consumer)
        self.assertIn("SAFE_ID.test(sessionId)", consumer)
        self.assertIn("/projects/${encodeURIComponent(projectId)}/runs/", consumer)
        self.assertIn("/chat/${encodeURIComponent(sessionId)}", consumer)
        self.assertIn(r"/^\/chat\/([^/]+)$/", router)
        self.assertIn("m[1] !== 'new'", router)
        self.assertIn(r"/^\/projects\/([^/]+)\/runs\/([^/]+)$/", router)
        self.assertIn("m[2] !== 'new'", router)
        self.assertIn('"schemes": ["agentmate"]', config)

    def test_installed_app_receives_handoff_in_a_single_instance(self) -> None:
        rust = (ROOT / "src-tauri/src/lib.rs").read_text(encoding="utf-8")
        app = (ROOT / "src/App.tsx").read_text(encoding="utf-8")
        execution = (ROOT / "console/src/components/project/WorkItemExecution.tsx").read_text(
            encoding="utf-8"
        )

        single = rust.index("tauri_plugin_single_instance::init")
        deep_link = rust.index("tauri_plugin_deep_link::init")
        self.assertLess(single, deep_link)
        self.assertIn("show_window(app);", rust[single:deep_link])
        self.assertIn("startDesktopDeepLinks", app)
        self.assertIn("desktopCompanionRunUrl", execution)
        self.assertIn("在执行节点打开", execution)


if __name__ == "__main__":
    unittest.main()
