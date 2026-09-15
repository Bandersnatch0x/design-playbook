#!/usr/bin/env python3
"""page-probe/v1 defect parser and JS contract tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.mcp.evidence.disclosure import (  # noqa: E402
    WEB_VIEWPORTS,
    VIEWPORT_ORDER,
)
from design_playbook.mcp.evidence.page_defects import (  # noqa: E402
    DEFECT_PROBE_JS,
    LEAK_KINDS,
    TAP_MIN_PX,
    probe_defects,
)


class WebViewportTests(unittest.TestCase):
    def test_web_viewports_drop_print_keep_order(self) -> None:
        self.assertEqual(
            WEB_VIEWPORTS,
            ("1280x900", "768x1024", "390x844", "360x800"),
        )
        self.assertIn("print", VIEWPORT_ORDER)
        self.assertNotIn("print", WEB_VIEWPORTS)


class DefectProbeJsTests(unittest.TestCase):
    def test_iife_inlines_tap_min_and_leak_needles(self) -> None:
        self.assertTrue(DEFECT_PROBE_JS.startswith("() => {"))
        self.assertTrue(DEFECT_PROBE_JS.rstrip().endswith("}"))
        self.assertNotIn("</script>", DEFECT_PROBE_JS)
        self.assertIn(str(TAP_MIN_PX), DEFECT_PROBE_JS)
        self.assertNotIn("TAP_MIN_PX", DEFECT_PROBE_JS)
        for kind in LEAK_KINDS:
            self.assertIn(kind, DEFECT_PROBE_JS)


class ProbeDefectsTests(unittest.TestCase):
    def test_maps_leaks_and_tap_fails(self) -> None:
        facts = probe_defects(
            lambda _js: {
                "leaks": [{"kind": "undefined", "text": "undefined"}],
                "tapFails": [{"tag": "button", "width": 10, "height": 10}],
            }
        )
        self.assertEqual(facts.measurement_status, "measured")
        self.assertEqual(facts.leaks, ({"kind": "undefined", "text": "undefined"},))
        self.assertEqual(
            facts.tap_fails, ({"tag": "button", "width": 10, "height": 10},)
        )

    def test_non_object_fails_closed(self) -> None:
        facts = probe_defects(lambda _js: None)
        self.assertEqual(facts.measurement_status, "blocked")
        self.assertEqual(facts.leaks, ())
        self.assertEqual(facts.tap_fails, ())

    def test_evaluate_error_fails_closed(self) -> None:
        def boom(_js: str) -> object:
            raise RuntimeError("evaluate failed")

        facts = probe_defects(boom)
        self.assertEqual(facts.measurement_status, "blocked")
        self.assertIn("evaluate failed", facts.measurement_error)


if __name__ == "__main__":
    unittest.main()
