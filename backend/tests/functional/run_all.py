"""Run all detailed functional suites (A/B/C/D) in sequence against the LIVE
backend and print an aggregate verdict. Exit code = number of failing suites.

Usage (from anywhere):
    backend/.venv/Scripts/python.exe backend/tests/functional/run_all.py

Requires: backend running on :8101 with a real LLM configured in backend/.env.
Each suite creates a throwaway account and deletes all of its data at the end.
"""
import subprocess, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
SUITES = ["test_A_chat.py", "test_B_projects.py", "test_C_skills_connectors.py", "test_D_automation.py", "test_E_project_kb_system_settings.py"]

def main():
    results = []
    for s in SUITES:
        print(f"\n{'#' * 70}\n# {s}\n{'#' * 70}")
        rc = subprocess.run([sys.executable, os.path.join(HERE, s)]).returncode
        results.append((s, rc))
    print(f"\n{'=' * 70}\nAGGREGATE\n{'=' * 70}")
    failed = 0
    for s, rc in results:
        verdict = "PASS" if rc == 0 else ("SKIP (no LLM)" if rc == 2 else "FAIL")
        if rc == 1: failed += 1
        print(f"  {verdict:14} {s}")
    print(f"\n{failed} suite(s) failed.")
    return failed

if __name__ == "__main__":
    sys.exit(main())
