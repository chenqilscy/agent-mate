"""Workspace usage cache coverage (WB-275)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from routers import files  # noqa: E402


class FilesUsageCacheTest(unittest.TestCase):
    def setUp(self) -> None:
        files._usage_cache.clear()

    def tearDown(self) -> None:
        files._usage_cache.clear()

    def test_reuses_scan_until_explicit_invalidation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.txt").write_bytes(b"123")
            with patch.object(files, "_directory_usage", wraps=files._directory_usage) as scan:
                self.assertEqual(3, files._workspace_usage(root))
                self.assertEqual(3, files._workspace_usage(root))
                self.assertEqual(1, scan.call_count)
                (root / "b.txt").write_bytes(b"4567")
                self.assertEqual(3, files._workspace_usage(root))
                files._invalidate_usage(root)
                self.assertEqual(7, files._workspace_usage(root))
                self.assertEqual(2, scan.call_count)

    def test_cache_is_isolated_by_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_root, second_root = Path(first), Path(second)
            (first_root / "a").write_bytes(b"1")
            (second_root / "b").write_bytes(b"22")
            self.assertEqual(1, files._workspace_usage(first_root))
            self.assertEqual(2, files._workspace_usage(second_root))


if __name__ == "__main__":
    unittest.main()
