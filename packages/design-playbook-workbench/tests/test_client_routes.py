"""Drift gate for the generated workbench client route table.

``design_playbook_workbench/client_routes.py`` is the single owner of the
paths the browser calls. ``scripts/generate_workbench_routes.py`` derives
``web/routes.js`` from it, so a rename that misses ``web/app.js`` turns this
file red instead of failing only in a browser test.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_PKG = Path(__file__).resolve().parents[1]
_ROOT = _PKG.parents[1]
_SRC = _PKG / "design_playbook_workbench"
_ARTIFACT = _SRC / "web" / "routes.js"
_GENERATOR = _ROOT / "scripts" / "generate_workbench_routes.py"
_APP_JS = _SRC / "web" / "app.js"
_APP_HTML = _SRC / "web" / "app.html"
_UI = _SRC / "ui.py"


class ClientRoutesDriftGate(unittest.TestCase):
    def test_regeneration_is_byte_identical_to_the_committed_artifact(self) -> None:
        committed = _ARTIFACT.read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            fresh_path = Path(tmp) / "routes.js"
            result = subprocess.run(
                [sys.executable, str(_GENERATOR), "--out", str(fresh_path)],
                capture_output=True, text=True, cwd=str(_ROOT),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            fresh = fresh_path.read_bytes()
        self.assertEqual(
            fresh, committed,
            "regenerated artifact drifted from the committed file; run "
            "scripts/generate_workbench_routes.py after changing the source")

    def test_the_artifact_carries_every_route_and_builder(self) -> None:
        sys.path.insert(0, str(_PKG))
        try:
            from design_playbook_workbench import client_routes
        finally:
            sys.path.pop(0)
        text = _ARTIFACT.read_text(encoding="utf-8")
        for name in ("API", "STATUS", "RESOLVE", "PROJECTS", "PROBE", "BACKUP", "SESSION"):
            with self.subTest(name=name):
                self.assertIn(f'{name}: "{getattr(client_routes, name)}"', text)
        for name, template in client_routes.BUILDERS:
            with self.subTest(builder=name):
                self.assertIn(f"    {name}: function (", text)
                # The path prefix before the first placeholder is literal.
                literal = template.split("{", 1)[0]
                self.assertIn(literal.rstrip("/").split("/")[-1], text)

    def test_the_client_keeps_no_route_literal_of_its_own(self) -> None:
        text = _APP_JS.read_text(encoding="utf-8")
        self.assertNotIn("/api/v1/", text)
        self.assertIn("window.DPBUI.workbenchRoutes", text)

    def test_the_shell_loads_the_table_ahead_of_the_client(self) -> None:
        html = _APP_HTML.read_text(encoding="utf-8")
        routes_at = html.find('src="/routes.js"')
        client_at = html.find('src="/app.js"')
        self.assertGreater(routes_at, -1, "routes script missing from the shell")
        self.assertGreater(client_at, routes_at,
                           "the routes table must load before the client")

    def test_the_shell_serves_the_generated_asset(self) -> None:
        text = _UI.read_text(encoding="utf-8")
        self.assertIn('"/routes.js": "routes.js"', text)
        self.assertIn('"routes.js": "text/javascript; charset=utf-8"', text)


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
