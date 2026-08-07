from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class TaskGovernanceEntryContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.work = (ROOT / "src" / "components" / "project" / "ProjectWork.tsx").read_text(encoding="utf-8")
        self.section = (ROOT / "src" / "components" / "project" / "TaskGovernanceSection.tsx").read_text(encoding="utf-8")

    def test_task_detail_mounts_governance_entry_with_write_gate(self) -> None:
        self.assertIn("<TaskGovernanceSection projectId={projectId} item={item} canWrite={canWrite}", self.work)
        self.assertIn("{canWrite && <Space", self.section)
        self.assertIn("showCreate('risk')", self.section)
        self.assertIn("showCreate('decision')", self.section)

    def test_create_payload_preserves_native_task_context(self) -> None:
        for contract in (
            "work_item_id: item.id",
            "milestone_id: item.milestone_id || ''",
            "owner_id: item.assignee || ''",
            "riskSeverityForWorkItem(item.priority)",
        ):
            self.assertIn(contract, self.section)
        self.assertIn("record.work_item_id === item.id", self.section)
        self.assertIn("riskDescriptionForWorkItem(item)", self.section)


if __name__ == "__main__":
    unittest.main()
