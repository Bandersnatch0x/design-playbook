#!/usr/bin/env python3
"""Structured finding projection for DesignBaseline verify (T-146)."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT
    / "packages"
    / "design-playbook"
    / "skills"
    / "design-baseline"
    / "scripts"
    / "design_baseline.py"
)

SPEC = importlib.util.spec_from_file_location("design_baseline_findings", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load DesignBaseline module: {MODULE_PATH}")
design_baseline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(design_baseline)


THEME_CSS = """:root {
  --color-background: #ffffff;
  --color-surface: #f7f8fa;
  --color-text: #1a1a1a;
  --color-primary: #2457d6;
}
body { font-family: Inter, system-ui, sans-serif; }
"""

DEFAULT_COLORS = (
    ("background", '"#ffffff"'),
    ("surface", '"#f7f8fa"'),
    ("text", '"#1a1a1a"'),
    ("primary", '"#2457d6"'),
)

DEFAULT_TYPOGRAPHY = (
    "## Typography Rules\n\n- Font families: Inter, system-ui, sans-serif"
)


def _write_baseline(
    project: Path,
    *,
    colors: tuple[tuple[str, str], ...] = DEFAULT_COLORS,
    typography: str | None = DEFAULT_TYPOGRAPHY,
    palette_extra: str = "",
) -> str:
    """Write a validated existing DESIGN.md plus the source it binds."""

    source = project / "src" / "styles" / "theme.css"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(THEME_CSS, encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    lines = ["---", 'name: "product"', "colors:"]
    lines.extend(f"  {role}: {value}" for role, value in colors)
    lines.extend(["---", "", "# Design System: product", "", "## Color Palette & Roles", ""])
    for role, value in colors:
        lines.append(f"- [observed] `--color-{role}: {value.strip().strip(chr(34))}`")
    if palette_extra:
        lines.append(palette_extra)
    if typography is not None:
        lines.extend(["", typography])
    lines.extend(
        [
            "",
            "## Source Evidence & Confidence",
            "",
            "- [observed] path: `src/styles/theme.css`",
            f"  sha256: `{digest}`",
            "  confidence: high",
        ]
    )
    text = "\n".join(lines) + "\n"
    (project / "DESIGN.md").write_text(text, encoding="utf-8")
    return text


def _bind(project: Path, run: Path) -> dict:
    outcome = design_baseline.prepare(project, run)
    if outcome["status"] != "ready":
        raise AssertionError(f"baseline was not bound: {outcome}")
    return design_baseline.verify_findings(project, run)


def _waive(project: Path, run: Path) -> Path:
    """Prepare + confirm a real waiver, returning its state file.

    The project has first-party sources but no existing DESIGN.md, so prepare
    produces a bound draft and confirm(waive) records an explicit decision
    over the source hashes — the legitimate waiver path.
    """

    source = project / "src" / "styles" / "theme.css"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(THEME_CSS, encoding="utf-8")
    design_baseline.prepare(project, run)
    design_baseline.confirm(
        project,
        run,
        decision="waive",
        reason="User accepts legacy visual drift for this run",
    )
    return run / "design-baseline" / "state.json"


def _rewrite_state(state_path: Path, mutate) -> None:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    mutate(state)
    state_path.write_text(json.dumps(state), encoding="utf-8")


def _codes(result: dict) -> list[str]:
    return [finding["code"] for finding in result["findings"]]


class DesignBaselineFindingTests(unittest.TestCase):
    def test_clean_baseline_produces_zero_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            run = project / ".scratch" / "clean-findings"
            _write_baseline(project)

            result = _bind(project, run)

            self.assertEqual(result["findings"], [])
            self.assertEqual(result["gate"]["verdict"], "pass")
            self.assertEqual(result["gate"]["errors"], 0)

    def test_generated_draft_produces_zero_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            run = project / ".scratch" / "generated-findings"
            theme = project / "src" / "styles" / "theme.css"
            theme.parent.mkdir(parents=True, exist_ok=True)
            theme.write_text(
                ":root {\n"
                "  --color-background: #f7f8fa;\n"
                "  --color-surface: #ffffff;\n"
                "  --color-text: #1a1a1a;\n"
                "  --color-primary: #2457d6;\n"
                "  --space-2: 0.5rem;\n"
                "}\n"
                "body { font-family: Inter, system-ui, sans-serif; }\n",
                encoding="utf-8",
            )
            design_baseline.prepare(project, run)
            design_baseline.confirm(project, run, decision="accept")

            result = design_baseline.verify_findings(project, run)

            self.assertEqual(result["findings"], [])
            self.assertEqual(result["gate"]["verdict"], "pass")

    def test_source_drift_produces_reference_broken(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            run = project / ".scratch" / "drift"
            _write_baseline(project)
            _bind(project, run)
            (project / "src" / "styles" / "theme.css").write_text(
                ":root { --color-primary: #000000; }\n", encoding="utf-8"
            )

            result = design_baseline.verify_findings(project, run)

            self.assertIn(design_baseline.CODE_REFERENCE_BROKEN, _codes(result))
            broken = [
                finding
                for finding in result["findings"]
                if finding["code"] == design_baseline.CODE_REFERENCE_BROKEN
            ][0]
            self.assertEqual(broken["severity"], "error")
            self.assertEqual(broken["path"], "src/styles/theme.css")
            self.assertEqual(result["gate"]["verdict"], "fail")

    def test_low_contrast_produces_contrast_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            run = project / ".scratch" / "contrast"
            _write_baseline(
                project,
                colors=(
                    ("background", '"#ffffff"'),
                    ("surface", '"#f7f8fa"'),
                    ("text", '"#eeeeee"'),
                    ("primary", '"#2457d6"'),
                ),
            )

            result = _bind(project, run)

            self.assertIn(design_baseline.CODE_CONTRAST_INSUFFICIENT, _codes(result))
            self.assertEqual(result["gate"]["verdict"], "fail")

    def test_unused_token_produces_orphan_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            run = project / ".scratch" / "orphan"
            _write_baseline(
                project,
                palette_extra="- [observed] `--color-brand: #123456`",
            )

            result = _bind(project, run)

            self.assertIn(design_baseline.CODE_TOKEN_ORPHANED, _codes(result))
            orphan = [
                finding
                for finding in result["findings"]
                if finding["code"] == design_baseline.CODE_TOKEN_ORPHANED
            ][0]
            self.assertEqual(orphan["severity"], "warning")
            self.assertEqual(result["gate"]["verdict"], "pass")

    def test_missing_primary_color_produces_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            run = project / ".scratch" / "no-primary"
            _write_baseline(
                project,
                colors=(
                    ("background", '"#ffffff"'),
                    ("surface", '"#f7f8fa"'),
                    ("text", '"#1a1a1a"'),
                ),
            )

            result = _bind(project, run)

            self.assertIn(design_baseline.CODE_PRIMARY_COLOR_MISSING, _codes(result))
            self.assertEqual(result["gate"]["verdict"], "fail")

    def test_typography_without_family_produces_font_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            run = project / ".scratch" / "no-font"
            _write_baseline(
                project,
                typography="## Typography Rules\n\n- Hierarchy: display, heading, body",
            )

            result = _bind(project, run)

            self.assertIn(design_baseline.CODE_PRIMARY_FONT_MISSING, _codes(result))
            self.assertEqual(result["gate"]["verdict"], "fail")

    def test_unjudgeable_check_stays_advisory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            run = project / ".scratch" / "advisory"
            _write_baseline(project, typography=None)

            result = _bind(project, run)

            self.assertEqual(
                [finding["code"] for finding in result["findings"]],
                [design_baseline.CODE_CHECK_UNAVAILABLE],
            )
            self.assertEqual(result["findings"][0]["severity"], "advisory")
            self.assertEqual(result["gate"]["verdict"], "pass")

    def test_changed_baseline_document_produces_binding_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            run = project / ".scratch" / "binding"
            _write_baseline(project)
            _bind(project, run)
            with (project / "DESIGN.md").open("a", encoding="utf-8") as handle:
                handle.write("\n")

            result = design_baseline.verify_findings(project, run)

            self.assertIn(design_baseline.CODE_BINDING_INVALID, _codes(result))
            self.assertEqual(result["gate"]["verdict"], "fail")

    def test_findings_keep_the_stable_four_field_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            run = project / ".scratch" / "shape"
            _write_baseline(
                project,
                colors=(("background", '"#ffffff"'), ("text", '"#eeeeee"')),
                typography=None,
            )

            result = _bind(project, run)

            self.assertTrue(result["findings"])
            for finding in result["findings"]:
                self.assertEqual(
                    set(finding), {"severity", "path", "code", "message"})
                self.assertIn(finding["code"], design_baseline.FINDING_CODES)
                self.assertTrue(finding["message"])

    def test_findings_cli_exit_code_follows_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            run = project / ".scratch" / "cli"
            _write_baseline(project)
            design_baseline.prepare(project, run)

            clean_output = io.StringIO()
            with contextlib.redirect_stdout(clean_output):
                clean_code = design_baseline.main(
                    ["findings", str(project), str(run)])
            clean = json.loads(clean_output.getvalue())
            self.assertEqual(clean_code, 0)
            self.assertEqual(clean["gate"]["verdict"], "pass")

            (project / "src" / "styles" / "theme.css").write_text(
                ":root { --color-primary: #000000; }\n", encoding="utf-8")
            failed_output = io.StringIO()
            with contextlib.redirect_stdout(failed_output):
                failed_code = design_baseline.main(
                    ["findings", str(project), str(run)])
            failed = json.loads(failed_output.getvalue())
            self.assertEqual(failed_code, 1)
            self.assertEqual(failed["gate"]["verdict"], "fail")


class DesignBaselineWaiverFindingTests(unittest.TestCase):
    """T-158: a waived state is an exemption only when its decision and
    source hashes pass the same validation ``verify`` applies."""

    def test_valid_waiver_stays_an_explicit_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            run = project / ".scratch" / "waiver-control"
            _waive(project, run)

            verified = design_baseline.verify(project, run)
            result = design_baseline.verify_findings(project, run)

            self.assertEqual(verified["status"], "waived")
            self.assertTrue(result["waived"])
            self.assertEqual(result["findings"], [])
            self.assertEqual(result["gate"]["verdict"], "pass")

    def test_forged_waiver_reason_is_not_a_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            run = project / ".scratch" / "waiver-forged"
            state_path = _waive(project, run)
            _rewrite_state(
                state_path,
                lambda state: state.__setitem__(
                    "decision",
                    {
                        "kind": "waived",
                        "reason": "   ",
                        "confirmed_at": "2026-11-07T00:00:00Z",
                    },
                ),
            )

            with self.assertRaises(design_baseline.BaselineError) as ctx:
                design_baseline.verify(project, run)
            self.assertIn("invalid baseline waiver decision", str(ctx.exception))

            result = design_baseline.verify_findings(project, run)

            self.assertFalse(result["waived"])
            self.assertEqual(result["gate"]["verdict"], "fail")
            errors = [
                finding
                for finding in result["findings"]
                if finding["severity"] == "error"
            ]
            self.assertEqual(len(errors), 1)
            self.assertEqual(errors[0]["code"], design_baseline.CODE_BINDING_INVALID)
            self.assertEqual(errors[0]["path"], "design-baseline/state.json")
            self.assertIn("invalid baseline waiver decision", errors[0]["message"])

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = design_baseline.main(
                    ["findings", str(project), str(run)])
            self.assertEqual(exit_code, 1)
            self.assertEqual(
                json.loads(output.getvalue())["gate"]["verdict"], "fail")

    def test_missing_waiver_decision_is_not_a_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            run = project / ".scratch" / "waiver-no-decision"
            state_path = _waive(project, run)
            _rewrite_state(state_path, lambda state: state.__setitem__("decision", None))

            with self.assertRaises(design_baseline.BaselineError):
                design_baseline.verify(project, run)

            result = design_baseline.verify_findings(project, run)

            self.assertFalse(result["waived"])
            self.assertEqual(result["gate"]["verdict"], "fail")
            self.assertEqual(_codes(result), [design_baseline.CODE_BINDING_INVALID])

    def test_waived_source_drift_is_not_a_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            run = project / ".scratch" / "waiver-drift"
            _waive(project, run)
            (project / "src" / "styles" / "theme.css").write_text(
                ":root { --color-primary: #000000; }\n", encoding="utf-8"
            )

            with self.assertRaises(design_baseline.BaselineError) as ctx:
                design_baseline.verify(project, run)
            self.assertIn("baseline source changed", str(ctx.exception))

            result = design_baseline.verify_findings(project, run)

            self.assertFalse(result["waived"])
            self.assertEqual(result["gate"]["verdict"], "fail")
            error = result["findings"][0]
            self.assertEqual(error["severity"], "error")
            self.assertEqual(error["code"], design_baseline.CODE_BINDING_INVALID)
            self.assertEqual(error["path"], "design-baseline/state.json")
            self.assertIn("baseline source changed: src/styles/theme.css",
                          error["message"])


if __name__ == "__main__":
    unittest.main()
