#!/usr/bin/env python3
"""Compile every Git-tracked Python source under backend/ and server/."""
from __future__ import annotations

from pathlib import Path
import py_compile
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    output = subprocess.check_output(
        ["git", "ls-files", "--cached", "-z", "--", "backend", "server"],
        cwd=ROOT,
    ).decode("utf-8")
    sources = [ROOT / item for item in output.split("\0") if item.endswith(".py")]
    if not sources:
        print("no tracked Python sources resolved", file=sys.stderr)
        return 1
    failures = 0
    for source in sources:
        try:
            py_compile.compile(str(source), doraise=True)
        except py_compile.PyCompileError as exc:
            failures += 1
            print(exc.msg, file=sys.stderr)
    print(f"compiled {len(sources)} tracked Python sources; failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
