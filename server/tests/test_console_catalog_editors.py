from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
CONSOLE = ROOT / "console" / "src"


class ConsoleCatalogEditorContractTests(unittest.TestCase):
    def test_catalog_sections_use_pro_table_drawer_and_real_api(self) -> None:
        page = (CONSOLE / "pages" / "CatalogPage.tsx").read_text(encoding="utf-8")
        for marker in ("<ProTable", "<Drawer", "consoleApi.catalog", "createCatalogItem",
                       "updateCatalogItem", "deleteCatalogItem"):
            self.assertIn(marker, page)
        for category in ("EXPERT_DEFS", "EXP_TEAMS", "EXPERT_RECOMMENDATIONS",
                         "CONN_DEFS", "CONNECTOR_RECOMMENDATIONS", "KB_TPLS"):
            self.assertIn(category, page)

    def test_skill_page_keeps_files_and_recommendation_management(self) -> None:
        page = (CONSOLE / "SkillsPage.tsx").read_text(encoding="utf-8")
        editor = (CONSOLE / "SkillEditor.tsx").read_text(encoding="utf-8")
        for marker in ("目录预览", "目录管理", "推荐位管理", "SkillRecommendations",
                       "SKILL_RECOMMENDATIONS"):
            self.assertIn(marker, page)
        for marker in ("file-workspace", "tools.map", "requestClose", "saving"):
            self.assertIn(marker, editor)

    def test_project_workspace_covers_all_legacy_capabilities(self) -> None:
        page = (CONSOLE / "pages" / "ProjectDetailPage.tsx").read_text(encoding="utf-8")
        for marker in ("ProjectOverview", "TasksTab", "KnowledgeTab", "CollaborationTab",
                       "ConfigTab", "createWorkItem", "uploadKnowledgeDocument",
                       "inviteProjectMember", "createComment", "updateProject"):
            self.assertIn(marker, page)

    def test_raw_catalog_and_user_admin_are_react_crud_pages(self) -> None:
        raw = (CONSOLE / "pages" / "RawCatalogPage.tsx").read_text(encoding="utf-8")
        users = (CONSOLE / "pages" / "UsersPage.tsx").read_text(encoding="utf-8")
        self.assertIn("<ProTable", raw)
        self.assertIn("<Drawer", raw)
        for marker in ("createAccount", "updateAccount", "resetPassword", "deleteAccount"):
            self.assertIn(marker, users)


if __name__ == "__main__":
    unittest.main()
