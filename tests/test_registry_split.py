"""Registry layout: explicit-path loading and the V-4 split measurement.

The registry may be one file or an index over part files. These cases pin
the fail-closed layout rules and the measured split clause, so a broken
index cannot yield an empty registry that reads as green.
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages" / "design-playbook"
if str(PKG / "scripts") not in sys.path:
    sys.path.insert(0, str(PKG / "scripts"))
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

import rules_registry  # noqa: E402  (standalone seam, same as validate.py)
from design_playbook.scripts import g8_run_registry as g8  # noqa: E402
from design_playbook.scripts import g10_design_decisions as g10  # noqa: E402
from design_playbook.scripts import rules_registry as pkg_rules  # noqa: E402
from design_playbook.scripts import validate_run as vr  # noqa: E402

REGISTRY_PATH = PKG / "skills" / "design-playbook" / "references" / "rules.md"

ENTRY = """## {entry_id} — fixture {entry_id}

```yaml
id: {entry_id}
version: 1
capability-domain: {domain}
```
"""


def _entry(entry_id: str, source: str = "", domain: str = "D4"):
    return rules_registry.RuleEntry(
        entry_id, {"capability-domain": domain}, source=source
    )


def _write_index(root: Path, parts: dict[str, str], order: list[str],
                 index_entries: str = "") -> Path:
    (root / "rules").mkdir(parents=True, exist_ok=True)
    for name, body in parts.items():
        (root / "rules" / name).write_text(body, encoding="utf-8")
    manifest = "\n".join(
        ["```registry-index", "schemaVersion: 1"]
        + [f"part: rules/{name}" for name in parts]
        + ["order: " + " ".join(order), "```"]
    )
    index = root / "rules.md"
    index.write_text(
        "# Fixture registry\n\n" + index_entries + manifest + "\n",
        encoding="utf-8",
    )
    return index


class RealLayoutTests(unittest.TestCase):
    def test_shipped_index_loads_every_entry_in_declared_order(self) -> None:
        entries = rules_registry.load_registry(REGISTRY_PATH)
        self.assertEqual(len(entries), 30)
        self.assertEqual(entries[0].id, "CRAFT-01")
        self.assertEqual(entries[-1].id, "CRAFT-11")
        self.assertGreaterEqual(
            len({entry.source for entry in entries}), 2,
            "shipped registry must be physically split",
        )
        self.assertEqual(
            rules_registry.registry_split_errors(entries), [],
            "a split layout within the limits must pass V-4",
        )

    def test_flat_text_keeps_the_declared_order(self) -> None:
        loaded = rules_registry.load_registry(REGISTRY_PATH)
        flat = rules_registry.parse_registry(
            rules_registry.load_registry_text(REGISTRY_PATH)
        )
        self.assertEqual([e.id for e in flat], [e.id for e in loaded])
        self.assertEqual(
            [e.fields for e in flat], [e.fields for e in loaded]
        )

    def test_index_text_alone_is_not_a_registry(self) -> None:
        # parse_registry stays a pure text parser; the index carries no
        # entries, so reading it without the loader must not look populated.
        text = REGISTRY_PATH.read_text(encoding="utf-8")
        self.assertEqual(rules_registry.parse_registry(text), [])


class SplitMeasurementTests(unittest.TestCase):
    def test_single_file_over_the_entry_limit_errors(self) -> None:
        entries = [_entry(f"CRAFT-{i:02d}") for i in range(1, 32)]
        errors = rules_registry.registry_split_errors(entries)
        self.assertEqual(len(errors), 1)
        self.assertIn("31 entries", errors[0])
        self.assertIn("or split", errors[0])

    def test_single_file_over_the_domain_limit_errors(self) -> None:
        entries = [_entry(f"D{index}-01", domain=f"D{index}")
                   for index in range(1, 5)]
        self.assertTrue(rules_registry.registry_split_errors(entries))

    def test_at_the_limit_is_fine(self) -> None:
        self.assertEqual(
            rules_registry.registry_split_errors(
                [_entry(f"CRAFT-{i:02d}") for i in range(1, 31)]),
            [],
        )

    def test_split_layout_satisfies_the_clause_over_the_limit(self) -> None:
        entries = [_entry(f"CRAFT-{i:02d}", source="rules/craft.md")
                   for i in range(1, 31)]
        entries.append(_entry("A11Y-01", source="rules/a11y.md"))
        self.assertEqual(rules_registry.registry_split_errors(entries), [])


class LayoutFailureTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_single_file_format_still_loads(self) -> None:
        path = self.root / "rules.md"
        path.write_text(ENTRY.format(entry_id="CRAFT-01", domain="D4")
                        + ENTRY.format(entry_id="CRAFT-02", domain="D4"),
                        encoding="utf-8")
        entries = rules_registry.load_registry(path)
        self.assertEqual([entry.id for entry in entries], ["CRAFT-01", "CRAFT-02"])
        self.assertEqual({entry.source for entry in entries}, {"rules.md"})

    def test_missing_part_fails(self) -> None:
        index = _write_index(
            self.root,
            {"craft.md": ENTRY.format(entry_id="CRAFT-01", domain="D4")},
            ["CRAFT-01"],
        )
        (self.root / "rules" / "craft.md").unlink()
        with self.assertRaises(rules_registry.RegistryLayoutError) as caught:
            rules_registry.load_registry(index)
        self.assertIn("missing", str(caught.exception))

    def test_part_path_escape_fails(self) -> None:
        (self.root / "outside.md").write_text(
            ENTRY.format(entry_id="CRAFT-01", domain="D4"), encoding="utf-8"
        )
        index = self.root / "rules.md"
        index.write_text(
            "# Fixture\n\n```registry-index\nschemaVersion: 1\n"
            "part: ../outside.md\norder: CRAFT-01\n```\n",
            encoding="utf-8",
        )
        with self.assertRaises(rules_registry.RegistryLayoutError) as caught:
            rules_registry.load_registry(index)
        self.assertIn("escapes", str(caught.exception))

    def test_duplicate_id_across_parts_fails(self) -> None:
        body = ENTRY.format(entry_id="CRAFT-01", domain="D4")
        index = _write_index(
            self.root, {"craft.md": body, "copy.md": body}, ["CRAFT-01"]
        )
        with self.assertRaises(rules_registry.RegistryLayoutError) as caught:
            rules_registry.load_registry(index)
        self.assertIn("repeats entry CRAFT-01", str(caught.exception))

    def test_order_omission_fails(self) -> None:
        index = _write_index(
            self.root,
            {"craft.md": ENTRY.format(entry_id="CRAFT-01", domain="D4")
             + ENTRY.format(entry_id="CRAFT-02", domain="D4")},
            ["CRAFT-01"],
        )
        with self.assertRaises(rules_registry.RegistryLayoutError) as caught:
            rules_registry.load_registry(index)
        self.assertIn("omits 1 registered id", str(caught.exception))

    def test_order_extra_id_fails(self) -> None:
        index = _write_index(
            self.root,
            {"craft.md": ENTRY.format(entry_id="CRAFT-01", domain="D4")},
            ["CRAFT-01", "CRAFT-99"],
        )
        with self.assertRaises(rules_registry.RegistryLayoutError) as caught:
            rules_registry.load_registry(index)
        self.assertIn("unknown id", str(caught.exception))

    def test_repeated_order_id_fails(self) -> None:
        index = _write_index(
            self.root,
            {"craft.md": ENTRY.format(entry_id="CRAFT-01", domain="D4")},
            ["CRAFT-01", "CRAFT-01"],
        )
        with self.assertRaises(rules_registry.RegistryLayoutError) as caught:
            rules_registry.load_registry(index)
        self.assertIn("repeats CRAFT-01", str(caught.exception))

    def test_index_carrying_entries_fails(self) -> None:
        index = _write_index(
            self.root,
            {"craft.md": ENTRY.format(entry_id="CRAFT-01", domain="D4")},
            ["CRAFT-01"],
            index_entries=ENTRY.format(entry_id="CRAFT-02", domain="D4") + "\n",
        )
        with self.assertRaises(rules_registry.RegistryLayoutError) as caught:
            rules_registry.load_registry(index)
        self.assertIn("carries rule entries", str(caught.exception))

    def test_empty_part_fails(self) -> None:
        index = _write_index(
            self.root,
            {"craft.md": "no entries here\n",
             "copy.md": ENTRY.format(entry_id="COPY-01", domain="D4")},
            ["COPY-01"],
        )
        with self.assertRaises(rules_registry.RegistryLayoutError) as caught:
            rules_registry.load_registry(index)
        self.assertIn("carries no rule entries", str(caught.exception))

    def test_index_order_drives_the_loaded_order(self) -> None:
        index = _write_index(
            self.root,
            {"craft.md": ENTRY.format(entry_id="CRAFT-01", domain="D4"),
             "a11y.md": ENTRY.format(entry_id="A11Y-01", domain="D4")},
            ["A11Y-01", "CRAFT-01"],
        )
        entries = rules_registry.load_registry(index)
        self.assertEqual([entry.id for entry in entries], ["A11Y-01", "CRAFT-01"])
        self.assertEqual(entries[0].source, "rules/a11y.md")

    def test_unclosed_index_fence_fails_closed(self) -> None:
        # Declaring the marker is a promise to carry a closed manifest; a
        # missing closing fence must not fall through to the single-file path
        # (which would load zero entries and read as green).
        index = self.root / "rules.md"
        index.write_text(
            "# Fixture\n\n```registry-index\nschemaVersion: 1\n"
            "part: rules/missing.md\norder: CRAFT-01\n",
            encoding="utf-8",
        )
        with self.assertRaises(rules_registry.RegistryLayoutError) as caught:
            rules_registry.load_registry(index)
        self.assertIn("not closed", str(caught.exception))

    def test_malformed_index_openings_fail_closed(self) -> None:
        # Only the canonical opener declares an index; every near miss is an
        # explicit failure instead of falling back to an empty single file.
        body = ENTRY.format(entry_id="CRAFT-01", domain="D4")
        (self.root / "rules").mkdir(exist_ok=True)
        (self.root / "rules" / "craft.md").write_text(body, encoding="utf-8")
        manifest = (
            "schemaVersion: 1\npart: rules/craft.md\norder: CRAFT-01\n"
        )
        variants = {
            "info-string suffix": f"```registry-index broken\n{manifest}```\n",
            "space after backticks": f"``` registry-index\n{manifest}```\n",
            "two backticks": f"``registry-index\n{manifest}```\n",
            "unknown fence, no entries": (
                f"```yaml\n{manifest}```\n"
            ),
        }
        for label, text in variants.items():
            with self.subTest(label):
                index = self.root / "rules.md"
                index.write_text("# Fixture\n\n" + text, encoding="utf-8")
                with self.assertRaises(rules_registry.RegistryLayoutError):
                    rules_registry.load_registry(index)

    def test_closing_fence_suffix_fails_closed(self) -> None:
        body = ENTRY.format(entry_id="CRAFT-01", domain="D4")
        (self.root / "rules").mkdir(exist_ok=True)
        (self.root / "rules" / "craft.md").write_text(body, encoding="utf-8")
        index = self.root / "rules.md"
        index.write_text(
            "# Fixture\n\n```registry-index\nschemaVersion: 1\n"
            "part: rules/craft.md\norder: CRAFT-01\n```invalid\n",
            encoding="utf-8",
        )
        with self.assertRaises(rules_registry.RegistryLayoutError) as caught:
            rules_registry.load_registry(index)
        self.assertIn("closing", str(caught.exception).lower())

    def test_prose_only_single_file_fails_closed(self) -> None:
        # An empty or unrecognized registry must not read as a green audit.
        path = self.root / "rules.md"
        path.write_text("# Registry\n\nNo rule entries here.\n", encoding="utf-8")
        with self.assertRaises(rules_registry.RegistryLayoutError) as caught:
            rules_registry.load_registry(path)
        self.assertIn("no rule entries", str(caught.exception).lower())


DD_REPORT = """## DD-0001 — trigger

```yaml
id: DD-0001
tier: record
question: trigger shape
status: confirmed-agent
constraints:
  baseline: waived: none bound this run
  spec: [l4.export-trigger]
  rules: [NOPE-99@1]
selection: {candidate: Button (icon + label), rationale: role table names it}
confirmation:
  kind: agent
  via: agent-record
  confirmed_at: 2026-08-14T10:16:00Z
supersedes: null
```
"""


class ConsumerFailureTests(unittest.TestCase):
    """Broken layouts must surface at the consumer, never read as green."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_g10_missing_part_reports_registry_unreadable(self) -> None:
        index = _write_index(
            self.root,
            {"craft.md": ENTRY.format(entry_id="CRAFT-01", domain="D4")},
            ["CRAFT-01"],
        )
        (self.root / "rules" / "craft.md").unlink()
        with mock.patch.object(g10, "_REGISTRY_PARTS", (str(index),)):
            findings = g10.check_g10(DD_REPORT)
        self.assertIn(
            "G10.registry_unreadable", {item.rule_id for item in findings},
            "a broken registry index must not skip rule-reference checks",
        )

    def test_g8_unclosed_index_fails_instead_of_empty_audit(self) -> None:
        index = self.root / "rules.md"
        index.write_text(
            "# Fixture\n\n```registry-index\nschemaVersion: 1\n"
            "part: rules/missing.md\norder: CRAFT-01\n",
            encoding="utf-8",
        )
        craft = self.root / "craft-guard.md"
        craft.write_text("", encoding="utf-8")
        with self.assertRaises(pkg_rules.RegistryLayoutError):
            g8.load_registry(index)
        with mock.patch.object(g8, "REGISTRY_PATH", index):
            self.assertEqual(g8.main(["g8", str(craft)]), 2,
                             "G8 must report the unreadable layout, not OK")

    def test_g10_malformed_index_opening_reports_unreadable(self) -> None:
        (self.root / "rules").mkdir(exist_ok=True)
        (self.root / "rules" / "craft.md").write_text(
            ENTRY.format(entry_id="CRAFT-01", domain="D4"), encoding="utf-8"
        )
        index = self.root / "rules.md"
        index.write_text(
            "# Fixture\n\n```registry-index broken\nschemaVersion: 1\n"
            "part: rules/craft.md\norder: CRAFT-01\n```\n",
            encoding="utf-8",
        )
        with mock.patch.object(g10, "_REGISTRY_PARTS", (str(index),)):
            findings = g10.check_g10(DD_REPORT)
        self.assertIn("G10.registry_unreadable",
                      {item.rule_id for item in findings})

    def test_g10_healthy_registry_flags_unknown_rule(self) -> None:
        findings = g10.check_g10(DD_REPORT)
        self.assertIn("G10.bad_rules_ref",
                      {item.rule_id for item in findings})

    def test_g8_p3_empty_audit_reports_every_missing_row(self) -> None:
        entries, _ = g8.load_registry()
        self.assertEqual(len(g8.check_g8_run("", entries, "P3")), 30)

    def test_g8_real_cli_p3_empty_audit_exits_1(self) -> None:
        craft = self.root / "craft-guard.md"
        craft.write_text("", encoding="utf-8")
        plan = PKG / "examples" / "dogfood" / "run" / "plan.md"
        self.assertEqual(g8.main(["g8", str(craft), "--plan", str(plan)]), 1)

    def test_g8_real_cli_malformed_index_opening_exits_2(self) -> None:
        (self.root / "rules").mkdir(exist_ok=True)
        (self.root / "rules" / "craft.md").write_text(
            ENTRY.format(entry_id="CRAFT-01", domain="D4"), encoding="utf-8"
        )
        index = self.root / "rules.md"
        index.write_text(
            "# Fixture\n\n```registry-index broken\nschemaVersion: 1\n"
            "part: rules/craft.md\norder: CRAFT-01\n```\n",
            encoding="utf-8",
        )
        craft = self.root / "craft-guard.md"
        craft.write_text("", encoding="utf-8")
        plan = PKG / "examples" / "dogfood" / "run" / "plan.md"
        with mock.patch.object(g8, "REGISTRY_PATH", index):
            self.assertEqual(
                g8.main(["g8", str(craft), "--plan", str(plan)]), 2,
                "malformed declaration must not print G8 OK",
            )

    def test_validate_run_main_projects_layout_error_as_json(self) -> None:
        run = PKG / "examples" / "export-entry" / "run"
        argv = [
            "validate_run.py", str(run / "spec.md"), str(run / "point-back.md"),
            "--run-root", str(run), "--legacy", "--format", "json",
        ]
        baseline = io.StringIO()
        with redirect_stdout(baseline):
            self.assertEqual(vr.main(argv), 0)
        self.assertEqual(json.loads(baseline.getvalue()), [])

        (self.root / "rules").mkdir(exist_ok=True)
        (self.root / "rules" / "craft.md").write_text(
            ENTRY.format(entry_id="CRAFT-01", domain="D4"), encoding="utf-8"
        )
        index = self.root / "rules.md"
        index.write_text(
            "# Fixture\n\n```registry-index\nschemaVersion: 1\n"
            "part: rules/missing.md\norder: CRAFT-01\n```\n",
            encoding="utf-8",
        )
        output = io.StringIO()
        with mock.patch.object(g8, "REGISTRY_PATH", index), \
                redirect_stdout(output):
            code = vr.main(argv)
        self.assertEqual(code, 1)
        findings = json.loads(output.getvalue())
        self.assertTrue(
            any(item["rule_id"] == "G8.run_registry" for item in findings),
            "the layout failure must render through the existing G8 diagnostic",
        )


if __name__ == "__main__":
    unittest.main()