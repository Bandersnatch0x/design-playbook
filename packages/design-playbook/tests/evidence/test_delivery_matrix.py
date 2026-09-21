#!/usr/bin/env python3
"""Stage 9 delivery-matrix capture tests.

Covers the five-viewport orchestrator in ``mcp/evidence/capture_runtime.py``:

- ``matrix_viewport`` maps a standard viewport name to a capture-contract
  viewport (Light scheme, DPR 1.0) and refuses unknown names.
- ``capture_delivery_matrix`` drives all five viewports through a BrowserAdapter
  seam and returns ``{metrics, screenshot}`` per viewport, computing
  ``inFold``/``hOverflow`` from an injected probe.
- metrics degrade to reference in-fold values when the adapter has no probe.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

# One import seam (ADR-0022): package root on sys.path once, then absolute
# design_playbook.* imports below. No per-runtime sys.path adapters.
_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.mcp.evidence.capture_runtime import (  # noqa: E402
    VIEWPORTS,
    capture_delivery_matrix,
    matrix_viewport,
)
from design_playbook.mcp.evidence.disclosure import LAYOUT_PROBE_JS  # noqa: E402


class _FakeMatrixAdapter:
    """BrowserAdapter with an injectable per-viewport probe."""

    def __init__(self, probe_values: dict[str, dict[str, Any]]) -> None:
        self.probe_values = probe_values
        self.captured: list[dict[str, Any]] = []

    def capture(self, **kwargs: Any) -> str:
        self.captured.append(kwargs)
        return "ok"


class _ProbingAdapter(_FakeMatrixAdapter):
    def __init__(
        self,
        probe_results: dict[str, dict[str, Any]],
        probe_js: str,
    ) -> None:
        super().__init__({})
        self.probe_results = probe_results
        self.probe_js = probe_js
        self.probe_calls: list[str] = []

    def probe(self, js: str, name: str) -> dict[str, Any]:
        self.probe_calls.append(js)
        # The orchestrator passes the viewport name explicitly so the probe
        # does not depend on capture-call ordering.
        if name in self.probe_results:
            return self.probe_results[name]
        ref = VIEWPORTS[name]
        return {
            "sw": ref["sw"],
            "innerH": ref["innerH"],
            "hOverflow": 0,
            "inFold": True,
        }

    def capture_and_probe(self, **kwargs: Any) -> dict[str, Any]:
        self.captured.append(kwargs)
        name = Path(kwargs["out_path"]).stem.removeprefix("viewport-")
        raw = self.probe(name=name, js=self.probe_js)
        from design_playbook.mcp.evidence.disclosure import probe_layout

        return {"observed_state": "ok", "metrics": probe_layout(lambda _js: raw)}


class MatrixViewportTests(unittest.TestCase):
    def test_maps_standard_viewports_to_contract_shape(self) -> None:
        vp = matrix_viewport("1280x900")
        self.assertEqual(
            vp,
            {
                "width": 1280,
                "height": 900,
                "devicePixelRatio": 1.0,
                "colorScheme": "light",
            },
        )
        self.assertEqual(matrix_viewport("print")["height"], 650)
        # print viewport emulates print media (spec §4.1); others do not carry it
        self.assertEqual(matrix_viewport("print")["media"], "print")
        self.assertNotIn("media", matrix_viewport("1280x900"))

    def test_unknown_viewport_raises(self) -> None:
        with self.assertRaises(ValueError):
            matrix_viewport("999x999")


class CaptureDeliveryMatrixTests(unittest.TestCase):
    def test_captures_all_five_viewports(self) -> None:
        adapter = _FakeMatrixAdapter({})
        with tempfile.TemporaryDirectory() as tmp:
            results = capture_delivery_matrix(
                url="about:blank",
                out_dir=Path(tmp),
                browser_adapter=adapter,
            )
            self.assertEqual(set(results), set(VIEWPORTS))
            self.assertEqual(len(adapter.captured), 5)
            for name in VIEWPORTS:
                self.assertTrue(
                    results[name]["screenshot"].endswith(f"viewport-{name}.png")
                )
            widths = {c["viewport"]["width"] for c in adapter.captured}
            self.assertEqual(widths, {1280, 768, 390, 360, 960})

    def test_probing_adapter_reports_measured_metrics(self) -> None:
        adapter = _ProbingAdapter(
            {"390x844": {"sw": 390, "innerH": 844, "hOverflow": 14, "inFold": False}},
            LAYOUT_PROBE_JS,
        )
        with tempfile.TemporaryDirectory() as tmp:
            results = capture_delivery_matrix(
                url="about:blank",
                out_dir=Path(tmp),
                browser_adapter=adapter,
            )
            self.assertEqual(results["390x844"]["metrics"]["hOverflow"], 14)
            self.assertFalse(results["390x844"]["metrics"]["disclosure"]["inFold"])
            # untouched viewports keep reference in-fold metrics (capture-side
            # fallback is the reference in-fold, not the disclosure unmeasured)
            self.assertTrue(results["1280x900"]["metrics"]["disclosure"]["inFold"])
            self.assertEqual(results["1280x900"]["metrics"]["sw"], 1280)
            # probe was driven with the shared LAYOUT_PROBE_JS
            self.assertEqual(adapter.probe_calls, [LAYOUT_PROBE_JS] * 5)

    def test_no_probe_falls_back_to_reference_metrics(self) -> None:
        adapter = _FakeMatrixAdapter({})
        with tempfile.TemporaryDirectory() as tmp:
            results = capture_delivery_matrix(
                url="about:blank",
                out_dir=Path(tmp),
                browser_adapter=adapter,
            )
            for name in VIEWPORTS:
                metrics = results[name]["metrics"]
                self.assertEqual(metrics["disclosure"]["inFold"], False, name)
                self.assertEqual(metrics["hOverflow"], 0, name)
                self.assertEqual(metrics["sw"], VIEWPORTS[name]["sw"], name)
                self.assertEqual(metrics["measurementStatus"], "unmeasured", name)


if __name__ == "__main__":
    unittest.main()
