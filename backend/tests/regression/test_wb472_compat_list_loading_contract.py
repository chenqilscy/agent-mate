"""WB-472 CompatList loading-state DOM contract."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class CompatListLoadingContractTest(unittest.TestCase):
    def test_loading_is_consumed_and_not_forwarded_to_the_native_div(self) -> None:
        source = (ROOT / "src/components/ui/CompatList.tsx").read_text(encoding="utf-8")

        self.assertIn("'children' | 'loading'", source)
        self.assertIn("loading?: boolean", source)
        self.assertIn("loading = false", source)
        self.assertIn("<div {...rest} className={classes} aria-busy={loading || undefined}>", source)
        self.assertNotIn("<div {...rest} loading=", source)

    def test_empty_loading_state_is_visible_and_accessible(self) -> None:
        source = (ROOT / "src/components/ui/CompatList.tsx").read_text(encoding="utf-8")

        self.assertIn("loading && dataSource.length === 0", source)
        self.assertIn('role="status" aria-live="polite"', source)
        self.assertIn('<Spin size="small" /> <span>正在加载…</span>', source)


if __name__ == "__main__":
    unittest.main()
