from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class WorkItemRunNavigationContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.detail = (ROOT / "console" / "src" / "components" / "project" / "WorkItemExecution.tsx").read_text(encoding="utf-8")
        self.handoff = (ROOT / "console" / "src" / "desktopHandoff.ts").read_text(encoding="utf-8")

    def test_new_work_item_run_opens_the_returned_server_session(self) -> None:
        self.assertIn("consoleApi.triggerWorkItemExecutionPolicy", self.detail)
        self.assertIn("desktopCompanionRunUrl", self.detail)
        self.assertIn("sessionId: run.session_id", self.detail)
        self.assertIn("agentmate://open/run?", self.handoff)

    def test_existing_runs_expose_their_real_session(self) -> None:
        self.assertIn("run.session_id", self.detail)
        self.assertIn("在执行节点打开", self.detail)
        self.assertIn('"waiting_user"', self.detail)
        self.assertIn('run.status === "waiting_user"', self.detail)


if __name__ == "__main__":
    unittest.main()
