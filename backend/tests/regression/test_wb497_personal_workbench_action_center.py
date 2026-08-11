from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class PersonalWorkbenchActionCenterContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.home = (ROOT / "src/views/HomeView.tsx").read_text(encoding="utf-8")
        self.store = (ROOT / "src/stores/workbenchStore.ts").read_text(encoding="utf-8")
        self.api = (ROOT / "src/lib/api.ts").read_text(encoding="utf-8")
        self.types = (ROOT / "src/lib/types.ts").read_text(encoding="utf-8")
        self.css = (ROOT / "src/styles/app.css").read_text(encoding="utf-8")

    def test_personal_action_items_use_server_authority_and_typed_contract(self) -> None:
        self.assertIn("export interface PersonalActionItemsResponse", self.types)
        self.assertIn("export interface PersonalActionItem extends WorkItem", self.types)
        self.assertIn("serverGet<PersonalActionItemsResponse>(`/work-items/action-items?as_of=", self.api)
        self.assertIn("api.listPersonalActionItems(localDate())", self.store)
        self.assertNotIn("/api/ideas", self.store)

    def test_partial_failures_preserve_each_last_successful_domain(self) -> None:
        self.assertIn("Promise.allSettled", self.store)
        self.assertIn("actions.status === 'fulfilled' ? actions.value.items : current.actionItems", self.store)
        self.assertIn("runs.status === 'fulfilled' ? runs.value.runs : current.runs", self.store)
        self.assertIn("actionError", self.store)
        self.assertIn("runError", self.store)
        self.assertIn("Server 暂不可达，显示上次同步结果", self.home)

    def test_home_prioritizes_intervention_actions_and_real_runs(self) -> None:
        for label in ("需要我处理", "我的行动项", "快速开始", "正在执行"):
            self.assertIn(label, self.home)
        self.assertIn("waiting_user", self.home)
        self.assertIn("waiting_approval", self.home)
        self.assertIn("awaiting_acceptance", self.home)
        self.assertIn("startWorkItemRun", self.home)
        self.assertIn("idempotencyKey: `workbench:${item.id}:${item.updated_at || item.status}`", self.home)
        self.assertNotIn("<Segmented", self.home)
        self.assertNotIn("最近完成", self.home)

    def test_viewer_offline_and_responsive_boundaries_remain_explicit(self) -> None:
        self.assertIn("item.project.role === 'Viewer'", self.home)
        self.assertIn("Local Agent 离线，暂时不能开始本机执行", self.home)
        self.assertIn("@media (max-width: 1280px)", self.css)
        self.assertIn("@media (max-width: 640px)", self.css)
        self.assertIn(".home-workbench-layout", self.css)
        self.assertIn("var(--bg-surface)", self.css)


if __name__ == "__main__":
    unittest.main()
