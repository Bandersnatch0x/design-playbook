#!/usr/bin/env python3
"""Stage 9 static-handoff builder tests (ADR-0034).

``mcp/evidence/handoff.py`` builds the delivery credential from durable run
artifacts with a lifecycle independent of any review round. These tests pin
the three boundaries the ADR fixed:

- ownership/lifecycle - the builder needs no review server, no browser, no
  port; everything lands under the run tree;
- confirmation authority - ``confirmed`` comes from the durable
  ``confirm-round-*.json`` (ADR-0013/0008), never from a choice label;
- capture target + honest conditionality - the matrix photographs the
  deliverable itself, and a conditional gate whose precondition never
  occurred reports ``not-applicable`` instead of silently passing.
"""
from __future__ import annotations

import json
import sys
import unittest
import zipfile
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.mcp.evidence import handoff  # noqa: E402

VIEWPORTS = ("1280x900", "768x1024", "390x844", "360x800", "print")
DELIVERABLE_HTML = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>deliverable</title></head><body><main><h1>Deliverable</h1></main></body></html>"""


def _fake_capture_runner(*, url: str, out_dir: Path) -> dict[str, dict[str, Any]]:
    """Write real non-empty snapshots for all five viewports."""
    out_dir.mkdir(parents=True, exist_ok=True)
    refs = {
        "1280x900": (1280, 900),
        "768x1024": (768, 1024),
        "390x844": (390, 844),
        "360x800": (360, 800),
        "print": (960, 650),
    }
    matrix: dict[str, dict[str, Any]] = {}
    for name, (sw, inner_h) in refs.items():
        screenshot = out_dir / f"viewport-{name}.png"
        screenshot.write_bytes(b"\x89PNG fake-bytes")
        matrix[name] = {
            "metrics": {
                "sw": sw,
                "innerH": inner_h,
                "hOverflow": 0,
                "disclosure": {"inFold": True},
                "measurementStatus": "measured",
            },
            "screenshot": str(screenshot.resolve()),
        }
    matrix["_url"] = {"url": url}  # type: ignore[assignment]
    return matrix


def _recording_capture_runner(seen: dict[str, str]):
    def runner(*, url: str, out_dir: Path) -> dict[str, dict[str, Any]]:
        seen["url"] = url
        return _fake_capture_runner(url=url, out_dir=out_dir)

    return runner


def _clean_capture_matrix() -> dict[str, dict[str, Any]]:
    return {
        name: {
            "metrics": {
                "sw": 1280,
                "innerH": 900,
                "hOverflow": 0,
                "disclosure": {"inFold": True},
                "measurementStatus": "measured",
            },
            "screenshot": "unused",
        }
        for name in VIEWPORTS
    }


def _passing_gate_runner(run_root: Path) -> dict[str, Any]:
    del run_root
    return {"available": True, "gates_passed": 8, "errors": []}


def _make_run(tmp: Path, *, with_confirm: bool = True) -> Path:
    """Lay down a minimal but honest run directory."""
    run_root = tmp / "run"
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "spec.md").write_text("# spec\n", encoding="utf-8")
    (run_root / "point-back.md").write_text("# point-back\n", encoding="utf-8")
    # Canonical run-profile shape (scripts/run_profile.py): an HTML marker,
    # then a fenced block with flat ``tier:`` / ``confirmed_by:`` lines.
    (run_root / "plan.md").write_text(
        "<!-- run-profile: v1 -->\n\n```yaml\ntier: P1\n"
        "confirmed_by: user + 2026-08-24T00:00:00Z\n```\n",
        encoding="utf-8",
    )
    preview = run_root / "preview"
    preview.mkdir(exist_ok=True)
    (preview / "round-1.html").write_text(DELIVERABLE_HTML, encoding="utf-8")
    (preview / "log.md").write_text("## round 1\n", encoding="utf-8")
    entry = {
        "schema_version": 1,
        "decision_id": "dd-0001",
        "binding": {
            "round": 1,
            "prototype_html_hash": "0" * 16,
            "report_ref": "r.md",
            "summary": "s",
            "options": ["确认通过"],
            "digest": "x",
        },
        "outcome": {
            "choice": "确认通过",
            "feedback": "ship it",
            "confirmed": True,
            "floor_pass": True,
        },
        "timestamp": "2026-08-24 00:00:00 +0000",
    }
    (preview / "decision-round-1.json").write_text(
        json.dumps(entry, ensure_ascii=False), encoding="utf-8"
    )
    if with_confirm:
        record = {
            "round": 1,
            "report_ref": "r.md",
            "confirmed": True,
            "floor_pass": True,
            "selected_options": ["确认通过"],
            "feedback": "ship it",
            "timestamp": "2026-08-24 00:00:00 +0000",
            "prototype_path": "preview/round-1.html",
            "prototype_html_hash": "0" * 16,
            "decision_id": "dd-0001",
        }
        (preview / "confirm-round-1.json").write_text(
            json.dumps(record, ensure_ascii=False), encoding="utf-8"
        )
    return run_root


class BuildStaticHandoffTests(unittest.TestCase):
    def _build(
        self,
        tmp: Path,
        run_root: Path,
        *,
        capture_runner=None,
        gate_runner=None,
    ):
        deliverable = tmp / "filled-ui.html"
        deliverable.write_text(DELIVERABLE_HTML, encoding="utf-8")
        return handoff.build_static_handoff(
            run_root,
            deliverable,
            round_n=1,
            summary="handoff summary",
            capture_runner=capture_runner or _fake_capture_runner,
            gate_runner=gate_runner or _passing_gate_runner,
        )

    def test_build_writes_the_full_artifact_set_under_the_run_tree(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            run_root = _make_run(tmp)
            result = self._build(tmp, run_root)
            base = run_root / "evidence" / "static-handoff"
            self.assertEqual(result.out_dir, base)
            for path in (result.json_path, result.zip_path, result.index_html):
                self.assertTrue(path.is_file(), path)
            self.assertTrue((base / "snapshots" / "viewport-1280x900.png").is_file())
            # nothing outside the run tree
            self.assertFalse((tmp / "output").exists())

    def test_zip_packages_credential_snapshots_and_deliverable_source(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            run_root = _make_run(tmp)
            result = self._build(tmp, run_root)
            with zipfile.ZipFile(result.zip_path) as zf:
                names = zf.namelist()
            self.assertIn("disclosure-review.json", names)
            self.assertIn("deliverable.html", names)
            for vp in VIEWPORTS:
                self.assertIn(f"snapshots/viewport-{vp}.png", names)
            zipped = json.loads(
                zipfile.ZipFile(result.zip_path).read("disclosure-review.json")
            )
            self.assertEqual(zipped, result.payload)

    def test_capture_targets_the_deliverable_not_review_chrome(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            run_root = _make_run(tmp)
            deliverable = tmp / "filled-ui.html"
            deliverable.write_text(DELIVERABLE_HTML, encoding="utf-8")
            seen: dict[str, str] = {}
            handoff.build_static_handoff(
                run_root,
                deliverable,
                round_n=1,
                summary="s",
                capture_runner=_recording_capture_runner(seen),
                gate_runner=_passing_gate_runner,
            )
            self.assertEqual(
                seen["url"], deliverable.resolve().as_uri(),
                "ADR-0034 §4: the matrix must photograph the deliverable itself",
            )

    def test_confirmed_record_drives_the_verdict(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            run_root = _make_run(tmp)
            result = self._build(tmp, run_root)
            payload = result.payload
            self.assertEqual(payload["authority"], "confirmed-user")
            self.assertEqual(payload["confirmationSource"], "confirm-record")
            self.assertEqual(payload["verdict"], "Pass")
            self.assertEqual(payload["profile"], "P1")
            self.assertEqual(
                [d["id"] for d in payload["decisions"]],
                ["DD-R1-01", "DD-R1-02"],
            )

    def test_floor_failing_record_is_never_confirmed(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            run_root = _make_run(tmp)
            record = json.loads(
                (run_root / "preview" / "confirm-round-1.json").read_text("utf-8")
            )
            # ADR-0008 floor failure recorded by transaction.py
            record["confirmed"] = False
            record["floor_pass"] = False
            (run_root / "preview" / "confirm-round-1.json").write_text(
                json.dumps(record), encoding="utf-8"
            )
            result = self._build(tmp, run_root)
            payload = result.payload
            # gatesPassed counts gates evaluated and passed, independent of
            # confirmation (ADR-0034 §7); confirmation semantics live here:
            self.assertNotEqual(payload["authority"], "confirmed-user")
            self.assertNotEqual(payload["verdict"], "Pass")
            self.assertEqual(payload["confirmationSource"], "unsubstantiated")

    def test_missing_confirm_record_leaves_the_credential_pending(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            run_root = _make_run(tmp, with_confirm=False)
            result = self._build(tmp, run_root)
            payload = result.payload
            self.assertEqual(payload["verdict"], "Pending")
            self.assertEqual(payload["confirmationSource"], "unsubstantiated")
            self.assertIn("no confirm record", payload["confirmationNote"])

    def test_conditional_gates_without_preconditions_are_not_applicable(self) -> None:
        """#89: "not triggered" is not "passed" (ADR-0034 §7)."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            run_root = _make_run(tmp, with_confirm=False)
            # Strip the conditional-gate preconditions: no preview round
            # artifacts, no evidence/, no craft-guard.md.
            import shutil

            shutil.rmtree(run_root / "preview")
            (run_root / "preview").mkdir()  # keep dir for decision fallback
            result = self._build(tmp, run_root)
            statuses = result.payload["gateStatuses"]
            self.assertEqual(
                statuses[:4], ["pass"] * 4, "G1-G4 are unconditional"
            )
            self.assertEqual(
                statuses[4:], ["not-applicable"] * 4,
                "G5/G6/G7/G8 preconditions never occurred",
            )
            self.assertEqual(result.payload["gatesPassed"], 4)

    def test_conditional_gate_with_precondition_still_counts(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            run_root = _make_run(tmp, with_confirm=False)
            # preview/ exists with round artifacts -> G5 precondition present
            result = self._build(tmp, run_root)
            statuses = result.payload["gateStatuses"]
            self.assertEqual(statuses[4], "pass", "G5 precondition present")

    def test_incomplete_capture_blocks_the_verdict(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            run_root = _make_run(tmp)

            def broken_runner(*, url: str, out_dir: Path):
                del url
                matrix = _fake_capture_runner(url="x", out_dir=out_dir)
                matrix["390x844"]["metrics"]["sw"] = 0  # zero measured dim
                return matrix

            result = self._build(tmp, run_root, capture_runner=broken_runner)
            payload = result.payload
            self.assertEqual(payload["captureStatus"], "blocked")
            self.assertNotEqual(payload["verdict"], "Pass")
            self.assertIn("390x844", payload["captureError"])

    def test_capture_runner_failure_is_disclosed_not_swallowed(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            run_root = _make_run(tmp)

            def raising_runner(*, url: str, out_dir: Path):
                del url, out_dir
                raise RuntimeError("chromium exploded")

            result = self._build(tmp, run_root, capture_runner=raising_runner)
            self.assertEqual(result.payload["captureStatus"], "blocked")
            self.assertIn("chromium exploded", result.payload["captureError"])
            self.assertNotEqual(result.payload["verdict"], "Pass")

    def test_missing_gate_inputs_leave_gates_unavailable(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            run_root = _make_run(tmp)
            (run_root / "spec.md").unlink()
            # Real validator: the injected fake runner ignores run_root and
            # cannot observe the missing gate input. Fail-closed is the
            # behavior under test.
            result = self._build(
                tmp, run_root, gate_runner=handoff._run_gate_validation
            )
            payload = result.payload
            self.assertEqual(payload["gateStatuses"], ["pending"] * 8)
            self.assertIn("gate input is missing", payload["gateError"])

    def test_undeclared_tier_is_unknown_not_guessed(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            run_root = _make_run(tmp)
            (run_root / "plan.md").unlink()
            result = self._build(tmp, run_root)
            self.assertEqual(result.payload["profile"], "unknown")


class HandoffPageTests(unittest.TestCase):
    def test_page_template_is_own_content_with_no_cdn(self) -> None:
        """ADR-0034 §6: the delivery page ships CDN-free inside the package."""
        template = (
            Path(handoff.__file__).with_name("static_handoff_page.html")
            .read_text(encoding="utf-8")
        )
        for banned in ("cdn.tailwindcss", "googleapis", "unpkg", "jsdelivr",
                       "https://", "http://"):
            self.assertNotIn(banned, template, f"CDN/remote ref: {banned}")

    def test_rendered_page_consumes_every_marker(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            run_root = _make_run(tmp)
            deliverable = tmp / "filled-ui.html"
            deliverable.write_text(DELIVERABLE_HTML, encoding="utf-8")
            result = handoff.build_static_handoff(
                run_root, deliverable, round_n=1, summary="s",
                capture_runner=_fake_capture_runner,
                gate_runner=_passing_gate_runner,
            )
            html = result.index_html.read_text(encoding="utf-8")
            self.assertNotIn("%", html.replace("100%", ""))
            self.assertIn(result.payload["runId"], html)
            self.assertIn("static-handoff.zip", html)
            self.assertIn("deliverable.html", html)
            # The payload must round-trip out of the embedded JSON block.
            start = html.index('<script type="application/json">') + len(
                '<script type="application/json">'
            )
            end = html.index("</script>", start)
            embedded = json.loads(html[start:end])
            self.assertEqual(embedded, result.payload)
            # No unsanitized injection from run-controlled text.
            self.assertNotIn("<script>", html[start:end])


class GateNormalizationTests(unittest.TestCase):
    """Ported from the review-session surface; the logic now lives in handoff."""

    def test_noncanonical_error_cannot_claim_eight_passes(self) -> None:
        raw = {
            "available": True,
            "gates_passed": 8,
            "errors": [
                {"rule_id": "G2.1", "message": "x"},
                {"rule_id": "OPERATIONAL.9", "message": "unscoped"},
            ],
        }
        result = handoff._normalise_gate_result(raw)
        self.assertTrue(result["available"])
        self.assertEqual(result["gate_statuses"][1], "fail")
        self.assertNotIn("pass", result["gate_statuses"])

    def test_unavailable_result_cannot_claim_pass_statuses(self) -> None:
        raw = {
            "available": False,
            "gates_passed": 8,
            "gate_statuses": ["pass"] * 8,
            "errors": [],
        }
        result = handoff._normalise_gate_result(raw)
        self.assertFalse(result["available"])
        self.assertEqual(result["gate_statuses"], ["pending"] * 8)

    def test_invalid_shapes_fail_closed(self) -> None:
        for raw in (None, "nope", 3.5, [], (None,), {"errors": "no"}):
            result = handoff._normalise_gate_result(raw)
            self.assertFalse(result["available"])


class CaptureEvidenceValidationTests(unittest.TestCase):
    """Fail-closed metric/screenshot validation, now owned by the handoff."""

    def _snap_dir(self) -> Path:
        import tempfile

        d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        return d

    def test_zero_measured_dimension_is_blocked(self) -> None:
        snap = self._snap_dir()
        (snap / "viewport-print.png").write_bytes(b"x")
        item = {
            "metrics": {
                "sw": 960, "innerH": 0, "hOverflow": 0,
                "disclosure": {"inFold": True}, "measurementStatus": "measured",
            },
            "screenshot": str(snap / "viewport-print.png"),
        }
        metric = handoff._metric_from_capture(item, "print")
        self.assertEqual(metric.measurement_status, "blocked")
        complete, error = handoff._capture_matrix_completeness(
            {"print": item}, snap
        )
        self.assertFalse(complete)
        self.assertIn("innerH is zero", error)

    def test_screenshot_escape_is_rejected(self) -> None:
        snap = self._snap_dir()
        outside = snap.parent / "outside.png"
        outside.write_bytes(b"x")
        self.addCleanup(outside.unlink)
        item = {"metrics": {}, "screenshot": str(outside)}
        self.assertIsNone(handoff._capture_screenshot_path(item, "print", snap))

    def test_empty_screenshot_is_rejected(self) -> None:
        snap = self._snap_dir()
        (snap / "viewport-print.png").write_bytes(b"")
        item = {"metrics": {}, "screenshot": str(snap / "viewport-print.png")}
        self.assertIsNone(handoff._capture_screenshot_path(item, "print", snap))


if __name__ == "__main__":
    unittest.main()
