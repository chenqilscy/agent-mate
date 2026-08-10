"""WB-440 component naming contract for Server, Local Agent and App."""
from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class LocalAgentNamingContractTest(unittest.TestCase):
    def test_desktop_sidecar_uses_local_agent_identity(self) -> None:
        tauri = json.loads(read("src-tauri/tauri.conf.json"))
        self.assertEqual(
            ["binaries/agentmate-local-agent"],
            tauri["bundle"]["externalBin"],
        )
        self.assertTrue((ROOT / "backend/agentmate-local-agent.spec").is_file())
        self.assertFalse((ROOT / "backend/agentmate-backend.spec").exists())

        build_script = read("backend/build_sidecar.py")
        rust_shell = read("src-tauri/src/lib.rs")
        install_check = read("scripts/validate-windows-tauri-install.ps1")
        sidecar_smoke = read("scripts/smoke-local-agent-sidecar.ps1")
        for content in (build_script, rust_shell, install_check, sidecar_smoke):
            self.assertIn("agentmate-local-agent", content)
            self.assertNotIn("agentmate-backend", content)
        self.assertIn("struct LocalAgentProcess", rust_shell)
        self.assertNotIn("struct Backend", rust_shell)

    def test_local_runtime_identifies_itself_as_local_agent(self) -> None:
        entrypoint = read("backend/main.py")
        self.assertIn('title="AgentMate Local Agent API"', entrypoint)
        self.assertIn("is not the AgentMate Server API", entrypoint)

        stack = read("run-stack.ps1")
        self.assertIn("Local Agent :8101", stack)
        self.assertIn("Server(API + Console)", stack)
        self.assertIn("App UI :8102", stack)
        self.assertNotIn("backend :8101", stack.lower())

        scripts = json.loads(read("package.json"))["scripts"]
        self.assertIn("dev:server", scripts)
        self.assertIn("dev:local-agent", scripts)
        self.assertIn("dev:app", scripts)

    def test_current_docs_do_not_use_backend_as_a_component_name(self) -> None:
        for relative in (
            "README.md",
            "docs/desktop-build.md",
            "docs/agentmate-server-first-架构设计.md",
            "docs/agentmate-数据分层与同步规范.md",
        ):
            content = read(relative)
            with self.subTest(path=relative):
                self.assertNotIn("App backend", content)
                self.assertNotIn("agentmate-backend", content)


if __name__ == "__main__":
    unittest.main()
