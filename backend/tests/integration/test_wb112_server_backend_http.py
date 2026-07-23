"""WB-112 isolated Server + Backend HTTP acceptance (real processes and requests)."""
from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest

import httpx


ROOT = Path(__file__).resolve().parents[3]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class Wb112ServerBackendHttpTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.server_port = _free_port()
        self.backend_port = _free_port()
        self.server: subprocess.Popen[bytes] | None = None
        self.backend: subprocess.Popen[bytes] | None = None
        self.client = httpx.Client(timeout=12)
        self._start_server()
        env = os.environ.copy()
        env.update({
            "AGENTMATE_DB": str(self.base / "app.db"),
            "AGENTMATE_WORKSPACE": str(self.base / "workspace"),
            "AGENTMATE_SERVER_URL": self.server_url,
            "AGENTMATE_SERVER_TIMELINE_UPLOAD": "1",
            "HOST": "127.0.0.1",
            "PORT": str(self.backend_port),
        })
        self.backend = self._spawn(ROOT / "backend", env)
        self._wait_health(f"{self.backend_url}/api/health")

    def tearDown(self) -> None:
        self.client.close()
        self._stop(self.backend)
        self._stop(self.server)
        time.sleep(0.2)  # Windows releases SQLite handles just after process-tree exit.
        self.tmp.cleanup()

    @property
    def server_url(self) -> str:
        return f"http://127.0.0.1:{self.server_port}"

    @property
    def backend_url(self) -> str:
        return f"http://127.0.0.1:{self.backend_port}"

    @staticmethod
    def _spawn(cwd: Path, env: dict[str, str]) -> subprocess.Popen[bytes]:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return subprocess.Popen(
            [sys.executable, "main.py"], cwd=cwd, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=flags,
        )

    @staticmethod
    def _stop(process: subprocess.Popen[bytes] | None) -> None:
        if process is None or process.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            )
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
            return
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def _start_server(self) -> None:
        env = os.environ.copy()
        env.update({
            "AGENTMATE_SERVER_DB": str(self.base / "server.db"),
            "AGENTMATE_SERVER_STORAGE": str(self.base / "server-storage"),
            "AGENTMATE_SERVER_HOST": "127.0.0.1",
            "AGENTMATE_SERVER_PORT": str(self.server_port),
        })
        self.server = self._spawn(ROOT / "server", env)
        self._wait_health(f"{self.server_url}/api/health")

    def _wait_health(self, url: str) -> None:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                if self.client.get(url, timeout=1).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        self.fail(f"health timeout: {url}")

    @staticmethod
    def _headers(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _ok(self, response: httpx.Response) -> dict:
        self.assertEqual(200, response.status_code, response.text)
        data = response.json()
        self.assertIsInstance(data, dict)
        return data

    def test_timeline_offline_cache_and_server_authority(self) -> None:
        owner = self._ok(self.client.post(
            f"{self.server_url}/api/auth/register",
            json={"name": "wb112-owner", "password": "owner-pass-123"},
        ))
        mate = self._ok(self.client.post(
            f"{self.server_url}/api/auth/register",
            json={"name": "wb112-mate", "password": "mate-pass-123"},
        ))
        owner_headers = self._headers(owner["token"])
        mate_headers = self._headers(mate["token"])
        project = self._ok(self.client.post(
            f"{self.server_url}/api/projects", headers=owner_headers,
            json={"name": "WB112 isolated", "instruction": "remote-v1"},
        ))
        project_id = project["id"]
        self._ok(self.client.post(
            f"{self.server_url}/api/projects/{project_id}/members", headers=owner_headers,
            json={"name": "wb112-mate", "role": "Member"},
        ))
        self._ok(self.client.post(
            f"{self.server_url}/api/projects/{project_id}/timeline", headers=mate_headers,
            json={"kind": "session", "title": "teammate real request", "summary": "", "ext_id": "mate-session-1"},
        ))

        login = self._ok(self.client.post(
            f"{self.backend_url}/api/auth/login",
            json={"name": "wb112-owner", "password": "owner-pass-123"},
        ))
        app_headers = self._headers(login["token"])
        first_pull = self._ok(self.client.post(f"{self.backend_url}/api/server/pull", headers=app_headers))
        self.assertEqual(1, first_pull["synced"])
        online = self._ok(self.client.get(
            f"{self.backend_url}/api/server/projects/{project_id}/timeline", headers=app_headers,
        ))
        self.assertTrue(online["reachable"])
        self.assertEqual("wb112-mate", online["events"][0]["actor_name"])

        self._stop(self.server)
        self.server = None
        offline_patch = self.client.patch(
            f"{self.backend_url}/api/projects/{project_id}", headers=app_headers,
            json={"instruction": "local-offline"},
        )
        self.assertEqual(503, offline_patch.status_code, offline_patch.text)
        self.assertIn("项目配置未保存", offline_patch.json()["detail"])
        offline = self._ok(self.client.get(
            f"{self.backend_url}/api/server/projects/{project_id}/timeline", headers=app_headers,
        ))
        self.assertTrue(offline["stale"])
        self.assertEqual(online["events"][0]["id"], offline["events"][0]["id"])

        self._start_server()
        remote = self._ok(self.client.patch(
            f"{self.server_url}/api/projects/{project_id}", headers=owner_headers,
            json={"instruction": "remote-concurrent"},
        ))
        self.assertEqual("remote-concurrent", remote["instruction"])
        second_pull = self._ok(self.client.post(f"{self.backend_url}/api/server/pull", headers=app_headers))
        app_project = self._ok(self.client.get(
            f"{self.backend_url}/api/projects/{project_id}", headers=app_headers,
        ))
        conflicts = self._ok(self.client.get(
            f"{self.backend_url}/api/server/projects/{project_id}/sync-conflicts", headers=app_headers,
        ))
        self.assertEqual("remote-concurrent", app_project["instruction"])
        self.assertEqual(0, conflicts["count"])
        self.assertEqual([], second_pull["conflicts"])


if __name__ == "__main__":
    unittest.main()
