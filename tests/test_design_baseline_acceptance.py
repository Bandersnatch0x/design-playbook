#!/usr/bin/env python3
"""Baseline owner capture entry for complete acceptance (T-158 phase A).

``capture`` is the one owner entry phase B freezes into RunFacts: the exact
state text it read plus the existing findings payload, verified once.
"""

from __future__ import annotations

import hashlib
import importlib.util
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

SPEC = importlib.util.spec_from_file_location(
    "design_baseline_acceptance", MODULE_PATH)
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


def _write_ready_project(project: Path) -> None:
    source = project / "src" / "styles" / "theme.css"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(THEME_CSS, encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    lines = [
        "---",
        'name: "product"',
        "colors:",
        '  background: "#ffffff"',
        '  surface: "#f7f8fa"',
        '  text: "#1a1a1a"',
        '  primary: "#2457d6"',
        "---",
        "",
        "# Design System: product",
        "",
        "## Color Palette & Roles",
        "",
        "- [observed] `--color-background: #ffffff`",
        "- [observed] `--color-surface: #f7f8fa`",
        "- [observed] `--color-text: #1a1a1a`",
        "- [observed] `--color-primary: #2457d6`",
        "",
        "## Typography Rules",
        "",
        "- Font families: Inter, system-ui, sans-serif",
        "",
        "## Source Evidence & Confidence",
        "",
        "- [observed] path: `src/styles/theme.css`",
        f"  sha256: `{digest}`",
        "  confidence: high",
    ]
    (project / "DESIGN.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _ready(project: Path, run: Path) -> Path:
    _write_ready_project(project)
    outcome = design_baseline.prepare(project, run)
    if outcome["status"] != "ready":
        raise AssertionError(f"baseline was not bound: {outcome}")
    return run / "design-baseline" / "state.json"


def _waive(project: Path, run: Path) -> Path:
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


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(
            path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class DesignBaselineCaptureTests(unittest.TestCase):
    def test_capture_returns_exact_state_text_and_existing_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            run = project / ".scratch" / "capture-ready"
            state_path = _ready(project, run)

            result = design_baseline.capture(project, run)

            self.assertEqual(set(result), {"state_text", "findings"})
            self.assertEqual(
                result["state_text"],
                state_path.read_text(encoding="utf-8-sig"),
            )
            self.assertEqual(
                result["findings"], design_baseline.verify_findings(project, run))
            self.assertEqual(
                result["findings"]["schema"], design_baseline.FINDINGS_SCHEMA)
            self.assertEqual(result["findings"]["gate"]["verdict"], "pass")

    def test_capture_reports_changed_design_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            run = project / ".scratch" / "capture-binding"
            _ready(project, run)
            with (project / "DESIGN.md").open("a", encoding="utf-8") as handle:
                handle.write("\n")

            result = design_baseline.capture(project, run)

            codes = [
                finding["code"]
                for finding in result["findings"]["findings"]
            ]
            self.assertIn(design_baseline.CODE_BINDING_INVALID, codes)
            self.assertEqual(result["findings"]["gate"]["verdict"], "fail")

    def test_capture_forged_waiver_is_not_a_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            run = project / ".scratch" / "capture-forged-waiver"
            state_path = _waive(project, run)
            _rewrite_state(
                state_path,
                lambda state: state.__setitem__("decision", None),
            )

            with self.assertRaises(design_baseline.BaselineError):
                design_baseline.verify(project, run)

            result = design_baseline.capture(project, run)

            self.assertFalse(result["findings"]["waived"])
            self.assertEqual(result["findings"]["gate"]["verdict"], "fail")

    def test_capture_rejects_foreign_state_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            run = project / ".scratch" / "capture-root"
            state_path = _ready(project, run)
            foreign = str((Path(tmp) / "other-project").resolve())
            _rewrite_state(
                state_path, lambda state: state.__setitem__("project_root", foreign))

            with self.assertRaises(design_baseline.BaselineError) as ctx:
                design_baseline.capture(project, run)
            self.assertIn(
                "bound to a different project root", str(ctx.exception))

    def test_capture_requires_a_state_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            project.mkdir()
            run = project / ".scratch" / "absent"

            with self.assertRaises(design_baseline.BaselineError) as ctx:
                design_baseline.capture(project, run)
            self.assertIn("baseline state does not exist", str(ctx.exception))

    def test_capture_and_verify_leave_the_tree_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            run = project / ".scratch" / "capture-readonly"
            _ready(project, run)
            before = _tree_hashes(project)

            design_baseline.verify(project, run)
            design_baseline.verify_findings(project, run)
            design_baseline.capture(project, run)

            self.assertEqual(_tree_hashes(project), before)


if __name__ == "__main__":
    unittest.main()
