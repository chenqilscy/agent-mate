from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class ProjectPlanMultiViewContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.work = (ROOT / "src" / "components" / "project" / "ProjectWork.tsx").read_text(encoding="utf-8")

    def test_plan_workspace_uses_one_store_for_all_real_views(self) -> None:
        for key in ("table", "kanban", "list", "gantt", "calendar", "workload"):
            self.assertIn(f"key: '{key}'", self.work)
        for component in ("TaskList", "KanbanBoard", "GroupedListView", "GanttView", "CalendarView"):
            self.assertRegex(self.work, rf"view === '[^']+' && <{component}[^>]*canWrite")
        self.assertIn("pm.plan.view.${projectId}", self.work)

    def test_calendar_maps_real_dates_and_creates_on_selected_day(self) -> None:
        self.assertIn("const key = item.due_date || item.start_date", self.work)
        self.assertIn("const undated = items.filter((item) => !item.start_date && !item.due_date)", self.work)
        self.assertIn('initialDue={createOn}', self.work)
        self.assertIn('onCreated={(item) => setDetailId(item.id)}', self.work)
        self.assertIn('canWrite && createOn', self.work)

    def test_quick_create_persists_complete_planning_fields(self) -> None:
        self.assertIn("const [status, setStatus] = useState<WorkStatus>(initialStatus)", self.work)
        self.assertIn("const [start, setStart] = useState<string | null>(null)", self.work)
        self.assertIn("start_date: start, due_date: due", self.work)
        self.assertIn("开始日期不能晚于截止日期", self.work)
        self.assertIn("<StatusPill status={status} onPick={setStatus}", self.work)
        self.assertIn("<StartDatePill value={start}", self.work)


if __name__ == "__main__":
    unittest.main()
