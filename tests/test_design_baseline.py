#!/usr/bin/env python3
"""Interface tests for the DesignBaseline module (ADR-0012)."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
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

SPEC = importlib.util.spec_from_file_location("design_baseline", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load DesignBaseline module: {MODULE_PATH}")
design_baseline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(design_baseline)


def _existing_frontend(root: Path) -> Path:
    theme = root / "src" / "styles" / "theme.css"
    theme.parent.mkdir(parents=True, exist_ok=True)
    theme.write_text(
        """:root {
  --color-background: #f7f8fa;
  --color-surface: #ffffff;
  --color-primary: #2457d6;
  --space-2: 0.5rem;
  --radius-card: 12px;
  --motion-fast: 160ms;
}
body { font-family: Inter, system-ui, sans-serif; }
""",
        encoding="utf-8",
    )
    component = root / "src" / "components" / "Button.tsx"
    component.parent.mkdir(parents=True, exist_ok=True)
    component.write_text(
        "export function Button() { return <button className='primary'>Save</button>; }\n",
        encoding="utf-8",
    )
    page = root / "src" / "pages" / "Settings.tsx"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("export default function Settings() { return <main />; }\n", encoding="utf-8")
    return theme


class DesignBaselineInterfaceTests(unittest.TestCase):
    def test_prepare_generates_provenance_backed_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            run = project / ".scratch" / "run-1"
            _existing_frontend(project)

            outcome = design_baseline.prepare(project, run)

            self.assertEqual(outcome["status"], "needs_confirmation")
            draft = run / outcome["draft"]["path"]
            evidence = run / "design-baseline" / "evidence.json"
            state = run / "design-baseline" / "state.json"
            self.assertTrue(draft.is_file())
            self.assertTrue(evidence.is_file())
            self.assertTrue(state.is_file())
            text = draft.read_text(encoding="utf-8")
            self.assertIn("## Color Palette & Roles", text)
            self.assertIn("[observed]", text)
            self.assertIn("[inferred confidence=", text)
            self.assertIn("src/styles/theme.css", text)

    def test_confirm_accept_writes_canonical_baseline_and_verify_binds_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            run = project / ".scratch" / "run-2"
            _existing_frontend(project)
            design_baseline.prepare(project, run)

            binding = design_baseline.confirm(project, run, decision="accept")
            verified = design_baseline.verify(project, run)

            self.assertEqual(binding["status"], "ready")
            self.assertEqual(binding["baseline"]["path"], "DESIGN.md")
            self.assertTrue((project / "DESIGN.md").is_file())
            self.assertEqual(verified["baseline"], binding["baseline"])

    def test_verify_rejects_forged_ready_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            run = project / ".scratch" / "run-forged"
            state_dir = run / "design-baseline"
            state_dir.mkdir(parents=True)
            (state_dir / "state.json").write_text(
                json.dumps(
                    {
                        "schema": "design-baseline/v1",
                        "status": "ready",
                        "project_root": str(project.resolve()),
                        "baseline": {
                            "path": "DESIGN.md",
                            "sha256": "a" * 64,
                            "origin": "generated",
                        },
                        "sources": [],
                        "decision": {"kind": "accepted", "confirmed_at": "2026-07-24T00:00:00Z"},
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(design_baseline.BaselineError):
                design_baseline.verify(project, run)

    def test_verify_rejects_source_change_after_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            run = project / ".scratch" / "run-stale"
            theme = _existing_frontend(project)
            design_baseline.prepare(project, run)
            design_baseline.confirm(project, run, decision="accept")
            theme.write_text(":root { --color-primary: #000000; }\n", encoding="utf-8")

            with self.assertRaises(design_baseline.BaselineError):
                design_baseline.verify(project, run)

    def test_prepare_binds_stitch_candidate_using_exact_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            seed_run = project / ".scratch" / "seed"
            _existing_frontend(project)
            design_baseline.prepare(project, seed_run)
            design_baseline.confirm(project, seed_run, decision="accept")
            stitch = project / ".stitch" / "DESIGN.md"
            stitch.parent.mkdir(parents=True)
            os.replace(project / "DESIGN.md", stitch)

            run = project / ".scratch" / "run-stitch"
            outcome = design_baseline.prepare(project, run)
            binding = design_baseline.verify(project, run)

            self.assertEqual(outcome["status"], "ready")
            self.assertEqual(binding["baseline"]["path"], ".stitch/DESIGN.md")

    def test_prepare_reports_conflicting_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            seed_run = project / ".scratch" / "seed"
            _existing_frontend(project)
            design_baseline.prepare(project, seed_run)
            design_baseline.confirm(project, seed_run, decision="accept")
            stitch = project / ".stitch" / "DESIGN.md"
            stitch.parent.mkdir(parents=True)
            stitch.write_text("# conflicting authority\n", encoding="utf-8")

            outcome = design_baseline.prepare(project, project / ".scratch" / "run-conflict")

            self.assertEqual(outcome["status"], "ambiguous")
            self.assertEqual(outcome["candidates"], ["DESIGN.md", ".stitch/DESIGN.md"])

    def test_waiver_requires_reason_and_verify_returns_waived_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            run = project / ".scratch" / "run-waive"
            _existing_frontend(project)
            design_baseline.prepare(project, run)

            with self.assertRaises(design_baseline.BaselineError):
                design_baseline.confirm(project, run, decision="waive", reason="")

            binding = design_baseline.confirm(
                project,
                run,
                decision="waive",
                reason="User accepts legacy visual drift for this run",
            )
            verified = design_baseline.verify(project, run)
            self.assertEqual(binding["status"], "waived")
            self.assertEqual(verified["status"], "waived")

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unsupported")
    def test_prepare_rejects_candidate_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "product"
            project.mkdir()
            outside = root / "outside-design.md"
            outside.write_text("# external\n", encoding="utf-8")
            try:
                os.symlink(outside, project / "DESIGN.md")
            except OSError:
                self.skipTest("symlink creation unavailable")

            with self.assertRaises(design_baseline.BaselineError):
                design_baseline.prepare(project, project / ".scratch" / "run-symlink")

    def test_prepare_binds_existing_baseline_with_provenance_only(self) -> None:
        """Adopted DESIGN.md only needs frontmatter + Source Evidence (not 9 sections)."""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            theme = _existing_frontend(project)
            digest = design_baseline._sha256(theme)
            (project / "DESIGN.md").write_text(
                "---\n"
                "name: product\n"
                "colors:\n"
                "  primary: \"#2457d6\"\n"
                "---\n\n"
                "# Design System: product\n\n"
                "## Source Evidence & Confidence\n\n"
                f"- [observed] path: `{theme.relative_to(project).as_posix()}`\n"
                f"  sha256: `{digest}`\n"
                "  confidence: high\n",
                encoding="utf-8",
            )

            outcome = design_baseline.prepare(project, project / ".scratch" / "run-minimal")
            verified = design_baseline.verify(project, project / ".scratch" / "run-minimal")

            self.assertEqual(outcome["status"], "ready")
            self.assertEqual(outcome["decision"]["kind"], "existing")
            self.assertNotIn("baseline_rejection", outcome)
            self.assertEqual(verified["baseline"]["path"], "DESIGN.md")

    def test_prepare_records_rejection_reason_for_invalid_existing_baseline(self) -> None:
        """A rejected hand-written DESIGN.md keeps its reason in the draft state."""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            _existing_frontend(project)
            handwritten = "# 手写设计权威\n\n无 YAML frontmatter、无 provenance 记录。\n"
            (project / "DESIGN.md").write_text(handwritten, encoding="utf-8")

            outcome = design_baseline.prepare(project, project / ".scratch" / "run-rejected")

            self.assertEqual(outcome["status"], "needs_confirmation")
            rejection = outcome["baseline_rejection"]
            self.assertEqual(rejection["path"], "DESIGN.md")
            self.assertIn("frontmatter", rejection["reason"])
            # The rejected authority stays untouched until an explicit accept.
            self.assertEqual(
                (project / "DESIGN.md").read_text(encoding="utf-8"), handwritten
            )

    def test_prepare_without_existing_baseline_reports_no_rejection(self) -> None:
        """needs_confirmation without a prior candidate carries a null rejection."""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            run = project / ".scratch" / "run-greenfield"
            _existing_frontend(project)

            outcome = design_baseline.prepare(project, run)

            self.assertEqual(outcome["status"], "needs_confirmation")
            self.assertIsNone(outcome["baseline_rejection"])

    def test_confirm_accept_backs_up_replaced_design_md(self) -> None:
        """Accept over a differing existing DESIGN.md keeps a byte-exact backup."""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            run = project / ".scratch" / "run-replace"
            _existing_frontend(project)
            handwritten = (
                "# 手写设计权威\n\n"
                "## Source Evidence & Confidence\n\n"
                "- 未带 provenance 哈希\n"
            )
            (project / "DESIGN.md").write_text(handwritten, encoding="utf-8")
            design_baseline.prepare(project, run)

            binding = design_baseline.confirm(project, run, decision="accept")
            verified = design_baseline.verify(project, run)

            self.assertEqual(binding["status"], "ready")
            replaced = binding["replaced_baseline"]
            self.assertEqual(replaced["path"], "DESIGN.md")
            backup = run / replaced["backup"]
            self.assertEqual(
                backup, run / "design-baseline" / "previous-DESIGN.md"
            )
            self.assertEqual(backup.read_text(encoding="utf-8"), handwritten)
            self.assertEqual(replaced["sha256"], design_baseline._sha256(backup))
            self.assertNotEqual(
                (project / "DESIGN.md").read_text(encoding="utf-8"), handwritten
            )
            self.assertEqual(verified["baseline"]["origin"], "generated")

    def test_confirm_accept_without_existing_canonical_keeps_no_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            run = project / ".scratch" / "run-fresh"
            _existing_frontend(project)
            design_baseline.prepare(project, run)

            binding = design_baseline.confirm(project, run, decision="accept")

            self.assertEqual(binding["status"], "ready")
            self.assertNotIn("replaced_baseline", binding)
            self.assertFalse(
                (run / "design-baseline" / "previous-DESIGN.md").exists()
            )

    def test_confirm_cli_warns_when_accept_replaces_existing_design_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            run = project / ".scratch" / "run-replace-cli"
            _existing_frontend(project)
            (project / "DESIGN.md").write_text(
                "# 手写设计权威\n\n## Source Evidence & Confidence\n\n- 无哈希\n",
                encoding="utf-8",
            )
            design_baseline.prepare(project, run)

            stderr = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
                code = design_baseline.main(
                    ["confirm", str(project), str(run), "--decision", "accept"]
                )

            self.assertEqual(code, 0)
            self.assertIn("WARNING", stderr.getvalue())
            self.assertIn("previous-DESIGN.md", stderr.getvalue())


    def test_safe_relative_file_rejects_control_characters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            project.mkdir()
            with self.assertRaises(design_baseline.BaselineError) as ctx:
                design_baseline._safe_relative_file(
                    project, "src/theme\x00.css", "baseline source"
                )
            self.assertIn("control characters", str(ctx.exception))

    def test_read_text_capped_rejects_oversized_document(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "huge.md"
            path.write_bytes(b"x" * (design_baseline._MAX_DOC_BYTES + 1))
            with self.assertRaises(design_baseline.BaselineError) as ctx:
                design_baseline._read_text_capped(path, "baseline document")
            self.assertIn("exceeds", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
