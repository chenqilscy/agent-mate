"""Build the backend sidecar and stage it for Tauri.

Runs PyInstaller (agentmate-backend.spec → dist/agentmate-backend.exe), then
copies it to ../src-tauri/binaries/agentmate-backend-<rust-target-triple>.exe —
the name Tauri's `bundle.externalBin` expects.

Run with the backend venv's python:
    backend/.venv/Scripts/python.exe backend/build_sidecar.py     # Windows
    backend/.venv/bin/python backend/build_sidecar.py             # macOS/Linux
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
ROOT = BACKEND.parent


def target_triple() -> str:
    out = subprocess.run(["rustc", "-vV"], capture_output=True, text=True, check=True).stdout
    for line in out.splitlines():
        if line.startswith("host:"):
            return line.split(":", 1)[1].strip()
    raise SystemExit("could not detect the rust target triple (is rustc installed?)")


def main() -> None:
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "agentmate-backend.spec",
         "--distpath", "dist", "--workpath", ".pyi-build", "--noconfirm"],
        cwd=BACKEND, check=True,
    )
    exe = "agentmate-backend.exe" if sys.platform == "win32" else "agentmate-backend"
    src = BACKEND / "dist" / exe
    dst_dir = ROOT / "src-tauri" / "binaries"
    dst_dir.mkdir(parents=True, exist_ok=True)
    suffix = ".exe" if sys.platform == "win32" else ""

    # Name the sidecar with the triple Tauri's bundler expects. On Windows Tauri
    # looks for the *msvc* triple even when the rust host toolchain is gnu (the
    # PyInstaller exe is toolchain-agnostic, so the triple is just a match label);
    # stage under both to be safe.
    triples = {target_triple()}
    if sys.platform == "win32":
        triples |= {"x86_64-pc-windows-msvc", "x86_64-pc-windows-gnu"}
    for triple in triples:
        dst = dst_dir / f"agentmate-backend-{triple}{suffix}"
        shutil.copy2(src, dst)
        print(f"sidecar staged → {dst}")


if __name__ == "__main__":
    main()
