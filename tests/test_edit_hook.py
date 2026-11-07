"""T-148: the edit-time hook reports, passes, and never blocks.

The entry is called directly — no real editor event is needed. Three
contracts: a source-decidable file reports, an undecidable one passes
quietly, and an entry that raises still exits 0 with no output.
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages" / "design-playbook"
if str(PKG / "scripts") not in sys.path:
    sys.path.insert(0, str(PKG / "scripts"))

import edit_hook  # noqa: E402  (standalone seam, same as validate.py)

# #999999 on #ffffff is 2.85:1 — below the 4.5:1 text floor.
FAILING = ".cta {\n  color: #999999;\n  background: #ffffff;\n  font-size: 16px;\n}\n"
# #767676 on #ffffff is 4.54:1 — just above the floor, not a finding.
PASSING = ".body {\n  color: #767676;\n  background: #ffffff;\n  font-size: 16px;\n}\n"
# No literal triple: the cascade supplies the color, the size is relative.
UNDECIDABLE = (
    ".body { color: var(--fg); background: #ffffff; font-size: 1rem; }\n"
    ".card { color: #999999; background: url(hero.png); font-size: 16px; }\n"
    ".lead { color: #999999; background: #ffffff; font-size: 20px; }\n"
)


def _payload(path: Path) -> str:
    return json.dumps({
        "tool_name": "Edit",
        "tool_input": {"file_path": str(path)},
    })


def _run(path: Path, runner=None) -> tuple[int, str]:
    out = io.StringIO()
    code = edit_hook.main(io.StringIO(_payload(path)), out, runner)
    return code, out.getvalue()


class EditHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _write(self, name: str, text: str) -> Path:
        path = self.tmp / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_a_decidable_file_reports_its_findings(self) -> None:
        path = self._write("failing.css", FAILING)
        code, output = _run(path)
        self.assertEqual(code, 0)
        envelope = json.loads(output)
        hint = envelope["hookSpecificOutput"]["additionalContext"]
        self.assertIn("A11Y-03", hint)
        self.assertIn(".cta", hint)
        self.assertIn("2.85:1", hint)
        # The hint must not read as full coverage.
        self.assertIn("not source-decidable", hint)

    def test_findings_carry_the_source_line(self) -> None:
        path = self._write("failing.css", FAILING)
        findings = edit_hook.check_file(path)
        self.assertEqual([finding["line"] for finding in findings], [1])
        self.assertEqual(findings[0]["ruleId"], "A11Y-03")

    def test_a_clean_decidable_file_passes_quietly(self) -> None:
        path = self._write("passing.css", PASSING)
        self.assertEqual(edit_hook.check_file(path), [])
        self.assertEqual(_run(path), (0, ""))

    def test_an_undecidable_file_passes_quietly(self) -> None:
        css = self._write("undecidable.css", UNDECIDABLE)
        self.assertEqual(edit_hook.check_file(css), [])
        self.assertEqual(_run(css), (0, ""))
        for name, text in (("view.tsx", "<div style={{color: '#999'}} />"),
                           ("notes.md", "# not css\n")):
            self.assertEqual(_run(self._write(name, text)), (0, ""))

    def test_a_raising_entry_point_neither_blocks_nor_reports(self) -> None:
        path = self._write("failing.css", FAILING)

        def boom(rule_id: str, payload: object) -> list[dict[str, object]]:
            raise RuntimeError("detector exploded")

        self.assertEqual(_run(path, boom), (0, ""))

    def test_a_malformed_payload_passes_quietly(self) -> None:
        out = io.StringIO()
        for raw in ("", "not json", '{"tool_input": {}}', '{"tool_name": "Edit"}'):
            self.assertEqual(edit_hook.main(io.StringIO(raw), out), 0)
        self.assertEqual(out.getvalue(), "")
        missing = self.tmp / "gone.css"
        self.assertEqual(_run(missing), (0, ""))

    def test_coverage_boundary_is_declared_for_every_machine_detector(self) -> None:
        import rules_registry
        from detectors.contrast import RULE_ID

        text = (
            PKG / "skills" / "design-playbook" / "references" / "rules.md"
        )
        registered = {
            status["ruleId"] for status in rules_registry.machine_detector_statuses(
                rules_registry.load_registry(text))
        }
        self.assertEqual(RULE_ID, edit_hook.CONTRAST_RULE)
        # Every machine-detector rule is named as decidable or not — the hook
        # cannot claim coverage by staying silent about a rule.
        self.assertEqual(
            set(edit_hook.SOURCE_DECIDABLE) | set(edit_hook.NOT_SOURCE_DECIDABLE),
            registered,
        )


if __name__ == "__main__":
    unittest.main()
