from pathlib import Path
import unittest


CONSOLE = (Path(__file__).resolve().parents[1] / "web" / "console.html").read_text(encoding="utf-8")


def _function_block(name: str, next_name: str) -> str:
    for prefix in (f"async function {name}", f"function {name}"):
        start = CONSOLE.find(prefix)
        if start >= 0:
            break
    else:
        raise AssertionError(f"missing function {name}")
    candidates = [
        CONSOLE.find(f"\nasync function {next_name}", start + 1),
        CONSOLE.find(f"\nfunction {next_name}", start + 1),
    ]
    end = min(pos for pos in candidates if pos >= 0)
    return CONSOLE[start:end]


class ConsoleCatalogEditorContractTests(unittest.TestCase):
    def test_catalog_list_views_do_not_embed_full_edit_forms(self) -> None:
        pairs = [
            ("expertRecommendationsView", "expertRecommendationEditor"),
            ("connectorsManage", "connectorEditor"),
            ("connectorRecommendations", "connectorRecommendationEditor"),
            ("knowledgeManage", "knowledgeEditor"),
            ("skillsRecommendations", "skillRecommendationEditor"),
        ]
        for view, editor in pairs:
            block = _function_block(view, editor)
            self.assertNotIn('<div class="card"><h3', block)
            self.assertNotIn("window.scrollTo(0,0)", block)
            self.assertIn(editor, block)

    def test_catalog_editors_share_modal_close_contract(self) -> None:
        self.assertIn('function expModal(inner, modalClass="")', CONSOLE)
        self.assertIn('if(e.key==="Escape") expClose(ov)', CONSOLE)
        for editor in (
            "expertRecommendationEditor",
            "connectorEditor",
            "connectorRecommendationEditor",
            "knowledgeEditor",
            "skillRecommendationEditor",
        ):
            self.assertIn(f"function {editor}", CONSOLE)
            self.assertIn("expModal(", CONSOLE[CONSOLE.index(f"function {editor}") :])

    def test_recommendation_lists_expose_edit_and_patch_paths(self) -> None:
        for view, next_name in (
            ("expertRecommendationsView", "expertRecommendationEditor"),
            ("connectorRecommendations", "connectorRecommendationEditor"),
            ("skillsRecommendations", "skillRecommendationEditor"),
        ):
            self.assertIn('data-ed="${it.id}"', _function_block(view, next_name))
        self.assertIn('api("PATCH","/catalog/item/"+it.id', CONSOLE)

    def test_skill_files_use_tree_browser_and_editor_workspace(self) -> None:
        block = _function_block("skillEditor", "recDateValue")
        for marker in (
            'class="sk-workspace"',
            'id="skf-tree"',
            'id="skf-search"',
            'id="skf-content"',
            "function generatedSkillMarkdown()",
            'data-dir="${esc(path)}"',
            'data-file="${file.index}"',
            'source: agentmate',
        ):
            self.assertIn(marker, block)
        self.assertNotIn('id="skf-list"', block)
        self.assertNotIn('class="sk-file-form"', block)


if __name__ == "__main__":
    unittest.main()
