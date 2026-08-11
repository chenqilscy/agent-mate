import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class DesktopRunLaunchRetirementContractTests(unittest.TestCase):
    def test_home_and_sidebar_do_not_create_business_runs(self) -> None:
        home = source("src/views/HomeView.tsx")
        sidebar = source("src/components/layout/Sidebar.tsx")

        for forbidden in ("<Composer", "startDraft", "startProject", "void send", "发起本机执行"):
            self.assertNotIn(forbidden, home)
        self.assertNotIn("['projects'", home)
        for forbidden in ("新建任务", "startDraft", "useLoadoutStore", "任务上下文"):
            self.assertNotIn(forbidden, sidebar)
        self.assertIn("最近执行", sidebar)
        self.assertIn("openSession(id)", sidebar)

    def test_new_routes_are_rejected_and_business_pages_handoff(self) -> None:
        app = source("src/App.tsx")
        router = source("src/lib/router.ts")
        handoff = source("src/views/ConsoleHandoffView.tsx")

        self.assertFalse((ROOT / "src/views/WorkspaceContextsView.tsx").exists())
        self.assertNotIn("WorkspaceContextsView", app)
        self.assertNotIn("startDraft", app)
        self.assertNotIn("startProject", app)
        # WB-521 fully retires the standalone inspiration surface instead of
        # handing it off, leaving five business views on the shared handoff.
        self.assertGreaterEqual(app.count("content = <ConsoleHandoffView />"), 5)
        self.assertIn("projects: ['项目与任务'", handoff)
        self.assertNotIn("inspire: ['灵感与新意图'", handoff)
        self.assertNotIn("|| 'new'", router)
        self.assertIn("m[1] !== 'new'", router)
        self.assertIn("m[2] !== 'new'", router)

    def test_existing_runs_keep_controls_without_idle_composer(self) -> None:
        chat = source("src/views/ChatView.tsx")
        project_run = source("src/views/ProjExecView.tsx")

        for view in (chat, project_run):
            self.assertIn("<RunLaunchHandoff", view)
            self.assertIn("streaming ? (", view)
            self.assertIn("<AskUserCard", view)
            self.assertIn("onPause={pause}", view)
            self.assertIn("onResume={resume}", view)
            self.assertIn("onCancel={cancel}", view)
            self.assertNotIn("const send =", view)
        for forbidden in (
            "ProjectTaskCenter",
            "TodoDetailModal",
            "promoteRunPlanItem",
            "useWorkItemStore",
            "Server 任务",
        ):
            self.assertNotIn(forbidden, project_run)
        self.assertIn("<PePanel", project_run)
        self.assertIn("onRetry={retry}", project_run)

    def test_capability_views_cannot_start_local_drafts(self) -> None:
        paths = (
            "src/views/ExpertsView.tsx",
            "src/components/connector/ConnectorDetailModal.tsx",
            "src/components/skill/SkillDetail.tsx",
            "src/components/skill/SkillBundleModal.tsx",
        )
        for path in paths:
            value = source(path)
            self.assertNotIn("startDraft", value, path)
            self.assertNotIn(".send(", value, path)


if __name__ == "__main__":
    unittest.main()
