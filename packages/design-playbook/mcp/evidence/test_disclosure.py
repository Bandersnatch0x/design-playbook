#!/usr/bin/env python3
"""Disclosure-review contract tests for the Stage 9 static handoff.

Covers the ``mcp/evidence/disclosure.py`` surface (docs/specs/
2026-08-22-interactive-review-and-static-handoff-implementation-plan.md §4.2):

- ``VIEWPORTS`` / ``VIEWPORT_ORDER`` — the five standard delivery viewports in
  the canonical matrix order.
- ``build_disclosure`` — deterministic §4.2 payload: run identity, verdict,
  profile, authority, timestamp, decisions, five viewport metrics, gate count.
- ``probe_layout`` — the DOM probe maps Playwright-evaluate output to coerced
  ``ViewportMetrics`` (fail-closed on malformed hosts, no browser needed).
- ``LAYOUT_PROBE_JS`` — a static JS structure/syntax check on the probe.
- ``build_handoff_zip`` — the ``/export-zip`` package: disclosure credential +
  caller-supplied snapshot members, read only from the exact file list.
"""

from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

# One import seam (ADR-0022): package root on sys.path once, then absolute
# design_playbook.* imports below. No per-runtime sys.path adapters.
_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.mcp.evidence.disclosure import (  # noqa: E402
    FOLD_BASELINE,
    LAYOUT_PROBE_JS,
    VIEWPORT_ORDER,
    VIEWPORTS,
    ViewportMetrics,
    build_disclosure,
    build_handoff_zip,
    disclosure_json,
    probe_layout,
)

_DECISIONS = [
    {"id": "DD-01", "title": "发送前独立双向确认", "authority": "confirmed-user"},
    {"id": "DD-02", "title": "写清允许与禁止能力", "authority": "confirmed-user"},
]

_FULL_DISCLOSURE = dict(
    run_id="ws_syn_7F3A",
    verdict="Pass",
    profile="P2-Standard",
    authority="confirmed-user",
    timestamp="2042-06-01 09:30 +08:00",
    decisions=_DECISIONS,
    gates_passed=8,
)


class DisclosureMatrixTests(unittest.TestCase):
    """The five standard viewports and their canonical order."""

    def test_viewport_matrix_has_five_standard_entries(self) -> None:
        self.assertEqual(len(VIEWPORTS), 5)
        self.assertEqual(
            set(VIEWPORTS),
            {"1280x900", "768x1024", "390x844", "360x800", "print"},
        )

    def test_reference_metric_shapes(self) -> None:
        self.assertEqual(
            {v["sw"] for v in VIEWPORTS.values()},
            {1280, 768, 390, 360, 960},
        )
        self.assertEqual(VIEWPORTS["print"]["innerH"], 650)
        self.assertEqual(VIEWPORTS["1280x900"]["kind"], "desktop")

    def test_viewport_order_matches_spec_matrix(self) -> None:
        self.assertEqual(
            VIEWPORT_ORDER,
            ("1280x900", "768x1024", "390x844", "360x800", "print"),
        )

    def test_fold_baseline_is_900(self) -> None:
        self.assertEqual(FOLD_BASELINE, 900)


class BuildDisclosureTests(unittest.TestCase):
    """Deterministic §4.2 payload builder (pure, no browser)."""

    def test_full_payload_shape(self) -> None:
        payload = build_disclosure(**_FULL_DISCLOSURE)
        self.assertEqual(payload["runId"], "ws_syn_7F3A")
        self.assertEqual(payload["verdict"], "Pass")
        self.assertEqual(payload["profile"], "P2-Standard")
        self.assertEqual(payload["authority"], "confirmed-user")
        self.assertEqual(payload["timestamp"], "2042-06-01 09:30 +08:00")
        self.assertEqual(payload["gatesPassed"], 8)

    def test_five_viewports_present_in_order(self) -> None:
        payload = build_disclosure(**_FULL_DISCLOSURE)
        names = [v["name"] for v in payload["viewports"]]
        self.assertEqual(names, list(VIEWPORT_ORDER))
        for viewport in payload["viewports"]:
            self.assertIn("metrics", viewport)
            self.assertIn("disclosure", viewport["metrics"])

    def test_default_metrics_unmeasured_honest(self) -> None:
        # Unprobed viewports carry the reference sw/innerH but inFold=False /
        # hOverflow=0 so an unmeasured viewport is never mistaken for a passed
        # fold check (spec §4.2 honesty: the payload is complete but does not
        # fabricate a pass).
        payload = build_disclosure(**_FULL_DISCLOSURE)
        by_name = {v["name"]: v["metrics"] for v in payload["viewports"]}
        for name in VIEWPORT_ORDER:
            metrics = by_name[name]
            ref = VIEWPORTS[name]
            self.assertEqual(metrics["sw"], ref["sw"], name)
            self.assertEqual(metrics["innerH"], ref["innerH"], name)
            self.assertEqual(metrics["hOverflow"], 0, name)
            self.assertFalse(metrics["disclosure"]["inFold"], name)

    def test_measured_viewport_metrics_override_reference(self) -> None:
        measured = {
            "390x844": ViewportMetrics(sw=390, innerH=844, hOverflow=14, inFold=False),
            "360x800": ViewportMetrics(sw=360, innerH=800, hOverflow=22, inFold=False),
        }
        payload = build_disclosure(**_FULL_DISCLOSURE, viewport_metrics=measured)
        by_name = {v["name"]: v["metrics"] for v in payload["viewports"]}
        self.assertEqual(by_name["390x844"]["hOverflow"], 14)
        self.assertFalse(by_name["390x844"]["disclosure"]["inFold"])
        self.assertEqual(by_name["360x800"]["hOverflow"], 22)
        # untouched viewports keep the unmeasured reference (inFold=False)
        self.assertFalse(by_name["1280x900"]["disclosure"]["inFold"])

    def test_unknown_viewport_keys_are_ignored(self) -> None:
        measured = {
            "999x999": ViewportMetrics(sw=999, innerH=999, hOverflow=1, inFold=False)
        }
        payload = build_disclosure(**_FULL_DISCLOSURE, viewport_metrics=measured)
        self.assertEqual(len(payload["viewports"]), 5)

    def test_decisions_normalized(self) -> None:
        base = {k: v for k, v in _FULL_DISCLOSURE.items() if k != "decisions"}
        payload = build_disclosure(
            **base,
            decisions=[
                {"id": "DD-01", "title": "发送前独立双向确认"},
                "not-a-dict",  # dropped
                {"id": "DD-02", "title": "写清允许与禁止能力", "authority": "override"},
            ],
        )
        self.assertEqual(len(payload["decisions"]), 2)
        self.assertEqual(payload["decisions"][0]["authority"], "confirmed-user")
        self.assertEqual(payload["decisions"][1]["authority"], "override")

    def test_disclosure_json_round_trips(self) -> None:
        payload = build_disclosure(**_FULL_DISCLOSURE)
        text = disclosure_json(payload)
        self.assertTrue(text.endswith("\n"))
        self.assertEqual(json.loads(text), payload)

    def test_payload_is_deterministic(self) -> None:
        a = json.dumps(build_disclosure(**_FULL_DISCLOSURE), sort_keys=True)
        b = json.dumps(build_disclosure(**_FULL_DISCLOSURE), sort_keys=True)
        self.assertEqual(a, b)


class ProbeLayoutTests(unittest.TestCase):
    """The DOM probe maps evaluate output to coerced metrics (fail-closed)."""

    def _fake_evaluate(self, result: Any) -> Callable[[str], Any]:
        return lambda js: result

    def test_maps_measured_layout(self) -> None:
        metrics = probe_layout(
            self._fake_evaluate(
                {"sw": 390, "innerH": 844, "hOverflow": 14, "inFold": False}
            )
        )
        self.assertEqual(metrics.sw, 390)
        self.assertEqual(metrics.innerH, 844)
        self.assertEqual(metrics.hOverflow, 14)
        self.assertFalse(metrics.inFold)

    def test_non_dict_output_fails_closed(self) -> None:
        for bad in (None, "oops", 42, []):
            with self.subTest(bad=bad):
                metrics = probe_layout(self._fake_evaluate(bad))
                self.assertEqual(metrics.sw, 0)
                self.assertEqual(metrics.hOverflow, 0)
                self.assertFalse(metrics.inFold)
                self.assertEqual(metrics.measurement_status, "blocked")

    def test_non_numeric_or_negative_fields_fail_closed_to_zero(self) -> None:
        metrics = probe_layout(
            self._fake_evaluate(
                {
                    "sw": -5,
                    "innerH": True,
                    "hOverflow": "wide",
                    "inFold": "yes",
                }
            )
        )
        self.assertEqual(metrics.sw, 0)
        self.assertEqual(metrics.innerH, 0)
        self.assertEqual(metrics.hOverflow, 0)
        self.assertFalse(metrics.inFold)
        self.assertEqual(metrics.measurement_status, "blocked")
        self.assertIn("inFold is not boolean", metrics.measurement_error)

    def test_non_finite_numeric_fields_fail_closed(self) -> None:
        metrics = probe_layout(
            self._fake_evaluate(
                {
                    "sw": math.nan,
                    "innerH": math.inf,
                    "hOverflow": -math.inf,
                    "inFold": True,
                }
            )
        )
        self.assertEqual((metrics.sw, metrics.innerH, metrics.hOverflow), (0, 0, 0))
        self.assertTrue(metrics.inFold)
        self.assertEqual(metrics.measurement_status, "blocked")
        self.assertIn("sw is not finite", metrics.measurement_error)
        self.assertIn("innerH is not finite", metrics.measurement_error)
        self.assertIn("hOverflow is not finite", metrics.measurement_error)

    def test_zero_measured_dimensions_fail_closed(self) -> None:
        metrics = probe_layout(
            self._fake_evaluate(
                {"sw": 0, "innerH": 0, "hOverflow": 0, "inFold": False}
            )
        )
        self.assertEqual(metrics.measurement_status, "blocked")
        self.assertIn("sw is zero", metrics.measurement_error)
        self.assertIn("innerH is zero", metrics.measurement_error)

    def test_probe_js_is_single_iife_with_required_keys(self) -> None:
        self.assertIn("document.documentElement", LAYOUT_PROBE_JS)
        self.assertIn("scrollWidth", LAYOUT_PROBE_JS)
        self.assertIn("clientWidth", LAYOUT_PROBE_JS)
        for key in ("sw", "innerH", "hOverflow", "inFold"):
            self.assertIn(key, LAYOUT_PROBE_JS)
        # single arrow IIFE, no stray </script>
        self.assertTrue(LAYOUT_PROBE_JS.startswith("() => {"))
        self.assertTrue(LAYOUT_PROBE_JS.rstrip().endswith("}"))
        self.assertNotIn("</script>", LAYOUT_PROBE_JS)

    def test_probe_js_inlines_fold_baseline_no_python_refs(self) -> None:
        # The probe JS runs in a browser that has no Python bindings. A Python
        # constant name (e.g. FOLD_BASELINE) referenced by name would raise
        # ReferenceError and silently break the inFold probe under real
        # Playwright (the stub-backed tests would not catch it). The baseline
        # must be inlined as a numeric literal.
        self.assertNotIn("FOLD_BASELINE", LAYOUT_PROBE_JS)
        self.assertIn(str(FOLD_BASELINE), LAYOUT_PROBE_JS)


class BuildHandoffZipTests(unittest.TestCase):
    """The /export-zip packaging endpoint (exact file list, no crawling)."""

    def test_zip_contains_disclosure_and_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp) / "viewport-1280.png"
            snap.write_bytes(b"PNG-DATA")
            payload = build_disclosure(**_FULL_DISCLOSURE)
            zip_bytes, members = build_handoff_zip(
                payload,
                artifact_files={"snapshots/viewport-1280.png": str(snap)},
            )
            self.assertEqual(
                members,
                ["disclosure-review.json", "snapshots/viewport-1280.png"],
            )
            with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
                names = zf.namelist()
                self.assertIn("disclosure-review.json", names)
                self.assertIn("snapshots/viewport-1280.png", names)
                self.assertEqual(
                    json.loads(zf.read("disclosure-review.json").decode("utf-8")),
                    payload,
                )
                self.assertEqual(zf.read("snapshots/viewport-1280.png"), b"PNG-DATA")

    def test_zip_writes_to_target_when_given(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "handoff.zip"
            payload = build_disclosure(**_FULL_DISCLOSURE)
            zip_bytes, _ = build_handoff_zip(payload, zip_target=str(target))
            self.assertTrue(target.is_file())
            self.assertEqual(target.read_bytes(), zip_bytes)

    def test_empty_artifact_list_yields_disclosure_only(self) -> None:
        payload = build_disclosure(**_FULL_DISCLOSURE)
        zip_bytes, members = build_handoff_zip(payload)
        self.assertEqual(members, ["disclosure-review.json"])
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            self.assertEqual(zf.namelist(), ["disclosure-review.json"])


if __name__ == "__main__":
    unittest.main()
