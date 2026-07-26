"""WB-326 real Server + Backend HTTP acceptance for token logout."""
from __future__ import annotations

import os
from contextlib import closing
from pathlib import Path
import socket
import sqlite3
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


class TokenLifecycleHttpTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.server_port = _free_port()
        self.backend_port = _free_port()
        self.client = httpx.Client(timeout=12)
        self.server = self._spawn_server()
        self.backend = self._spawn_backend()

    def tearDown(self) -> None:
        self.client.close()
        self._stop(self.backend)
        self._stop(self.server)
        # Windows releases uvicorn/SQLite handles just after process-tree exit.
        for attempt in range(10):
            try:
                self.tmp.cleanup()
                break
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.2)

    @property
    def server_url(self) -> str:
        return f"http://127.0.0.1:{self.server_port}"

    @property
    def backend_url(self) -> str:
        return f"http://127.0.0.1:{self.backend_port}"

    def _spawn(self, cwd: Path, env: dict[str, str]) -> subprocess.Popen[bytes]:
        process = subprocess.Popen(
            [sys.executable, "main.py"],
            cwd=cwd,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return process

    def _spawn_server(self) -> subprocess.Popen[bytes]:
        env = os.environ.copy()
        env.update({
            "AGENTMATE_SERVER_DB": str(self.base / "server.db"),
            "AGENTMATE_SERVER_STORAGE": str(self.base / "server-storage"),
            "AGENTMATE_SERVER_HOST": "127.0.0.1",
            "AGENTMATE_SERVER_PORT": str(self.server_port),
        })
        process = self._spawn(ROOT / "server", env)
        self._wait_health(f"{self.server_url}/api/health")
        return process

    def _spawn_backend(self) -> subprocess.Popen[bytes]:
        env = os.environ.copy()
        env.update({
            "AGENTMATE_DB": str(self.base / "app.db"),
            "AGENTMATE_WORKSPACE": str(self.base / "workspace"),
            "AGENTMATE_SERVER_URL": self.server_url,
            "HOST": "127.0.0.1",
            "PORT": str(self.backend_port),
        })
        process = self._spawn(ROOT / "backend", env)
        self._wait_health(f"{self.backend_url}/api/health")
        return process

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
    def _stop(process: subprocess.Popen[bytes] | None) -> None:
        if process is None or process.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            process.terminate()
        process.wait(timeout=8)

    def test_backend_logout_revokes_server_token(self) -> None:
        register = self.client.post(
            f"{self.backend_url}/api/auth/register",
            json={"name": "wb326-user", "password": "password123"},
        )
        self.assertEqual(200, register.status_code, register.text)
        auth = register.json()
        self.assertGreater(auth["expires_at"], time.time())
        headers = {"Authorization": f"Bearer {auth['token']}"}

        self.assertEqual(
            200,
            self.client.get(f"{self.server_url}/api/auth/verify", headers=headers).status_code,
        )
        logout = self.client.post(f"{self.backend_url}/api/auth/logout", headers=headers)
        self.assertEqual(200, logout.status_code, logout.text)
        self.assertEqual(
            {"ok": True, "revoked_remote": True, "pending": False}, logout.json()
        )
        self.assertEqual(
            401,
            self.client.get(f"{self.server_url}/api/auth/verify", headers=headers).status_code,
        )
        me = self.client.get(f"{self.backend_url}/api/me", headers=headers)
        self.assertEqual(200, me.status_code, me.text)
        self.assertFalse(me.json()["authenticated"])

    def test_expired_server_token_is_rejected_and_removed(self) -> None:
        register = self.client.post(
            f"{self.server_url}/api/auth/register",
            json={"name": "wb326-expired", "password": "password123"},
        )
        self.assertEqual(200, register.status_code, register.text)
        token = register.json()["token"]
        with closing(sqlite3.connect(self.base / "server.db")) as conn:
            conn.execute(
                "UPDATE server_tokens SET expires_at=? WHERE token=?", (time.time() - 1, token)
            )
            conn.commit()
        headers = {"Authorization": f"Bearer {token}"}
        self.assertEqual(
            401,
            self.client.get(f"{self.server_url}/api/auth/verify", headers=headers).status_code,
        )
        with closing(sqlite3.connect(self.base / "server.db")) as conn:
            self.assertIsNone(conn.execute(
                "SELECT 1 FROM server_tokens WHERE token=?", (token,)
            ).fetchone())


if __name__ == "__main__":
    unittest.main()
