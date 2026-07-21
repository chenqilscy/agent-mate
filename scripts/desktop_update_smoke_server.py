#!/usr/bin/env python3
"""Loopback-only Tauri updater server for signed desktop installation smoke tests."""
from __future__ import annotations

import argparse
import json
import shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18177)
    parser.add_argument("--version", required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--signature", type=Path, required=True)
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--bad-signature", action="store_true")
    args = parser.parse_args()

    artifact = args.artifact.resolve(strict=True)
    signature = args.signature.read_text(encoding="utf-8").strip()
    if args.bad_signature:
        signature = ("A" if signature[:1] != "A" else "B") + signature[1:]
    base_url = f"http://127.0.0.1:{args.port}"
    artifact_route = f"/artifacts/{artifact.name}"

    class Handler(BaseHTTPRequestHandler):
        server_version = "AgentMateUpdateSmoke/1.0"

        def log_message(self, fmt: str, *values: object) -> None:
            print(f"{self.address_string()} {fmt % values}", flush=True)

        def _json(self, status: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _handle(self) -> None:
            path = unquote(urlparse(self.path).path)
            if path == "/health":
                self._json(200, {"ok": True, "version": args.version, "rollback": args.rollback})
                return
            if path.startswith("/api/desktop-updates/"):
                current = path.rstrip("/").rsplit("/", 1)[-1]
                if current == args.version:
                    self.send_response(204)
                    self.end_headers()
                    return
                self._json(200, {
                    "version": args.version,
                    "notes": "WB-257 signed loopback installation smoke",
                    "pub_date": "2026-07-22T00:00:00Z",
                    "url": base_url + artifact_route,
                    "signature": signature,
                    "release_id": f"wb257-{args.version}",
                    "rollback": args.rollback,
                    "forced": False,
                })
                return
            if path == artifact_route:
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Length", str(artifact.stat().st_size))
                self.end_headers()
                if self.command != "HEAD":
                    with artifact.open("rb") as source:
                        shutil.copyfileobj(source, self.wfile, length=1024 * 1024)
                return
            self._json(404, {"detail": "not found"})

        do_GET = _handle
        do_HEAD = _handle

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(json.dumps({
        "ready": True,
        "endpoint": base_url,
        "version": args.version,
        "artifact": str(artifact),
        "rollback": args.rollback,
        "bad_signature": args.bad_signature,
    }), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
