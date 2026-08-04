"""System-browser golden G05 regression (WB-244)."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from agent import browser, security, tools  # noqa: E402
from agent.sandbox import use_root  # noqa: E402
from config import settings  # noqa: E402


class _Site(BaseHTTPRequestHandler):
    posts = 0

    def do_GET(self):  # noqa: N802
        if self.path == "/download":
            body = b"downloaded evidence"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Disposition", "attachment; filename=evidence.txt")
        elif self.path == "/echo":
            body = (self.headers.get("Cookie") or "no-cookie").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
        else:
            body = b"""<!doctype html><title>Golden Browser Form</title>
            <h1>Golden Browser Form</h1>
            <form method='post'><input id='name' name='name'><input id='upload' type='file'>
            <button id='submit' type='submit'>Submit</button></form>
            <a id='download' href='/download'>Download</a>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Set-Cookie", "golden=present; Path=/")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        type(self).posts += 1
        self.send_response(204)
        self.end_headers()

    def log_message(self, *_args):
        pass


class BrowserToolsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Site)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_workspace = settings.WORKSPACE_ROOT
        self.old_db = settings.DB_PATH
        settings.WORKSPACE_ROOT = Path(self.tmp.name) / "workspace"
        settings.DB_PATH = Path(self.tmp.name) / "data" / "agentmate.db"
        settings.DB_PATH.parent.mkdir(parents=True)
        settings.WORKSPACE_ROOT.mkdir(parents=True)
        use_root(settings.WORKSPACE_ROOT / "default")
        security.set_security_context("browser-owner-a")
        _Site.posts = 0

    def tearDown(self) -> None:
        settings.WORKSPACE_ROOT = self.old_workspace
        settings.DB_PATH = self.old_db
        self.tmp.cleanup()

    def test_public_policy_blocks_local_and_private_targets(self) -> None:
        for url in ("http://127.0.0.1/", "http://localhost/", "http://192.168.1.1/"):
            with self.assertRaises(browser.BrowserPolicyError):
                browser.validate_url(url)

    def test_profile_reuse_submit_block_screenshot_upload_and_download(self) -> None:
        upload = settings.WORKSPACE_ROOT / "default" / "upload.txt"
        upload.parent.mkdir(parents=True, exist_ok=True)
        upload.write_text("upload evidence", encoding="utf-8")
        with patch.object(browser, "_public_hostname", return_value=True):
            first = browser.navigate({"url": self.base + "/form", "screenshot_path": "page.png"})
            self.assertEqual("Golden Browser Form", first["title"])
            self.assertTrue((settings.WORKSPACE_ROOT / "default" / "page.png").is_file())
            self.assertEqual("screenshot", first["artifacts"][0]["kind"])
            self.assertFalse((settings.WORKSPACE_ROOT / ".browser-profiles").exists())
            self.assertTrue((settings.DB_PATH.parent / ".browser-profiles").is_dir())

            echo = browser.read({"url": self.base + "/echo"})
            self.assertIn("golden=present", echo["text"])

            blocked = browser.interact({"url": self.base + "/form", "actions": [
                {"type": "fill", "selector": "#name", "value": "AgentMate"},
                {"type": "upload", "selector": "#upload", "path": "upload.txt"},
                {"type": "click", "selector": "#submit"},
            ]})
            self.assertTrue(blocked["confirmation_required"])
            self.assertEqual(0, _Site.posts)
            self.assertEqual(["fill", "upload"], [item["type"] for item in blocked["performed"]])

            downloaded = browser.interact({"url": self.base + "/form", "actions": [
                {"type": "download", "selector": "#download", "path": "downloads/evidence.txt"},
            ]})
            self.assertFalse(downloaded["confirmation_required"])
            self.assertEqual("download", downloaded["artifacts"][0]["kind"])
            self.assertEqual(b"downloaded evidence", (settings.WORKSPACE_ROOT / "default" / "downloads/evidence.txt").read_bytes())

    def test_profiles_are_owner_isolated_and_plan_mode_is_read_only(self) -> None:
        with patch.object(browser, "_public_hostname", return_value=True):
            browser.navigate({"url": self.base + "/form"})
            security.set_security_context("browser-owner-b")
            echo = browser.read({"url": self.base + "/echo"})
            self.assertIn("no-cookie", echo["text"])
        plan_names = {
            tool.name for tool in tools.base_tools(plan=True) + tools.deferred_tools(plan=True)
        }
        self.assertTrue({"browser_navigate", "browser_read"} <= plan_names)
        self.assertNotIn("browser_interact", plan_names)


if __name__ == "__main__":
    unittest.main()
