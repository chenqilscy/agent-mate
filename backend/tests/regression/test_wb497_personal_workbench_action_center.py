"""WB-497 data contracts remain valid after the business UI moved to Workspace."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class PersonalWorkbenchActionCenterContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.home = (ROOT / "src/views/HomeView.tsx").read_text(encoding="utf-8")
        self.store = (ROOT / "src/stores/workbenchStore.ts").read_text(encoding="utf-8")
        self.workbench = (ROOT / "src/lib/workbench.ts").read_text(encoding="utf-8")
        self.api = (ROOT / "src/lib/api.ts").read_text(encoding="utf-8")
        self.types = (ROOT / "src/lib/types.ts").read_text(encoding="utf-8")
        self.css = (ROOT / "src/styles/app.css").read_text(encoding="utf-8")

    def test_personal_action_items_keep_server_authority_and_typed_contract(self) -> None:
        self.assertIn("export interface PersonalActionItemsResponse", self.types)
        self.assertIn("export interface PersonalActionItem extends WorkItem", self.types)
        self.assertIn("serverGet<PersonalActionItemsResponse>(`/work-items/action-items?as_of=", self.api)
        self.assertIn("api.listPersonalActionItems(localDate(), { onResolvedState })", self.store)
        self.assertNotIn("/api/ideas", self.store)

    def test_partial_failure_helpers_preserve_each_last_successful_domain(self) -> None:
        self.assertIn("Promise.allSettled", self.store)
        self.assertIn("mergeWorkbenchDomains(current, actions, runs)", self.store)
        self.assertIn("actions.status === 'fulfilled' ? actions.value.value.items : current.actionItems", self.workbench)
        self.assertIn("runs.status === 'fulfilled' ? runs.value.value.runs : current.runs", self.workbench)

    def test_desktop_home_no_longer_consumes_business_workbench_aggregation(self) -> None:
        self.assertNotIn("useWorkbenchStore", self.home)
        self.assertNotIn("loadWorkbench", self.home)
        self.assertNotIn("startWorkItemRun", self.home)
        self.assertNotIn("我的行动项", self.home)
        self.assertNotIn("待验收", self.home)
        for marker in ("执行节点状态", "打开 Server Workspace", "发起本机执行"):
            self.assertIn(marker, self.home)

    def test_offline_and_responsive_boundaries_remain_explicit(self) -> None:
        self.assertIn("Local Agent 离线，暂时不能开始本机执行", self.home)
        self.assertIn("server.state === 'cached'", self.home)
        self.assertIn("@media (max-width: 1280px)", self.css)
        self.assertIn("@media (max-width: 640px)", self.css)
        self.assertIn(".home-workbench-layout", self.css)
        self.assertIn("var(--bg-surface)", self.css)
        self.assertIn(".home-quick-start.is-keyboard-navigation .composer:focus-within", self.css)


if __name__ == "__main__":
    unittest.main()
