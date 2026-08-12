from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class AppReleaseBuildContractTest(unittest.TestCase):
    def test_plan_events_require_the_server_protocol_version(self) -> None:
        types = (ROOT / "src" / "lib" / "types.ts").read_text(encoding="utf-8")
        sse = (ROOT / "src" / "lib" / "sse.ts").read_text(encoding="utf-8")
        plan = types.split("export interface RunPlanEvent", 1)[1].split("}", 1)[0]
        self.assertIn("version: number", plan)
        self.assertNotIn("version?: number", plan)
        self.assertIn("number('version') && Array.isArray(value.items)", sse)

    def test_workbench_requires_each_read_to_report_its_own_source(self) -> None:
        store = (ROOT / "src" / "stores" / "workbenchStore.ts").read_text(encoding="utf-8")
        self.assertIn("resolved.current = state", store)
        self.assertIn("if (!server) throw new Error", store)
        self.assertIn("server.state === 'cached'", store)


if __name__ == "__main__":
    unittest.main()
