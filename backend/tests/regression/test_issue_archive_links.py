from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "archive_issues_under_test", ROOT / "scripts" / "archive_issues.py"
)
assert SPEC and SPEC.loader
archive_issues = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = archive_issues
SPEC.loader.exec_module(archive_issues)


class IssueArchiveLinkTest(unittest.TestCase):
    def test_relative_repository_links_are_rebased_for_archive_depth(self) -> None:
        source = ROOT / "docs" / "issues" / "WB-300-example.md"
        destination = ROOT / "docs" / "issues" / "archive" / "2026" / "WB-300-399.md"
        text = (
            "[source](../../src/lib/api.ts#L10) "
            "[design](../agentmate-实现方案.md) "
            "[issue](WB-299-example.md)"
        )

        rebased = archive_issues.rebase_relative_links(text, source, destination)

        self.assertIn("[source](../../../../src/lib/api.ts#L10)", rebased)
        self.assertIn("[design](../../../agentmate-实现方案.md)", rebased)
        self.assertIn("[issue](WB-299-example.md)", rebased)

    def test_record_metadata_upgrade_is_deterministic(self) -> None:
        record = (
            '<!-- issue-record:start {"id":"WB-001","number":1} -->\n'
            '<a id="wb-001"></a>\n'
            "<!-- issue-record:end WB-001 -->"
        )
        meta = {"id": "WB-001", "number": 1, "archive_format": 2}

        upgraded = archive_issues.replace_record_meta(record, meta)

        self.assertEqual(upgraded, archive_issues.replace_record_meta(upgraded, meta))
        self.assertIn('"archive_format":2', upgraded)


if __name__ == "__main__":
    unittest.main()
