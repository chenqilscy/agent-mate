"""WB-518: Desktop home is the local execution control surface."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class DesktopHomeBoundaryContractTest(unittest.TestCase):
    def test_home_does_not_duplicate_server_workspace_business_lists(self) -> None:
        home = (ROOT / "src" / "views" / "HomeView.tsx").read_text(encoding="utf-8")

        for forbidden in (
            "useWorkbenchStore",
            "loadWorkbench",
            "startWorkItemRun",
            "我的行动项",
            "需要我处理",
            "待验收",
        ):
            self.assertNotIn(forbidden, home)

    def test_home_keeps_real_local_execution_and_workspace_handoff(self) -> None:
        home = (ROOT / "src" / "views" / "HomeView.tsx").read_text(encoding="utf-8")

        for marker in (
            "useConnectivityStore",
            "执行节点状态",
            "活动租约",
            "待回执事件",
            "Local Agent Core",
            "打开 Server Workspace",
            "本机能力",
        ):
            self.assertIn(marker, home)
        self.assertNotIn("<Composer", home)
        self.assertNotIn("发起本机执行", home)


if __name__ == "__main__":
    unittest.main()
