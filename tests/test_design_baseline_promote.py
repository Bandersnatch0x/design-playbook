#!/usr/bin/env python3
"""T-070 unit tests: design_baseline.py promote — the durable incremental merge.

Write gate (user-gated via the promotion governance log), incremental merge
keeping the rest of the document byte-identical, byte-exact backup, verify
re-check, and refusals (no user event / not-ready baseline / waived baseline).
In-process via the same importlib seam as test_design_baseline.py.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages" / "design-playbook"
MODULE_PATH = (PKG / "skills" / "design-baseline" / "scripts"
               / "design_baseline.py")

if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

SPEC = importlib.util.spec_from_file_location("design_baseline", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load design_baseline: {MODULE_PATH}")
design_baseline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(design_baseline)

from design_playbook.scripts import promotion_governance as pg  # noqa: E402

TS = "2026-09-22T00:00:00Z"
COMPONENT = "src/ui/Button.tsx"


def _write_event(log: Path, event: dict) -> None:
    pg.append_event(log, event)


def _promote_event(target: str = COMPONENT) -> dict:
    return {
        "id": "evt-p1", "event": "promotion_decided", "decided_by": "user",
        "confirmed_at": TS, "kind": "component", "target": target,
        "decision": "promote", "rationale": "stable across runs",
    }


def _frontend(project: Path) -> Path:
    """Minimal first-party frontend (theme + component + page)."""
    theme = project / "src" / "styles" / "theme.css"
    theme.parent.mkdir(parents=True, exist_ok=True)
    theme.write_text(":root { --color-primary: #2457d6; }\n", encoding="utf-8")
    comp = project / "src" / "components" / "Button.tsx"
    comp.parent.mkdir(parents=True, exist_ok=True)
    comp.write_text("export function Button() { return null; }\n",
                    encoding="utf-8")
    page = project / "src" / "pages" / "Settings.tsx"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("export default function Settings() { return null; }\n",
                    encoding="utf-8")
    return theme


def _ready_baseline(project: Path, run: Path,
                    seed_component: bool = True) -> None:
    """Generate + accept a baseline (the reliable ready path), then inject a
    pre-existing Component Stylings entry via the same merge function promote
    uses, and rebind the state hash so the bound authority matches disk."""
    _frontend(project)
    design_baseline.prepare(project, run)
    binding = design_baseline.confirm(project, run, decision="accept")
    assert binding["status"] == "ready", binding
    if not seed_component:
        return
    design = project / "DESIGN.md"
    merged = design_baseline._merge_component_into_baseline(
        design.read_text(encoding="utf-8"),
        "src/components/Card.tsx",
        "existing-card: Card.tsx baseline styling")
    design.write_text(merged, encoding="utf-8")
    state_path = run / "design-baseline" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["baseline"]["sha256"] = design_baseline._sha256(design)
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")


class PromoteTests(unittest.TestCase):
    def _project_with_baseline(self, tmp: str, seed_component: bool = True):
        project = Path(tmp) / "product"
        run = project / ".scratch" / "run-1"
        _ready_baseline(project, run, seed_component=seed_component)
        return project, run

    def test_merge_is_incremental_and_byte_preserving(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, run = self._project_with_baseline(tmp)
            _write_event(project / "promotion-governance.jsonl",
                         _promote_event())
            before = (project / "DESIGN.md").read_text(encoding="utf-8")

            design_baseline.promote(
                project, run, COMPONENT,
                f"primary-action: {COMPONENT} (reused across runs)")

            after = (project / "DESIGN.md").read_text(encoding="utf-8")
            self.assertIn(COMPONENT, after)
            # Everything before the promoted section is byte-identical.
            self.assertEqual(before.split("## Component Stylings")[0],
                             after.split("## Component Stylings")[0])
            # The pre-existing entry is preserved alongside the new one.
            self.assertIn("existing-card: Card.tsx baseline styling", after)

    def test_missing_section_is_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            run = project / ".scratch" / "run-1"
            _ready_baseline(project, run, seed_component=False)
            # Remove the generated Component Stylings section entirely.
            design = project / "DESIGN.md"
            text = design.read_text(encoding="utf-8")
            start = text.index("## Component Stylings")
            nxt = text.find("\n## ", start + 1)
            text = text[:start] + (text[nxt + 1:] if nxt != -1 else "")
            design.write_text(text, encoding="utf-8")
            state_path = run / "design-baseline" / "state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["baseline"]["sha256"] = design_baseline._sha256(design)
            state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
            self.assertNotIn("## Component Stylings",
                             design.read_text(encoding="utf-8"))

            _write_event(project / "promotion-governance.jsonl",
                         _promote_event())
            design_baseline.promote(project, run, COMPONENT,
                                    f"primary-action: {COMPONENT}")
            after = design.read_text(encoding="utf-8")
            self.assertIn("## Component Stylings", after)
            self.assertIn(COMPONENT, after)

    def test_existing_entry_replaced_not_duplicated(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, run = self._project_with_baseline(tmp)
            _write_event(project / "promotion-governance.jsonl",
                         _promote_event())
            design_baseline.promote(project, run, COMPONENT,
                                    f"v1: {COMPONENT}")
            _write_event(project / "promotion-governance.jsonl",
                         {**_promote_event(), "id": "evt-p2"})
            design_baseline.promote(project, run, COMPONENT,
                                    f"v2: {COMPONENT}")
            after = (project / "DESIGN.md").read_text(encoding="utf-8")
            self.assertEqual(after.count(COMPONENT), 1)
            self.assertIn("v2:", after)

    def test_backup_and_state_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, run = self._project_with_baseline(tmp)
            _write_event(project / "promotion-governance.jsonl",
                         _promote_event())
            prior = (project / "DESIGN.md").read_bytes()
            result = design_baseline.promote(project, run, COMPONENT,
                                             f"primary-action: {COMPONENT}")
            backup = run / "design-baseline" / "previous-DESIGN.md"
            self.assertTrue(backup.is_file())
            self.assertEqual(backup.read_bytes(), prior)
            self.assertEqual(result["status"], "ready")

    def test_refuses_without_user_promote_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, run = self._project_with_baseline(tmp)
            # An agent-authored promote event must not authorize a write even
            # if a hostile writer bypasses append_event's validation.
            pg._raw_append(project / "promotion-governance.jsonl", {
                "id": "evt-a", "event": "promotion_decided",
                "decided_by": "agent", "confirmed_at": TS, "kind": "component",
                "target": COMPONENT, "decision": "promote", "rationale": "x",
            })
            before = (project / "DESIGN.md").read_text(encoding="utf-8")
            with self.assertRaises(design_baseline.BaselineError):
                design_baseline.promote(project, run, COMPONENT, "x")
            self.assertEqual(
                (project / "DESIGN.md").read_text(encoding="utf-8"), before)

    def test_refuses_when_no_governance_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, run = self._project_with_baseline(tmp)
            with self.assertRaises(design_baseline.BaselineError):
                design_baseline.promote(project, run, COMPONENT, "x")

    def test_refuses_on_not_ready_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "product"
            run = project / ".scratch" / "run-1"
            project.mkdir(parents=True)
            # No DESIGN.md / no prepared state -> not ready.
            _write_event(project / "promotion-governance.jsonl",
                         _promote_event())
            with self.assertRaises(design_baseline.BaselineError):
                design_baseline.promote(project, run, COMPONENT, "x")

    def test_standalone_import_fallback_loads_governance(self):
        """promote() run as a standalone script (package not importable) must
        still load promotion_governance via its importlib fallback (S1)."""
        import subprocess
        harness = ROOT / "tests" / "_standalone_promote_fallback.py"
        result = subprocess.run(
            [sys.executable, str(harness), str(ROOT)],
            capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0,
                         result.stdout + "\n" + result.stderr)
        self.assertIn("FALLBACK_OK", result.stdout)

    def test_empty_entry_line_rejected(self):
        """S4: promote() must not merge a bare bullet for an empty entry."""
        with tempfile.TemporaryDirectory() as tmp:
            project, run = self._project_with_baseline(tmp)
            _write_event(project / "promotion-governance.jsonl",
                         _promote_event())
            before = (project / "DESIGN.md").read_text(encoding="utf-8")
            with self.assertRaises(design_baseline.BaselineError):
                design_baseline.promote(project, run, COMPONENT, "   ")
            self.assertEqual(
                (project / "DESIGN.md").read_text(encoding="utf-8"), before)

    def test_substring_sibling_not_replaced(self):
        """S3: promoting Button.tsx must not clobber a ButtonGroup.tsx bullet
        that merely contains the path as a substring."""
        with tempfile.TemporaryDirectory() as tmp:
            project, run = self._project_with_baseline(tmp)
            design = project / "DESIGN.md"
            merged = design_baseline._merge_component_into_baseline(
                design.read_text(encoding="utf-8"),
                "src/ui/ButtonGroup.tsx",
                "group: src/ui/ButtonGroup.tsx (a different component)")
            design.write_text(merged, encoding="utf-8")
            state_path = run / "design-baseline" / "state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["baseline"]["sha256"] = design_baseline._sha256(design)
            state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
            _write_event(project / "promotion-governance.jsonl",
                         _promote_event())
            design_baseline.promote(project, run, COMPONENT,
                                    f"primary-action: {COMPONENT}")
            after = design.read_text(encoding="utf-8")
            # Both survive: the sibling bullet is not substring-replaced.
            self.assertIn("src/ui/ButtonGroup.tsx (a different component)",
                          after)
            self.assertIn(f"primary-action: {COMPONENT}", after)

    def test_identical_entry_skips_write(self):
        """P5: re-promoting an identical entry is a no-op skip (no replace)."""
        with tempfile.TemporaryDirectory() as tmp:
            project, run = self._project_with_baseline(tmp)
            _write_event(project / "promotion-governance.jsonl",
                         _promote_event())
            entry = f"primary-action: {COMPONENT}"
            design_baseline.promote(project, run, COMPONENT, entry)
            once = (project / "DESIGN.md").read_text(encoding="utf-8")
            _write_event(project / "promotion-governance.jsonl",
                         {**_promote_event(), "id": "evt-p2"})
            design_baseline.promote(project, run, COMPONENT, entry)
            twice = (project / "DESIGN.md").read_text(encoding="utf-8")
            self.assertEqual(once, twice)
            self.assertEqual(twice.count(f"- {entry}"), 1)

    def test_promoted_entry_records_source_provenance(self):
        """P2: promote() records the promoted component's source sha256."""
        with tempfile.TemporaryDirectory() as tmp:
            project, run = self._project_with_baseline(tmp)
            # The promoted component must exist on disk for provenance.
            src = project / COMPONENT
            src.parent.mkdir(parents=True, exist_ok=True)
            src.write_text("export function Button(){return null;}\n",
                           encoding="utf-8")
            _write_event(project / "promotion-governance.jsonl",
                         _promote_event())
            design_baseline.promote(project, run, COMPONENT,
                                    f"primary-action: {COMPONENT}")
            state = json.loads(
                (run / "design-baseline" / "state.json").read_text(
                    encoding="utf-8"))
            promo = state["promotions"][-1]
            self.assertEqual(promo["target"], COMPONENT)
            self.assertEqual(promo["source_sha256"],
                             design_baseline._sha256(src))

    def test_verify_detects_promoted_source_drift(self):
        """P3/D7: editing a promoted component's source after promotion makes
        verify() fail closed on the drift."""
        with tempfile.TemporaryDirectory() as tmp:
            project, run = self._project_with_baseline(tmp)
            src = project / COMPONENT
            src.parent.mkdir(parents=True, exist_ok=True)
            src.write_text("export function Button(){return null;}\n",
                           encoding="utf-8")
            _write_event(project / "promotion-governance.jsonl",
                         _promote_event())
            design_baseline.promote(project, run, COMPONENT,
                                    f"primary-action: {COMPONENT}")
            # Baseline verify passes right after promotion.
            design_baseline.verify(project, run)
            # Drift the promoted source -> verify must now refuse.
            src.write_text("export function Button(){return <b/>;}\n",
                           encoding="utf-8")
            with self.assertRaises(design_baseline.BaselineError):
                design_baseline.verify(project, run)


def _token_event(token: str, event_id: str = "evt-t1") -> dict:
    return {
        "id": event_id, "event": "promotion_decided", "decided_by": "user",
        "confirmed_at": TS, "kind": "token", "target": token,
        "decision": "promote", "rationale": "recurs across runs",
    }


class TokenPromoteTests(unittest.TestCase):
    """T-072: token promotion into the dedicated section, reusing the merge."""

    def test_token_merges_into_dedicated_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, run = PromoteTests._project_with_baseline(self, tmp)
            _write_event(project / "promotion-governance.jsonl",
                         _token_event("--color-primary"))
            before = (project / "DESIGN.md").read_text(encoding="utf-8")
            design_baseline.promote(
                project, run, "--color-primary",
                "`--color-primary: #2457d6` (promoted token)",
                kind="token")
            after = (project / "DESIGN.md").read_text(encoding="utf-8")
            self.assertIn("## Design Tokens (Promoted)", after)
            self.assertIn("--color-primary: #2457d6", after)
            # Extraction-template color section is untouched.
            self.assertEqual(before.split("## Color Palette & Roles")[1]
                             .split("##")[0],
                             after.split("## Color Palette & Roles")[1]
                             .split("##")[0])

    def test_token_conflict_replaces_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, run = PromoteTests._project_with_baseline(self, tmp)
            _write_event(project / "promotion-governance.jsonl",
                         _token_event("--color-primary"))
            design_baseline.promote(project, run, "--color-primary",
                                    "`--color-primary: #111111`", kind="token")
            _write_event(project / "promotion-governance.jsonl",
                         _token_event("--color-primary", event_id="evt-t2"))
            design_baseline.promote(project, run, "--color-primary",
                                    "`--color-primary: #222222`", kind="token")
            after = (project / "DESIGN.md").read_text(encoding="utf-8")
            self.assertIn("#222222", after)
            self.assertNotIn("#111111", after)

    def test_token_requires_user_token_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, run = PromoteTests._project_with_baseline(self, tmp)
            # A component-kind event must not authorize a token write.
            _write_event(project / "promotion-governance.jsonl",
                         _promote_event())
            with self.assertRaises(design_baseline.BaselineError):
                design_baseline.promote(project, run, "--color-primary",
                                        "x", kind="token")


if __name__ == "__main__":
    unittest.main()
