from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class ProjectViewerUiContractTests(unittest.TestCase):
    def test_project_workspace_propagates_viewer_write_permission(self) -> None:
        source = (ROOT / "src" / "views" / "ProjectHomeView.tsx").read_text(encoding="utf-8")

        self.assertIn("const canWrite = project.role !== 'Viewer'", source)
        for component in ("PlanWorkspace", "TaskList", "AssetsManager", "ServerCommentsPanel"):
            self.assertRegex(source, rf"<{component}[^>]*canWrite")
        self.assertIn("canWrite ? (", source)
        self.assertIn("<Composer", source)
        self.assertIn("只读模式 · 可查看项目内容，不能发起执行或修改协作数据", source)

    def test_project_write_surfaces_consume_permission(self) -> None:
        work = (ROOT / "src" / "components" / "project" / "ProjectWork.tsx").read_text(encoding="utf-8")
        assets = (ROOT / "src" / "components" / "project" / "AssetsManager.tsx").read_text(encoding="utf-8")
        comments = (ROOT / "src" / "components" / "server" / "ServerCommentsPanel.tsx").read_text(encoding="utf-8")

        self.assertIn("draggable={canWrite && !batch}", work)
        self.assertIn("{canWrite && <WbButton className=\"btn-dark\"", work)
        self.assertIn("delivery?.can_write", work)
        self.assertIn("onRemove={canWrite ? rmAttach : undefined}", work)
        self.assertIn("disabled={!canWrite}", work)
        self.assertIn("view === 'gantt' && <GanttView canWrite={canWrite}", work)
        self.assertIn("view === 'calendar' && <CalendarView canWrite={canWrite}", work)
        self.assertIn("{canWrite && <WbButton className=\"cap-act\"", assets)
        self.assertIn("...(canWrite ? [{ key: 'rename'", assets)
        self.assertIn("{canWrite ? (", comments)
        self.assertIn("不能发表评论", comments)


if __name__ == "__main__":
    unittest.main()
