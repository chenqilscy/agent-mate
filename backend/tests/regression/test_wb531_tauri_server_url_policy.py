"""WB-531: Desktop reports CSP-incompatible HTTP Server URLs before fetch."""
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class TauriServerUrlPolicyTests(unittest.TestCase):
    def test_desktop_channel_requires_https_for_non_loopback_server(self) -> None:
        channels = (ROOT / "src" / "lib" / "channels.ts").read_text(encoding="utf-8")
        self.assertIn("parsed.protocol === 'http:'", channels)
        self.assertIn("hostname.toLowerCase() === 'localhost'", channels)
        self.assertIn("hostname === '127.0.0.1'", channels)
        self.assertIn("局域网或公网 Server 必须使用 HTTPS", channels)
        self.assertIn("return `${validateServerRoot(value)}/api`", channels)
        self.assertIn("return validateServerRoot(configured)", channels)

    def test_csp_does_not_expand_to_arbitrary_http_origins(self) -> None:
        config = json.loads((ROOT / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
        csp = config["app"]["security"]["csp"]
        connect_sources = csp.split("connect-src", 1)[1].split(";", 1)[0].split()
        self.assertIn("http://127.0.0.1:*", connect_sources)
        self.assertIn("http://localhost:*", connect_sources)
        self.assertNotIn("http:", connect_sources)


if __name__ == "__main__":
    unittest.main()
