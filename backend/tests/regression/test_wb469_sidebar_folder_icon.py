from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class SidebarFolderIconContractTest(unittest.TestCase):
    def test_folder_icon_is_imported_before_use(self) -> None:
        sidebar = (ROOT / "src" / "components" / "layout" / "Sidebar.tsx").read_text(
            encoding="utf-8"
        )
        self.assertIn("import { IcBell, IcCompass, IcFolder } from '../../lib/icons'", sidebar)
        self.assertIn("icon: <IcFolder />", sidebar)


if __name__ == "__main__":
    unittest.main()
