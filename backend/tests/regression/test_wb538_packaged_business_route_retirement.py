"""WB-538: the packaged compatibility target is not a second business API."""
from __future__ import annotations

import unittest

import main


class PackagedBusinessRouteRetirementTest(unittest.TestCase):
    def test_packaged_target_excludes_retired_business_routes(self) -> None:
        routes = {getattr(route, "path", "") for route in main.compatibility_app.routes}
        for path in (
            "/api/projects",
            "/api/sessions",
            "/api/chat",
            "/api/automations",
            "/api/work-items",
            "/api/milestones",
            "/api/notifications",
            "/api/catalog",
            "/api/ideas",
            "/api/auth/login",
            "/docs",
            "/openapi.json",
        ):
            self.assertNotIn(path, routes, path)

    def test_explicit_local_development_keeps_full_compatibility_app(self) -> None:
        routes = {getattr(route, "path", "") for route in main.app.routes}
        for path in ("/api/projects", "/api/sessions", "/api/automations"):
            self.assertIn(path, routes, path)


if __name__ == "__main__":
    unittest.main()
