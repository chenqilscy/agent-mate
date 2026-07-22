"""WB-290 real-process HTTP contract: fake WeKnora ↔ Server ↔ backend pull."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

import httpx

ROOT = Path(__file__).resolve().parents[3]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _FakeWeKnora(BaseHTTPRequestHandler):
    kb_id = "provider-kb-private"
    doc_id = "provider-doc-private"
    docs: list[dict] = []

    def log_message(self, _format: str, *_args) -> None:
        return

    def _reply(self, data: object, status: int = 200) -> None:
        body = json.dumps({"success": status < 400, "data": data}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def _body(self) -> bytes:
        return self.rfile.read(int(self.headers.get("content-length", "0") or 0))

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._reply({"ok": True}); return
        if self.path == "/api/v1/models":
            self._reply([{"id": "embedding-1", "type": "embedding"}]); return
        if self.path == "/api/v1/system/info":
            self._reply({"version": "0.6.2"}); return
        if self.path.startswith(f"/api/v1/knowledge-bases/{self.kb_id}/knowledge"):
            self._reply({"data": list(self.docs), "total": len(self.docs)}); return
        self._reply({}, 404)

    def do_POST(self) -> None:  # noqa: N802
        raw = self._body()
        if self.path == "/api/v1/knowledge-bases":
            body = json.loads(raw or b"{}")
            if body.get("embedding_model_id") != "embedding-1":
                self._reply({}, 400); return
            self._reply({"id": self.kb_id, "name": body.get("name")}); return
        if self.path == f"/api/v1/knowledge-bases/{self.kb_id}/knowledge/file":
            if b"shared.md" not in raw or b"central knowledge" not in raw:
                self._reply({}, 400); return
            doc = {
                "id": self.doc_id, "file_name": "shared.md", "file_size": 17,
                "parse_status": "completed",
            }
            self.docs[:] = [doc]
            self._reply(doc); return
        if self.path == "/api/v1/knowledge-search":
            body = json.loads(raw or b"{}")
            if body.get("knowledge_base_ids") != [self.kb_id]:
                self._reply({}, 400); return
            self._reply([{
                "content": "central knowledge", "score": 0.99,
                "knowledge_filename": "shared.md", "knowledge_id": self.doc_id,
            }]); return
        self._reply({}, 404)

    def do_DELETE(self) -> None:  # noqa: N802
        if self.path == f"/api/v1/knowledge-bases/{self.kb_id}":
            self.docs.clear(); self._reply(None); return
        self._reply({}, 404)


class ProjectWeKnoraHttpTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.client = httpx.Client(timeout=15)
        self.provider = ThreadingHTTPServer(("127.0.0.1", 0), _FakeWeKnora)
        self.provider_thread = threading.Thread(target=self.provider.serve_forever, daemon=True)
        self.provider_thread.start()
        self.server_port = _free_port(); self.backend_port = _free_port()
        self.server = self._spawn(ROOT / "server", {
            "AGENTMATE_SERVER_DB": str(self.base / "server.db"),
            "AGENTMATE_SERVER_STORAGE": str(self.base / "server-storage"),
            "AGENTMATE_SERVER_HOST": "127.0.0.1", "AGENTMATE_SERVER_PORT": str(self.server_port),
            "AGENTMATE_SERVER_WEKNORA_URL": f"http://127.0.0.1:{self.provider.server_port}",
            "AGENTMATE_SERVER_WEKNORA_API_KEY": "server-only-secret",
            "AGENTMATE_SERVER_WEKNORA_EMBEDDING_MODEL_ID": "embedding-1",
        })
        self._wait(f"{self.server_url}/api/health")
        self.backend = self._spawn(ROOT / "backend", {
            "AGENTMATE_DB": str(self.base / "app.db"),
            "AGENTMATE_WORKSPACE": str(self.base / "workspace"),
            "AGENTMATE_SERVER_URL": self.server_url,
            "HOST": "127.0.0.1", "PORT": str(self.backend_port),
        })
        self._wait(f"{self.backend_url}/api/health")

    def tearDown(self) -> None:
        self.client.close(); self._stop(self.backend); self._stop(self.server)
        self.provider.shutdown(); self.provider.server_close(); self.provider_thread.join(timeout=3)
        time.sleep(0.2); self.tmp.cleanup()

    @property
    def server_url(self) -> str:
        return f"http://127.0.0.1:{self.server_port}"

    @property
    def backend_url(self) -> str:
        return f"http://127.0.0.1:{self.backend_port}"

    @staticmethod
    def _spawn(cwd: Path, values: dict[str, str]) -> subprocess.Popen[bytes]:
        env = os.environ.copy(); env.update(values)
        return subprocess.Popen(
            [sys.executable, "main.py"], cwd=cwd, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    @staticmethod
    def _stop(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()

    def _wait(self, url: str) -> None:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                if self.client.get(url, timeout=1).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        self.fail(f"health timeout: {url}")

    def _ok(self, response: httpx.Response) -> dict:
        self.assertEqual(200, response.status_code, response.text)
        data = response.json(); self.assertIsInstance(data, dict); return data

    def test_create_upload_search_and_backend_downlink(self) -> None:
        registered = self._ok(self.client.post(
            f"{self.server_url}/api/auth/register",
            json={"name": "wb290-owner", "password": "owner-pass-123"},
        ))
        headers = {"Authorization": f"Bearer {registered['token']}"}
        project = self._ok(self.client.post(
            f"{self.server_url}/api/projects", headers=headers, json={"name": "Central KB"},
        ))
        kb = self._ok(self.client.post(
            f"{self.server_url}/api/projects/{project['id']}/knowledge-bases",
            headers=headers, json={"name": "Team docs"},
        ))
        self.assertNotEqual(_FakeWeKnora.kb_id, kb["id"])
        self.assertNotIn("provider_id", kb)
        self.assertNotIn("server-only-secret", repr(kb))

        uploaded = self._ok(self.client.post(
            f"{self.server_url}/api/projects/{project['id']}/knowledge-bases/{kb['id']}/documents",
            headers={**headers, "Content-Type": "text/markdown"},
            params={"filename": "shared.md"}, content=b"central knowledge",
        ))
        self.assertEqual("completed", uploaded["parse_status"])
        searched = self._ok(self.client.post(
            f"{self.server_url}/api/projects/{project['id']}/knowledge-search",
            headers=headers, json={"query": "central", "knowledge_ids": [kb["id"]]},
        ))
        self.assertEqual("central knowledge", searched["hits"][0]["text"])

        login = self._ok(self.client.post(
            f"{self.backend_url}/api/auth/login",
            json={"name": "wb290-owner", "password": "owner-pass-123"},
        ))
        app_headers = {"Authorization": f"Bearer {login['token']}"}
        self._ok(self.client.post(f"{self.backend_url}/api/server/pull", headers=app_headers))
        mirrored = self._ok(self.client.get(
            f"{self.backend_url}/api/projects/{project['id']}", headers=app_headers,
        ))
        self.assertEqual([kb["id"]], mirrored["knowledge_ids"])


if __name__ == "__main__":
    unittest.main()
