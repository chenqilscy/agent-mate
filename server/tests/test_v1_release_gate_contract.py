from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class V1ReleaseGateContractTest(unittest.TestCase):
    def test_package_exposes_single_v1_gate(self) -> None:
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        command = package["scripts"]["validate:v1-rc"]
        self.assertIn("validate-v1-rc.ps1", command)
        self.assertIn("-NonInteractive", command)

    def test_gate_covers_required_engineering_lanes(self) -> None:
        gate = (ROOT / "scripts" / "validate-v1-rc.ps1").read_text(encoding="utf-8")
        for required in (
            "archive_issues.py --check",
            "App production build",
            "Console production build",
            "backend/tests/regression",
            "server/tests",
            "backend/tests/integration",
            "git ls-files --cached",
            "Untracked tests are excluded",
            "compile_tracked_python.py",
        ):
            self.assertIn(required, gate)

    def test_live_and_desktop_are_explicit_not_silent_skips(self) -> None:
        gate = (ROOT / "scripts" / "validate-v1-rc.ps1").read_text(encoding="utf-8")
        self.assertIn("llm_configured=false", gate)
        self.assertIn("[BLOCKED]", gate)
        self.assertGreaterEqual(gate.count("[NOT RUN]"), 2)
        self.assertIn("run_all.py", gate)
        self.assertIn("run_v1_live_isolated.py", gate)
        self.assertIn("cargo check", gate)

    def test_release_doc_names_scope_journeys_and_evidence_boundary(self) -> None:
        doc = (ROOT / "docs" / "agentmate-v1-release-candidate.md").read_text(encoding="utf-8")
        for required in (
            "local-first AI 执行工作台",
            "从需求到成果",
            "从工作项到验收",
            "从定时触发到通知",
            "WB-283",
            "WB-307",
            "NOT RUN",
            "3–5 名目标用户",
        ):
            self.assertIn(required, doc)


if __name__ == "__main__":
    unittest.main()
