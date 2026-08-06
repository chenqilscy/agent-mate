#!/usr/bin/env python3
"""Run V1 A-E journeys against temporary real Server and Backend processes."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "backend" / ".venv" / "Scripts" / "python.exe"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_health(url: str, process: subprocess.Popen[bytes], timeout: float = 30) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"service exited before health check: {url} (exit {process.returncode})")
        try:
            with urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return json.loads(response.read().decode("utf-8"))
        except (OSError, URLError, ValueError):
            pass
        time.sleep(0.2)
    raise RuntimeError(f"health timeout: {url}")


def stop_tree(process: subprocess.Popen[bytes] | None) -> None:
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
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def spawn(cwd: Path, env: dict[str, str]) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [str(PYTHON), "main.py"],
        cwd=cwd,
        env=env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def main() -> int:
    if not PYTHON.is_file():
        print(f"[BLOCKED] Project Python runtime is missing: {PYTHON}", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="agentmate-v1-live-") as temp_name:
        temp = Path(temp_name)
        server_port = free_port()
        backend_port = free_port()
        server_url = f"http://127.0.0.1:{server_port}"
        backend_api = f"http://127.0.0.1:{backend_port}/api"
        server: subprocess.Popen[bytes] | None = None
        backend: subprocess.Popen[bytes] | None = None
        try:
            server_env = os.environ.copy()
            server_env.update({
                "AGENTMATE_SERVER_DB": str(temp / "server.db"),
                "AGENTMATE_SERVER_STORAGE": str(temp / "server-storage"),
                "AGENTMATE_SERVER_HOST": "127.0.0.1",
                "AGENTMATE_SERVER_PORT": str(server_port),
                "AGENTMATE_SSO_REGISTRATION_POLICY": "open",
            })
            server = spawn(ROOT / "server", server_env)
            wait_health(f"{server_url}/api/health", server)

            app_db = temp / "app.db"
            workspace = temp / "workspace"
            backend_env = os.environ.copy()
            backend_env.update({
                "AGENTMATE_DB": str(app_db),
                "AGENTMATE_WORKSPACE": str(workspace),
                "AGENTMATE_SKILLS_DIR": str(temp / "skills"),
                "AGENTMATE_SERVER_URL": server_url,
                "HOST": "127.0.0.1",
                "PORT": str(backend_port),
            })
            backend = spawn(ROOT / "backend", backend_env)
            wait_health(f"{backend_api}/health", backend)

            test_env = backend_env.copy()
            test_env.update({
                "AGENTMATE_TEST_BASE": backend_api,
                "AGENTMATE_DB": str(app_db),
                "AGENTMATE_WORKSPACE": str(workspace),
            })
            print(f"[PASS] Isolated Server and Backend healthy; functional tests must provide owner-scoped model DB configuration; port={backend_port}")
            result = subprocess.run(
                [str(PYTHON), str(ROOT / "backend" / "tests" / "functional" / "run_all.py")],
                cwd=ROOT,
                env=test_env,
                check=False,
            )
            return result.returncode
        finally:
            stop_tree(backend)
            stop_tree(server)


if __name__ == "__main__":
    raise SystemExit(main())
