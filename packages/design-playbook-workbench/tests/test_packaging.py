#!/usr/bin/env python3
"""R15 (packaging slice): the distribution is installable on its own.

The workbench must not require the development checkout, so the declared
distribution has to carry the runtime *and* the frozen web assets, and
the console-script target has to resolve. These checks read the real
``pyproject.toml`` and import the real modules rather than restating the
list, so a forgotten manifest entry fails here.
"""
from __future__ import annotations

import sys
import tomllib
import unittest
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))

from design_playbook_workbench import __main__ as entry  # noqa: E402
from design_playbook_workbench.security import (  # noqa: E402
    DEFAULT_BIND_HOST,
    LOOPBACK_BIND_HOSTS,
)
from design_playbook_workbench.ui import ROUTE_TO_FILE, UIResources  # noqa: E402


def _manifest() -> dict:
    return tomllib.loads((_PACKAGE_ROOT / "pyproject.toml").read_text("utf-8"))


class DistributionTest(unittest.TestCase):
    def test_declares_one_runtime_package_and_no_third_party_dependency(self) -> None:
        manifest = _manifest()
        self.assertEqual(
            manifest["tool"]["setuptools"]["packages"], ["design_playbook_workbench"]
        )
        self.assertEqual(manifest["project"]["dependencies"], [])
        self.assertGreaterEqual(
            tuple(int(part) for part in manifest["project"]["requires-python"].strip(">=").split(".")[:2]),
            (3, 12),
        )

    def test_console_script_target_resolves(self) -> None:
        manifest = _manifest()
        scripts = manifest["project"]["scripts"]
        self.assertEqual(
            scripts["design-playbook-workbench"],
            "design_playbook_workbench.__main__:main",
        )
        self.assertTrue(callable(entry.main))
        self.assertTrue(callable(entry.build_parser))

    def test_web_assets_are_shipped_and_frozen(self) -> None:
        manifest = _manifest()
        web_glob = manifest["tool"]["setuptools"]["package-data"][
            "design_playbook_workbench"
        ]
        self.assertIn("web/*", web_glob)
        directory = _PACKAGE_ROOT / "design_playbook_workbench" / "web"
        for name in set(ROUTE_TO_FILE.values()):
            self.assertTrue((directory / name).is_file(), name)
        resources = UIResources()
        for route in ROUTE_TO_FILE:
            resource = resources.lookup(route)
            self.assertIsNotNone(resource, route)
            self.assertTrue(resource.body)
            self.assertIn("frame-ancestors 'none'", resource.content_security_policy)
        self.assertIsNone(resources.lookup("/../session/session.json"))
        self.assertIsNone(resources.lookup("/app.js/extra"))

    def test_the_shell_has_no_remote_asset_or_storage_reference(self) -> None:
        html = (
            _PACKAGE_ROOT / "design_playbook_workbench" / "web" / "app.html"
        ).read_text("utf-8")
        for forbidden in ("http://", "https://", "//cdn", "localStorage", "sessionStorage"):
            self.assertNotIn(forbidden, html)
        script = (
            _PACKAGE_ROOT / "design_playbook_workbench" / "web" / "app.js"
        ).read_text("utf-8")
        for forbidden in ("localStorage", "sessionStorage", "document.cookie", "http://"):
            self.assertNotIn(forbidden, script)

    def test_cli_defaults_are_loopback_only(self) -> None:
        arguments = entry.build_parser().parse_args([])
        self.assertEqual(arguments.bind_host, DEFAULT_BIND_HOST)
        self.assertIn(arguments.bind_host, LOOPBACK_BIND_HOSTS)
        self.assertEqual(arguments.port, 0)
        with self.assertRaises(SystemExit):
            entry.build_parser().parse_args(["--bind-host", "0.0.0.0"])


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
