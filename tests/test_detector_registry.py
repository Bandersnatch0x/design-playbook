"""T-144: machine-detector rules are either bound to a callable or downgraded.

Every implemented detector is pinned by a positive and a negative fixture in
the same run: the positive produces at least one finding, the negative — built
from values sitting exactly on the floors — produces none. The fixtures are
module constants so the run report can reproduce the same counts.
"""
from __future__ import annotations

import sys
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages" / "design-playbook"
if str(PKG / "scripts") not in sys.path:
    sys.path.insert(0, str(PKG / "scripts"))

# The registry resolves its detectors under its own module name, so importing
# it bare keeps the detector and this error class in one module tree.
import rules_registry  # noqa: E402  (standalone seam, same as validate.py)
from detectors._shared import DetectorInputError  # noqa: E402

REGISTRY_TEXT = (
    PKG / "skills" / "design-playbook" / "references" / "rules.md"
).read_text(encoding="utf-8")

CONTRAST_POSITIVE = {"appearances": [{"name": "light", "pairs": [
    {"label": "Muted body", "foreground": "#777777",
     "background": "#ffffff", "kind": "text", "fontSizePx": 16},
    {"label": "State icon", "foreground": "#c0c0c0",
     "background": "#ffffff", "kind": "nontext"},
]}]}
CONTRAST_NEGATIVE = {"appearances": [{"name": "light", "pairs": [
    {"label": "Just above floor", "foreground": "#767676",
     "background": "#ffffff", "kind": "text", "fontSizePx": 16},
    {"label": "Large text", "foreground": "#949494",
     "background": "#ffffff", "kind": "text", "fontSizePx": 24},
    {"label": "Large bold", "foreground": "#949494",
     "background": "#ffffff", "kind": "text", "fontSizePx": 19,
     "bold": True},
    {"label": "Control edge", "foreground": "#949494",
     "background": "#ffffff", "kind": "nontext"},
]}]}

HIT_TARGET_POSITIVE = {"viewports": [
    {"name": "desktop", "touchPrimary": False, "targets": [
        {"label": "Row menu", "widthPx": 20, "heightPx": 20}]},
    {"name": "mobile", "touchPrimary": True, "targets": [
        {"label": "Close", "widthPx": 40, "heightPx": 44}]},
]}
HIT_TARGET_NEGATIVE = {"viewports": [
    {"name": "desktop", "touchPrimary": False, "targets": [
        {"label": "Row menu", "widthPx": 24, "heightPx": 24},
        {"label": "Wide", "widthPx": 120, "heightPx": 24}]},
    {"name": "mobile", "touchPrimary": True, "targets": [
        {"label": "Close", "widthPx": 44, "heightPx": 44}]},
]}

TEXT_SIZE_POSITIVE = {
    "nodes": [
        {"label": "Caption", "fontSizePx": 10, "fontWeight": 400,
         "script": "latin"},
        {"label": "CJK body", "fontSizePx": 11, "fontWeight": 400,
         "script": "cjk"},
        {"label": "Thin", "fontSizePx": 15, "fontWeight": 300,
         "script": "latin"},
    ],
    "zoom": {"percent": 200, "clipped": [{"label": "Card title"}]},
}
TEXT_SIZE_NEGATIVE = {
    "nodes": [
        {"label": "Caption", "fontSizePx": 11, "fontWeight": 400,
         "script": "latin"},
        {"label": "CJK body", "fontSizePx": 12, "fontWeight": 400,
         "script": "cjk"},
        {"label": "Thin", "fontSizePx": 16, "fontWeight": 300,
         "script": "latin"},
    ],
    "zoom": {"percent": 200, "clipped": []},
}


class DetectorBindingTests(unittest.TestCase):
    def test_every_machine_detector_rule_is_enumerated(self) -> None:
        statuses = rules_registry.machine_detector_statuses(
            rules_registry.parse_registry(REGISTRY_TEXT)
        )
        self.assertEqual(
            [status["ruleId"] for status in statuses],
            ["A11Y-03", "A11Y-04", "A11Y-05", "CRAFT-11"],
        )
        by_id = {status["ruleId"]: status for status in statuses}
        for rule_id in ("A11Y-03", "A11Y-04", "A11Y-05"):
            self.assertTrue(by_id[rule_id]["implemented"], rule_id)
        self.assertFalse(by_id["CRAFT-11"]["implemented"])
        self.assertTrue(by_id["CRAFT-11"]["reason"])

    def test_bindings_point_at_machine_detector_rules(self) -> None:
        entries = rules_registry.parse_registry(REGISTRY_TEXT)
        self.assertEqual(rules_registry.validate_detector_bindings(entries), [])

    def test_the_package_seam_resolves_detectors_too(self) -> None:
        # gates import design_playbook.scripts.rules_registry; the detector
        # modules must resolve under that name as well as the standalone one.
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; sys.path.insert(0, sys.argv[1]); "
                "from design_playbook.scripts import rules_registry as r; "
                "print(r.run_detector('A11Y-04', "
                "{'viewports': [{'name': 'mobile', 'touchPrimary': True, "
                "'targets': [{'label': 'Save', 'widthPx': 20, "
                "'heightPx': 20}]}]}))",
                str(PKG),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("A11Y-04", result.stdout)

    def test_unimplemented_detector_refuses_to_run(self) -> None:
        with self.assertRaises(NotImplementedError):
            rules_registry.run_detector("CRAFT-11", {})

    def test_unbound_binding_requires_a_reason(self) -> None:
        with self.assertRaises(ValueError):
            rules_registry.DetectorBinding("A11Y-99")


class ContrastDetectorTests(unittest.TestCase):
    def test_positive_and_negative_fixtures(self) -> None:
        findings = rules_registry.run_detector("A11Y-03", CONTRAST_POSITIVE)
        self.assertEqual(len(findings), 2)
        self.assertEqual(findings[0]["ruleId"], "A11Y-03")
        self.assertEqual(findings[0]["evidence"]["appearance"], "light")
        self.assertEqual(
            rules_registry.run_detector("A11Y-03", CONTRAST_NEGATIVE), []
        )

    def test_broken_capture_fails_closed(self) -> None:
        with self.assertRaises(DetectorInputError):
            rules_registry.run_detector("A11Y-03", {"appearances": [
                {"name": "light", "pairs": [
                    {"label": "Body", "foreground": "red",
                     "background": "#ffffff", "kind": "text",
                     "fontSizePx": 16},
                ]},
            ]})


class HitTargetDetectorTests(unittest.TestCase):
    def test_positive_and_negative_fixtures(self) -> None:
        findings = rules_registry.run_detector("A11Y-04", HIT_TARGET_POSITIVE)
        self.assertEqual(len(findings), 2)
        self.assertEqual(findings[1]["evidence"]["viewport"], "mobile")
        self.assertEqual(
            rules_registry.run_detector("A11Y-04", HIT_TARGET_NEGATIVE), []
        )


class TextSizeDetectorTests(unittest.TestCase):
    def test_positive_and_negative_fixtures(self) -> None:
        self.assertEqual(
            len(rules_registry.run_detector("A11Y-05", TEXT_SIZE_POSITIVE)), 4
        )
        self.assertEqual(
            rules_registry.run_detector("A11Y-05", TEXT_SIZE_NEGATIVE), []
        )

    def test_missing_zoom_capture_fails_closed(self) -> None:
        with self.assertRaises(DetectorInputError):
            rules_registry.run_detector("A11Y-05", {"nodes": []})


if __name__ == "__main__":
    unittest.main()
