"""WB-427: App and Console share safe, lossless project-management contracts."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
PROJECT_HOME = ROOT / "src" / "views" / "ProjectHomeView.tsx"
PROJECT_WORK = ROOT / "src" / "components" / "project" / "ProjectWork.tsx"
CONSOLE_WORK = ROOT / "console" / "src" / "components" / "project" / "ProjectWorkspace.tsx"


class WB427AppConsoleContractTests(unittest.TestCase):
    def test_server_metadata_is_project_scoped_and_preserves_failure_state(self) -> None:
        source = PROJECT_HOME.read_text(encoding="utf-8")
        for marker in (
            "projectId: pid",
            "serverMetadata?.projectId === project.id",
            "fieldsReachable: fields.status === 'fulfilled'",
            "preferencesReachable: preferences.status === 'fulfilled'",
            "fields: fieldCount,",
            "savedViews,",
            "setServerMetadata(null)",
            "失败区域不会被当作空配置",
        ):
            self.assertIn(marker, source)
        self.assertNotIn("fields: fieldCount ?? 0", source)
        self.assertNotIn("savedViews: savedViews ?? 0", source)

    def test_sprint_defaults_use_local_calendar_dates(self) -> None:
        source = PROJECT_HOME.read_text(encoding="utf-8")
        date_helper = source.split("function dateAfter", 1)[1].split("\n}", 1)[0]
        self.assertIn("date.getFullYear()", date_helper)
        self.assertIn("date.getMonth() + 1", date_helper)
        self.assertNotIn("toISOString", date_helper)

    def test_shared_templates_keep_all_server_supported_task_fields(self) -> None:
        source = PROJECT_WORK.read_text(encoding="utf-8")
        for field in (
            "status", "source", "assignee", "description", "due_date", "start_date",
            "labels", "parent_id", "milestone_id", "estimate_h", "spent_h",
            "custom_fields", "dependency_ids", "sprint_id",
        ):
            self.assertIn(f"{field}:", source)
        self.assertIn("add({ title: t.name, ...t.values })", source)
        self.assertIn("values: workItemTemplateValues(item)", source)

    def test_app_and_console_send_optimistic_concurrency_revisions(self) -> None:
        app_source = PROJECT_WORK.read_text(encoding="utf-8")
        console_source = CONSOLE_WORK.read_text(encoding="utf-8")
        self.assertIn("expected_shared_updated_at: current.shared_updated_at", app_source)
        self.assertIn("expected_views_updated_at: current.views_updated_at", app_source)
        self.assertIn("!canManage || !sharedPmPreferencesReady", app_source)
        self.assertIn("expected_shared_updated_at: preferenceRevisions.current.shared", console_source)
        self.assertIn("expected_views_updated_at: preferenceRevisions.current.views", console_source)


if __name__ == "__main__":
    unittest.main()
