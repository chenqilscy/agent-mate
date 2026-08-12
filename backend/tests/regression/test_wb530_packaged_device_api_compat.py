"""WB-530: packaged Desktop keeps retained device APIs until their IPC migration."""
from pathlib import Path
import unittest

import main


ROOT = Path(__file__).resolve().parents[3]


class PackagedDeviceApiCompatibilityTests(unittest.TestCase):
    def test_compatibility_app_contains_every_retained_device_route(self) -> None:
        routes = {getattr(route, "path", "") for route in main.compatibility_app.routes}
        for path in (
            "/api/settings/runtime",
            "/api/device-diagnostics",
            "/api/models",
            "/api/skills",
            "/api/connectors/local",
            "/api/local-agent/status",
        ):
            self.assertIn(path, routes, path)

    def test_packaged_sidecar_selects_compatibility_app_with_protected_ipc(self) -> None:
        rust = (ROOT / "src-tauri" / "src" / "lib.rs").read_text(encoding="utf-8")
        self.assertIn('["--ipc-token-stdin"]', rust)
        self.assertNotIn('["--local-agent-core", "--ipc-token-stdin"]', rust)
        backend = (ROOT / "backend" / "main.py").read_text(encoding="utf-8")
        self.assertIn("compatibility_app if compatibility_mode else app", backend)
        self.assertIn("local_agent_core.router", backend)


if __name__ == "__main__":
    unittest.main()
