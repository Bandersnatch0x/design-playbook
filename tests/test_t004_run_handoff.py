#!/usr/bin/env python3
"""Public-seam tests for the thin run-handoff entrypoint (T-004)."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages" / "design-playbook"
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

from design_playbook.scripts.run_handoff import (  # noqa: E402
    RunHandoffError,
    main,
    run_handoff,
)

RUN_HANDOFF = PKG / "scripts" / "run_handoff.py"
COMMAND = PKG / "commands" / "run-handoff.md"
DELIVERABLE_HTML = (
    "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
    "<title>deliverable</title></head><body><main><h1>Deliverable</h1>"
    "</main></body></html>"
)
VIEWPORTS = ("1280x900", "768x1024", "390x844", "360x800", "print")


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, str(RUN_HANDOFF), *args],
        cwd=cwd or ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )


def _fake_capture_runner(*, url: str, out_dir: Path) -> dict[str, dict[str, Any]]:
    del url
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
    return matrix


def _blocked_capture_runner(*, url: str, out_dir: Path) -> dict[str, dict[str, Any]]:
    matrix = _fake_capture_runner(url=url, out_dir=out_dir)
    matrix["390x844"]["metrics"]["sw"] = 0
    return matrix


def _passing_gate_runner(run_root: Path) -> dict[str, Any]:
    del run_root
    return {"available": True, "gates_passed": 8, "errors": []}


def _handoff_binding(
    *,
    round_n: int,
    prototype_html_hash: str,
    report_ref: str,
    summary: str,
    options: list[str],
) -> dict[str, Any]:
    from design_playbook.mcp.preview.integrity import compute_binding_digest

    return compute_binding_digest(
        round_n=round_n,
        prototype_html_hash=prototype_html_hash,
        report_ref=report_ref,
        summary=summary,
        options=options,
    )


def _write_plan(run_root: Path, fills: tuple[str, ...], *, extra: str = "") -> None:
    body = (
        "<!-- run-profile: v1 -->\n\n"
        "```yaml\ntier: P1\nconfirmed_by: user + 2026-08-24T00:00:00Z\n```\n"
    )
    for fill in fills:
        body += f"fill: {fill}\n"
    body += extra
    (run_root / "plan.md").write_text(body, encoding="utf-8")


def _make_run(
    tmp: Path,
    *,
    fills: tuple[str, ...] = ("surface.html",),
    with_confirm: bool = False,
    write_fill_files: bool = True,
    extra_plan: str = "",
    name: str = "run",
) -> Path:
    run_root = tmp / name
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "spec.md").write_text("# spec\n", encoding="utf-8")
    (run_root / "point-back.md").write_text("# point-back\n", encoding="utf-8")
    _write_plan(run_root, fills, extra=extra_plan)
    if write_fill_files:
        for fill in fills:
            candidate = Path(fill)
            target = candidate if candidate.is_absolute() else run_root / candidate
            if not target.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(DELIVERABLE_HTML, encoding="utf-8")
    preview = run_root / "preview"
    preview.mkdir(exist_ok=True)
    (preview / "round-1.html").write_text(DELIVERABLE_HTML, encoding="utf-8")
    (preview / "log.md").write_text("## round 1\n", encoding="utf-8")
    entry = {
        "schema_version": 1,
        "decision_id": "dd-0001",
        "binding": _handoff_binding(
            round_n=1,
            prototype_html_hash="0" * 16,
            report_ref="r.md",
            summary="s",
            options=["确认通过"],
        ),
        "outcome": {
            "confirmed": True,
            "user_confirmed": True,
            "floor_pass": True,
            "floor_failure": "",
            "selected_options": ["确认通过"],
            "feedback": "ship it",
            "anchors": [],
            "aborted": False,
            "rejected": False,
            "rejection": "",
            "skipped": False,
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


def _fingerprint(paths: list[Path]) -> dict[str, str]:
    digest: dict[str, str] = {}
    for path in paths:
        if path.is_file():
            digest[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        elif path.exists():
            digest[str(path)] = "exists"
        else:
            digest[str(path)] = "missing"
    return digest


def _build(
    run_root: Path,
    *,
    fill: str | None = None,
    capture_runner=None,
    gate_runner=None,
):
    return run_handoff(
        run_root,
        fill=fill,
        round_n=1,
        summary="handoff summary",
        capture_runner=capture_runner or _fake_capture_runner,
        gate_runner=gate_runner or _passing_gate_runner,
    )


class RunHandoffDeclarationTests(unittest.TestCase):
    def test_unique_declared_fill_is_used_automatically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            run_root = _make_run(tmp, fills=("surface.html",))
            result = _build(run_root)
            self.assertEqual(result.fill, "surface.html")
            self.assertEqual(result.fill_path, (run_root / "surface.html").resolve())
            self.assertTrue(result.index_html.is_file())

    def test_multiple_declared_fills_require_explicit_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            run_root = _make_run(tmp, fills=("a.html", "b.html"))
            with self.assertRaises(RunHandoffError) as raised:
                _build(run_root)
            message = str(raised.exception)
            self.assertIn("--fill", message)
            self.assertIn("a.html", message)
            self.assertIn("b.html", message)
            self.assertFalse((run_root / "evidence" / "static-handoff").exists())

            result = _build(run_root, fill="b.html")
            self.assertEqual(result.fill, "b.html")
            self.assertEqual(result.fill_path, (run_root / "b.html").resolve())

    def test_missing_fill_declaration_fails_with_repair_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            run_root = _make_run(tmp, fills=())
            (run_root / "filled-ui.html").write_text(DELIVERABLE_HTML, encoding="utf-8")
            with self.assertRaises(RunHandoffError) as raised:
                _build(run_root)
            message = str(raised.exception).casefold()
            self.assertIn("fill:", message)
            self.assertIn("plan.md", message)
            self.assertFalse((run_root / "evidence" / "static-handoff").exists())

    def test_fenced_fill_example_is_not_a_declaration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            run_root = _make_run(
                tmp,
                fills=(),
                extra_plan="```yaml\nfill: surface.html\n```\n",
            )
            (run_root / "surface.html").write_text(DELIVERABLE_HTML, encoding="utf-8")
            with self.assertRaises(RunHandoffError) as raised:
                _build(run_root)
            self.assertIn("fill:", str(raised.exception).casefold())
            self.assertFalse((run_root / "evidence" / "static-handoff").exists())

    def test_declared_but_missing_fill_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            run_root = _make_run(
                tmp, fills=("missing.html",), write_fill_files=False
            )
            with self.assertRaises(RunHandoffError) as raised:
                _build(run_root)
            message = str(raised.exception)
            self.assertIn("missing.html", message)
            self.assertFalse((run_root / "evidence" / "static-handoff").exists())

    def test_unsupported_selection_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            run_root = _make_run(tmp, fills=("a.html", "b.html"))
            (run_root / "guess.html").write_text(DELIVERABLE_HTML, encoding="utf-8")
            with self.assertRaises(RunHandoffError) as raised:
                _build(run_root, fill="guess.html")
            message = str(raised.exception)
            self.assertIn("guess.html", message)
            self.assertIn("a.html", message)
            self.assertFalse((run_root / "evidence" / "static-handoff").exists())

    def test_preview_and_reference_fills_are_ineligible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            run_root = _make_run(tmp, fills=("preview/round-1.html",))
            with self.assertRaises(RunHandoffError) as raised:
                _build(run_root)
            self.assertIn("preview", str(raised.exception).casefold())
            self.assertFalse((run_root / "evidence" / "static-handoff").exists())

            reference = run_root / "reference"
            reference.mkdir()
            (reference / "example.html").write_text(DELIVERABLE_HTML, encoding="utf-8")
            _write_plan(run_root, ("reference/example.html",))
            with self.assertRaises(RunHandoffError) as raised:
                _build(run_root)
            self.assertIn("reference", str(raised.exception).casefold())
            self.assertFalse((run_root / "evidence" / "static-handoff").exists())


class RunHandoffResolutionAndFailureVisibilityTests(unittest.TestCase):
    def test_run_root_fill_wins_over_same_named_cwd_file(self) -> None:
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            run_root = _make_run(tmp, fills=("surface.html",))
            cwd_dir = tmp / "cwd"
            cwd_dir.mkdir()
            (cwd_dir / "surface.html").write_text(DELIVERABLE_HTML, encoding="utf-8")
            with patch.object(Path, "cwd", return_value=cwd_dir):
                result = _build(run_root)
            self.assertEqual(result.fill_path, (run_root / "surface.html").resolve())
            self.assertEqual(
                result.deliverable_html.read_bytes(),
                (run_root / "surface.html").read_bytes(),
            )

    def test_containment_check_fails_closed_on_resolution_error(self) -> None:
        from unittest.mock import patch

        from design_playbook.scripts.run_handoff import _is_ineligible_fill

        with patch.object(Path, "resolve", side_effect=OSError("resolution failed")):
            with self.assertRaises(RunHandoffError) as raised:
                _is_ineligible_fill(Path("run"), Path("run") / "preview" / "x.html")
        message = str(raised.exception)
        self.assertIn("Cannot verify", message)
        self.assertIn("resolution failed", message)

    def test_builder_payload_is_passed_through_not_replaced(self) -> None:
        from unittest.mock import patch

        from design_playbook.mcp.evidence.handoff import StaticHandoffResult

        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            run_root = _make_run(tmp, fills=("surface.html",))
            out_dir = run_root / "evidence" / "static-handoff"
            payload = {
                "verdict": "Pending",
                "authority": "pending-user",
                "confirmationSource": "unsubstantiated",
            }
            with patch(
                "design_playbook.scripts.run_handoff.build_static_handoff"
            ) as builder:
                builder.return_value = StaticHandoffResult(
                    out_dir=out_dir,
                    payload=payload,
                    json_path=out_dir / "disclosure-review.json",
                    zip_path=out_dir / "static-handoff.zip",
                    index_html=out_dir / "index.html",
                    deliverable_html=out_dir / "deliverable.html",
                )
                result = run_handoff(run_root)
            self.assertIs(result.payload, payload)
            self.assertEqual(result.verdict, "Pending")
            self.assertEqual(result.confirmation_source, "unsubstantiated")

    def test_non_dict_builder_payload_surfaces_instead_of_fake_success(self) -> None:
        from unittest.mock import patch

        from design_playbook.mcp.evidence.handoff import StaticHandoffResult

        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            run_root = _make_run(tmp, fills=("surface.html",))
            out_dir = run_root / "evidence" / "static-handoff"
            with patch(
                "design_playbook.scripts.run_handoff.build_static_handoff"
            ) as builder:
                builder.return_value = StaticHandoffResult(
                    out_dir=out_dir,
                    payload=None,
                    json_path=out_dir / "disclosure-review.json",
                    zip_path=out_dir / "static-handoff.zip",
                    index_html=out_dir / "index.html",
                    deliverable_html=out_dir / "deliverable.html",
                )
                result = run_handoff(run_root)
            # A violated builder contract must surface, not report an
            # empty-dict fake success.
            with self.assertRaises(AttributeError):
                _ = result.verdict


class RunHandoffCliAndRunSelectionTests(unittest.TestCase):
    def test_cli_requires_an_explicit_run(self) -> None:
        result = _run()
        self.assertNotEqual(result.returncode, 0)
        combined = (result.stdout + result.stderr).casefold()
        self.assertTrue("run" in combined or "run_root" in combined)

    def test_cli_does_not_discover_a_scratch_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            run_root = _make_run(tmp, fills=("surface.html",))
            result = _run(cwd=tmp)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((run_root / "evidence" / "static-handoff").exists())

    def test_explicit_run_is_the_selected_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            first = _make_run(tmp, fills=("first.html",), name="run-a")
            second = _make_run(tmp, fills=("second.html",), name="run-b")
            result = _build(second)
            self.assertEqual(result.fill, "second.html")
            self.assertEqual(result.run_root, second.resolve())
            self.assertTrue((second / "evidence" / "static-handoff" / "index.html").is_file())
            self.assertFalse((first / "evidence" / "static-handoff").exists())

    def test_cli_reports_missing_declaration_without_writing_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            run_root = _make_run(tmp, fills=())
            result = _run(str(run_root))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("fill:", result.stderr.casefold())
            self.assertIn("plan.md", result.stderr.casefold())
            self.assertFalse((run_root / "evidence" / "static-handoff").exists())

    def test_cli_help_names_the_entrypoint(self) -> None:
        result = _run("--help")
        self.assertEqual(result.returncode, 0)
        help_text = result.stdout.casefold()
        self.assertIn("--fill", help_text)
        self.assertIn("run", help_text)


class RunHandoffHonestyAndOutputTests(unittest.TestCase):
    def test_pending_and_unsubstantiated_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            run_root = _make_run(tmp, fills=("surface.html",), with_confirm=False)
            result = _build(run_root)
            payload = json.loads(result.json_path.read_text(encoding="utf-8"))
            self.assertEqual(result.verdict, "Pending")
            self.assertEqual(result.verdict, payload["verdict"])
            self.assertEqual(result.authority, payload["authority"])
            self.assertEqual(result.confirmation_source, payload["confirmationSource"])
            self.assertEqual(payload["confirmationSource"], "unsubstantiated")
            self.assertNotEqual(payload["verdict"], "Pass")

    def test_blocked_capture_is_not_promoted_to_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            run_root = _make_run(tmp, fills=("surface.html",), with_confirm=True)
            result = _build(run_root, capture_runner=_blocked_capture_runner)
            payload = json.loads(result.json_path.read_text(encoding="utf-8"))
            self.assertEqual(result.verdict, payload["verdict"])
            self.assertEqual(payload["captureStatus"], "blocked")
            self.assertNotEqual(payload["verdict"], "Pass")
            self.assertNotEqual(result.verdict, "Pass")

    def test_not_applicable_gate_status_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            run_root = _make_run(tmp, fills=("surface.html",), with_confirm=False)
            import shutil

            shutil.rmtree(run_root / "preview")
            (run_root / "preview").mkdir()
            result = _build(run_root)
            payload = json.loads(result.json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["gateStatuses"][4:], ["not-applicable"] * 4)
            self.assertEqual(result.verdict, payload["verdict"])

    def test_source_tree_stays_read_only_except_handoff_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            run_root = _make_run(tmp, fills=("surface.html",))
            watched = [
                run_root / "spec.md",
                run_root / "plan.md",
                run_root / "point-back.md",
                run_root / "surface.html",
                run_root / "preview" / "round-1.html",
                run_root / "preview" / "log.md",
            ]
            before = _fingerprint(watched)
            result = _build(run_root)
            after = _fingerprint(watched)
            self.assertEqual(before, after)
            self.assertTrue(result.index_html.is_file())
            self.assertTrue(result.json_path.is_file())
            self.assertTrue(result.zip_path.is_file())
            self.assertTrue(result.deliverable_html.is_file())
            self.assertEqual(
                result.out_dir.resolve(),
                (run_root / "evidence" / "static-handoff").resolve(),
            )
            self.assertFalse((tmp / "output").exists())

    def test_actual_output_generation_and_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            run_root = _make_run(tmp, fills=("surface.html",))
            first = _build(run_root)
            for path in (
                first.index_html,
                first.json_path,
                first.zip_path,
                first.deliverable_html,
            ):
                self.assertTrue(path.is_file(), path)
            for viewport in VIEWPORTS:
                self.assertTrue(
                    (first.out_dir / "snapshots" / f"viewport-{viewport}.png").is_file()
                )
            self.assertEqual(
                first.deliverable_html.read_bytes(),
                (run_root / "surface.html").read_bytes(),
            )
            first.index_html.write_text("stale", encoding="utf-8")
            second = _build(run_root)
            self.assertEqual(second.out_dir, first.out_dir)
            self.assertNotEqual(second.index_html.read_text(encoding="utf-8"), "stale")
            self.assertIn(second.verdict, second.index_html.read_text(encoding="utf-8"))

    def test_cli_json_preserves_pending_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            run_root = _make_run(tmp, fills=("surface.html",), with_confirm=False)
            from io import StringIO
            from unittest.mock import patch

            with patch(
                "design_playbook.scripts.run_handoff.build_static_handoff"
            ) as builder:
                from design_playbook.mcp.evidence.handoff import StaticHandoffResult

                out_dir = run_root / "evidence" / "static-handoff"
                payload = {
                    "verdict": "Pending",
                    "authority": "pending-user",
                    "confirmationSource": "unsubstantiated",
                }
                builder.return_value = StaticHandoffResult(
                    out_dir=out_dir,
                    payload=payload,
                    json_path=out_dir / "disclosure-review.json",
                    zip_path=out_dir / "static-handoff.zip",
                    index_html=out_dir / "index.html",
                    deliverable_html=out_dir / "deliverable.html",
                )
                stdout = StringIO()
                with patch("sys.stdout", stdout):
                    code = main([str(run_root), "--json"])
            self.assertEqual(code, 0)
            reported = json.loads(stdout.getvalue())
            self.assertEqual(reported["verdict"], "Pending")
            self.assertEqual(reported["authority"], "pending-user")
            self.assertEqual(reported["confirmationSource"], "unsubstantiated")
            self.assertEqual(reported["fill"], "surface.html")

    def test_command_file_is_discoverable(self) -> None:
        self.assertTrue(COMMAND.is_file())
        text = COMMAND.read_text(encoding="utf-8")
        self.assertIn("description:", text)
        self.assertIn("run_handoff.py", text)
        self.assertIn("$ARGUMENTS", text)


if __name__ == "__main__":
    unittest.main()
