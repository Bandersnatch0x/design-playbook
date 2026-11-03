"""Drift gate for the generated Run Console client routes contract.

``mcp/run_console/client_routes.py`` is the single owner of the routes, action
names, and payload schema version the server and the client must agree on.
``scripts/generate_run_console_routes.py`` derives the browser copy, so a
rename that misses the client turns this file red instead of leaving only a
browser test to notice.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
_PKG = _ROOT / "packages" / "design-playbook"
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

_ARTIFACT = _PKG / "mcp" / "run_console" / "client_routes.js"
_SOURCE = _PKG / "mcp" / "run_console" / "client_routes.py"
_GENERATOR = _ROOT / "scripts" / "generate_run_console_routes.py"
_APP_JS = _PKG / "mcp" / "run_console" / "app.js"
_APP_HTML = _PKG / "mcp" / "run_console" / "app.html"
_UI = _PKG / "mcp" / "run_console" / "ui.py"


def _load_routes():
    spec = importlib.util.spec_from_file_location("run_console_client_routes", _SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ClientRoutesDriftGate(unittest.TestCase):
    def test_regeneration_is_byte_identical_to_the_committed_artifact(self) -> None:
        committed = _ARTIFACT.read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            fresh_path = Path(tmp) / "client_routes.js"
            result = subprocess.run(
                [sys.executable, str(_GENERATOR), "--out", str(fresh_path)],
                capture_output=True, text=True, cwd=str(_ROOT),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            fresh = fresh_path.read_bytes()
        self.assertEqual(
            fresh, committed,
            "regenerated artifact drifted from the committed file; run "
            "scripts/generate_run_console_routes.py after changing the source")

    def test_the_artifact_carries_every_route_and_action(self) -> None:
        routes = _load_routes()
        text = _ARTIFACT.read_text(encoding="utf-8")
        for fact in (
            routes.SNAPSHOT_ROUTE,
            routes.SOURCES_PREFIX,
            routes.REFRESH_ROUTE,
            routes.EXPORT_PREVIEW_ROUTE,
            routes.EXPORT_WRITE_ROUTE,
            routes.ACTION_REFRESH,
            routes.ACTION_EXPORT_PREVIEW,
            routes.ACTION_EXPORT_WRITE,
        ):
            with self.subTest(fact=fact):
                self.assertIn(fact, text)
        self.assertIn(f"SCHEMA_VERSION: {routes.SCHEMA_VERSION},", text)

    def test_the_client_reads_the_contract_and_does_not_reliteralize_it(self) -> None:
        text = _APP_JS.read_text(encoding="utf-8")
        for literal in (
            '"/api/v1/snapshot"',
            '"/api/v1/sources/"',
            '"/api/v1/actions/refresh"',
            '"/api/v1/actions/diagnostic-export/preview"',
            '"/api/v1/actions/diagnostic-export/write"',
            'action: "refresh"',
            'action: "diagnostic-export-preview"',
            'action: "diagnostic-export-write"',
            "schemaVersion: 1",
        ):
            with self.subTest(literal=literal):
                self.assertNotIn(literal, text)
        self.assertIn("DPBUI.runConsoleRoutes", text)
        for fact in (
            "ROUTES.SNAPSHOT",
            "ROUTES.SOURCES_PREFIX",
            "ROUTES.REFRESH.path",
            "ROUTES.EXPORT_PREVIEW.path",
            "ROUTES.EXPORT_WRITE.path",
        ):
            with self.subTest(fact=fact):
                self.assertIn(fact, text)

    def test_the_shell_loads_the_routes_ahead_of_the_client(self) -> None:
        html = _APP_HTML.read_text(encoding="utf-8")
        routes_at = html.find('src="client_routes.js"')
        client_at = html.find('src="app.js"')
        self.assertGreater(routes_at, -1, "routes script missing from the shell")
        self.assertGreater(client_at, routes_at,
                           "the routes must load before the client that reads it")

    def test_the_shell_serves_the_generated_asset(self) -> None:
        text = _UI.read_text(encoding="utf-8")
        self.assertIn('"/client_routes.js": "client_routes.js"', text)
        self.assertIn(
            '"client_routes.js": "text/javascript; charset=utf-8"', text)


if __name__ == "__main__":
    unittest.main()
