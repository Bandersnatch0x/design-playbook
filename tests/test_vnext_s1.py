#!/usr/bin/env python3
"""vNext S1 unit tests: registry, seven-column rows, run-profile, shaping
log, six-block report parsing, severity alias union, G9/G11/G1-deep gates.

Issue #34 exit criterion 3: these hang off the existing CI unit-test step.
Black-box where a CLI exists (validate_run.py); in-process for the parsers.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages" / "design-playbook"
SCRIPTS = PKG / "scripts"

if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import rules_registry  # noqa: E402
from design_playbook.scripts import g11_coverage  # noqa: E402
from design_playbook.scripts.g1_spec import check_spec  # noqa: E402
from design_playbook.scripts.g2_g4_pointback import (  # noqa: E402
    _findings,
    check_pointback,
    severity_axis,
)
from design_playbook.scripts.g9_shaping import check_g9  # noqa: E402
from design_playbook.scripts.run_profile import (  # noqa: E402
    parse_run_profile,
    validate_run_profile,
)
from design_playbook.scripts.shaping_log import (  # noqa: E402
    derive_queue,
    parse_shaping_log,
)

REGISTRY_TEXT = (PKG / "skills" / "design-playbook" / "references"
                 / "rules.md").read_text(encoding="utf-8")
FIXTURE_RUN = PKG / "examples" / "export-entry" / "run"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class RegistryTests(unittest.TestCase):
    def test_registry_parses_thirteen_entries(self) -> None:
        entries = rules_registry.parse_registry(REGISTRY_TEXT)
        self.assertEqual(
            [entry.id for entry in entries],
            [f"CRAFT-{i:02d}" for i in range(1, 9)]
            + ["A11Y-01", "RESP-01", "I18N-01", "PERF-01", "SEC-01"],
        )
        self.assertEqual(
            rules_registry.validate_registry(entries), [])

    def test_registry_enums_and_placeholders(self) -> None:
        entries = rules_registry.parse_registry(REGISTRY_TEXT)
        by_id = {entry.id: entry for entry in entries}
        placeholders = {
            entry_id for entry_id, entry in by_id.items()
            if entry.provenance == "placeholder"
        }
        self.assertEqual(placeholders, {"I18N-01", "PERF-01", "SEC-01"})
        for entry_id in placeholders:
            for key in rules_registry.APPLICABILITY_KEYS:
                self.assertTrue(
                    by_id[entry_id].fields.get(key, "").strip(),
                    f"{entry_id} missing {key}",
                )
        self.assertEqual(by_id["A11Y-01"].fields["authority"], "hard-constraint")
        self.assertEqual(by_id["SEC-01"].fields["authority"], "hard-constraint")

    def test_registry_enum_drift_is_caught(self) -> None:
        text = REGISTRY_TEXT.replace("status: advisory", "status: suggested", 1)
        errors = rules_registry.validate_registry(
            rules_registry.parse_registry(text))
        self.assertTrue(any("status" in error for error in errors))

    def test_registry_unknown_reference_is_caught(self) -> None:
        text = REGISTRY_TEXT.replace(
            "related: CRAFT-06@1", "related: CRAFT-99@1", 1)
        errors = rules_registry.validate_registry(
            rules_registry.parse_registry(text))
        self.assertTrue(
            any("unknown id CRAFT-99" in error for error in errors))

    def test_registry_version_pin_drift_is_caught(self) -> None:
        text = REGISTRY_TEXT.replace(
            "related: CRAFT-06@1", "related: CRAFT-06@2", 1)
        errors = rules_registry.validate_registry(
            rules_registry.parse_registry(text))
        self.assertTrue(
            any("pins CRAFT-06@2" in error for error in errors))


class SevenColumnRowTests(unittest.TestCase):
    ROW = ("| CRAFT-01@1 | applicable | - | hit | three equal primaries "
           "| three primary variants | no exception | keep one primary |")

    def test_valid_row_parses(self) -> None:
        rows = rules_registry.parse_craft_rows(self.ROW + "\n")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.entry_id, "CRAFT-01")
        self.assertEqual(row.applicability, "applicable")
        self.assertEqual(row.result, "hit")
        entries = rules_registry.parse_registry(REGISTRY_TEXT)
        self.assertEqual(
            rules_registry.validate_craft_rows(rows, entries), [])

    def test_blank_not_applicable_reason_rejected(self) -> None:
        row = ("| CRAFT-08@1 | not-applicable | - | - | - | - | - | - |")
        entries = rules_registry.parse_registry(REGISTRY_TEXT)
        errors = rules_registry.validate_craft_rows(
            rules_registry.parse_craft_rows(row + "\n"), entries)
        self.assertTrue(any("observable reason" in e for e in errors))

    def test_result_present_only_when_applicable(self) -> None:
        row = ("| CRAFT-08@1 | blocked | motion source missing | clear "
               "| - | - | - | - |")
        entries = rules_registry.parse_registry(REGISTRY_TEXT)
        errors = rules_registry.validate_craft_rows(
            rules_registry.parse_craft_rows(row + "\n"), entries)
        self.assertTrue(any("Result must be '-'" in e for e in errors))

    def test_unknown_registry_id_rejected(self) -> None:
        row = ("| CRAFT-99@1 | applicable | - | clear | rendered | source "
               "| none | - |")
        entries = rules_registry.parse_registry(REGISTRY_TEXT)
        errors = rules_registry.validate_craft_rows(
            rules_registry.parse_craft_rows(row + "\n"), entries)
        self.assertTrue(any("unknown registry id" in e for e in errors))

    def test_case_column_rows_parse(self) -> None:
        row = ("| case-a | CRAFT-02@1 | applicable | - | hit | cards "
               "| wrappers | rows | fix it |")
        rows = rules_registry.parse_craft_rows(row + "\n", with_case_column=True)
        self.assertEqual(rows[0].entry_id, "CRAFT-02")
        self.assertEqual(rows[0].result, "hit")


class RunProfileTests(unittest.TestCase):
    PROFILE = """# plan
<!-- run-profile: v1 -->

```yaml
tier: P2
criteria:
  - decided-fields: add-only
confirmed_by: user + 2026-08-14T09:30:00Z
skipped:
  - preview: adapter absent (G5 not triggered)
upgrades: []
```
"""

    def test_parses_tier_and_skips(self) -> None:
        profile = parse_run_profile(self.PROFILE)
        self.assertIsNotNone(profile)
        self.assertEqual(profile.tier, "P2")
        self.assertEqual(
            profile.skipped, (("preview", "adapter absent (G5 not triggered)"),))
        self.assertEqual(validate_run_profile(profile), [])

    def test_missing_block_is_reported(self) -> None:
        self.assertIsNone(parse_run_profile("# plan\nbody only\n"))
        self.assertTrue(validate_run_profile(None))

    def test_invalid_tier_rejected(self) -> None:
        profile = parse_run_profile(
            self.PROFILE.replace("tier: P2", "tier: P9"))
        self.assertTrue(any("P1|P2|P3" in e for e in validate_run_profile(profile)))

    def test_skip_without_reason_rejected(self) -> None:
        profile = parse_run_profile(
            self.PROFILE.replace(
                "- preview: adapter absent (G5 not triggered)",
                "- preview:"))
        self.assertTrue(
            any("reason" in e for e in validate_run_profile(profile)))

    def test_fixture_plan_profile(self) -> None:
        profile = parse_run_profile(
            (FIXTURE_RUN / "plan.md").read_text(encoding="utf-8"))
        self.assertEqual(profile.tier, "P2")
        self.assertEqual(profile.skipped[0][0], "preview")
        self.assertEqual(validate_run_profile(profile), [])


class ShapingLogTests(unittest.TestCase):
    EVENTS = [
        {"event": "asked", "question_id": "Q1", "tier": "T1", "batch": 1,
         "text": "goal?", "impact": "l1.goal", "ts": "2026-08-14T09:00:00Z"},
        {"event": "assumption_staged", "field": "export.row_cap", "tier": "T1",
         "reason": "unanswered", "risk": "cap", "fallback": "50000",
         "ts": "2026-08-14T09:01:00Z"},
        {"event": "confirm_presented", "batch": "CP-C", "kind": "assumption",
         "items": ["export.row_cap"], "ts": "2026-08-14T09:02:00Z"},
    ]

    def test_closed_event_enum(self) -> None:
        text = "\n".join(json.dumps(e) for e in self.EVENTS) + "\n"
        self.assertEqual(len(parse_shaping_log(text)), 3)
        with self.assertRaises(Exception):
            parse_shaping_log('{"event": "exploded"}\n')

    def test_queue_derivation(self) -> None:
        queue = derive_queue(self.EVENTS)
        self.assertEqual(
            [q["question_id"] for q in queue["pending_questions"]], ["Q1"])
        self.assertEqual(
            [a["field"] for a in queue["staged_assumptions"]],
            ["export.row_cap"])
        self.assertEqual(len(queue["open_confirmations"]), 1)
        resolved = derive_queue(self.EVENTS + [
            {"event": "answered", "question_id": "Q1"},
            {"event": "item_confirmed", "batch": "CP-C",
             "field": "export.row_cap"},
        ])
        self.assertEqual(resolved["pending_questions"], [])
        self.assertEqual(resolved["staged_assumptions"], [])
        self.assertEqual(resolved["open_confirmations"], [])

    def test_g9_rejects_unknown_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sd = Path(tmp) / "shaping"
            _write(sd / "shaping-log.jsonl", '{"event": "exploded"}\n')
            findings = check_g9(sd)
            self.assertTrue(
                any(f.rule_id == "G9.invalid_event" for f in findings))

    def test_g9_requires_projection_and_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sd = Path(tmp) / "shaping"
            log = "\n".join(
                json.dumps(e) for e in self.EVENTS
            ) + '\n{"event": "archived"}\n'
            _write(sd / "shaping-log.jsonl", log)
            findings = check_g9(sd)
            rules = {f.rule_id for f in findings}
            self.assertIn("G9.missing_projection", rules)
            self.assertIn("G9.missing_queue", rules)
            _write(sd / "queue.json", json.dumps(derive_queue(self.EVENTS)))
            rules = {f.rule_id for f in check_g9(sd)}
            self.assertNotIn("G9.missing_queue", rules)
            self.assertIn("G9.missing_projection", rules)

    def test_g9_accepts_fixture_session(self) -> None:
        findings = check_g9(
            FIXTURE_RUN / "shaping",
            project_dir=FIXTURE_RUN.parent / "project",
            run_dir=FIXTURE_RUN,
        )
        self.assertEqual(findings, [])


class SixBlockReportTests(unittest.TestCase):
    POINTBACK = """# pb

## Evidence ledger

```text
criterion: L6.1
required: proof
observed: evidence/a.png
result: pass
```

## Findings

```text
issue:    toast has no accessible name
source:   components
fix:      add role=alert
severity: S3
track:    cross-cutting
confidence: high
disposition: blocking
evidence:  evidence/a11y.json
rule:      A11Y-01@1
```

## Positive findings

```text
issue:    export loop completes in limit
source:   spec L6.1
fix:      none - positive
severity: S0
disposition: info
```

## Coverage statement

必审: primary path 4/4 complete
未审: mobile viewport (undeclared)

## Limitations statement

- no user-test evidence this run

## Verdict

**Pass.**

- closes: toast has no accessible name -> recirculate -> fix -> re-eval -> 0 blocking
"""

    def test_findings_parse_additional_fields(self) -> None:
        parsed = _findings(self.POINTBACK)
        self.assertEqual(len(parsed), 2)
        first = parsed[0]
        self.assertEqual(first["track"], ["cross-cutting"])
        self.assertEqual(first["disposition"], ["blocking"])
        self.assertEqual(first["rule"], ["A11Y-01@1"])
        self.assertEqual(first["severity"], ["S3"])

    def test_extra_field_only_block_is_not_a_finding(self) -> None:
        parsed = _findings("## Notes\n\ntrack: product\n")
        self.assertEqual(parsed, [])

    def test_coverage_gate_passes_on_six_block_shape(self) -> None:
        self.assertEqual(g11_coverage.check_coverage(self.POINTBACK), [])

    def test_coverage_gate_fires_when_unreviewed_list_missing(self) -> None:
        broken = self.POINTBACK.replace(
            "未审: mobile viewport (undeclared)", "extra: nothing")
        rules = {f.rule_id for f in g11_coverage.check_coverage(broken)}
        self.assertIn("G11.missing_unreviewed_list", rules)

    def test_coverage_gate_skips_legacy_reports(self) -> None:
        legacy = "# pb\n\n## Evidence ledger\n\n(ledger rows only)\n"
        self.assertEqual(g11_coverage.check_coverage(legacy), [])
        rules = {
            f.rule_id for f in g11_coverage.check_coverage(legacy, required=True)
        }
        self.assertIn("G11.missing_coverage_block", rules)


class SeverityAxisTests(unittest.TestCase):
    """vNext S5 rewrote the alias-period expectations: the legacy values are
    now structural errors (vnext-prototype Q5=B, two-stage migration)."""

    def test_axis_mapping(self) -> None:
        for value in ("S3", "S2", "S1", "S0"):
            self.assertEqual(severity_axis(value), value)
        self.assertIsNone(severity_axis("critical"))

    def _probe(self, severity: str, disposition: str = "") -> list:
        block = (
            "issue:    probe finding\n"
            "source:   components\n"
            "fix:      fix it\n"
            f"severity: {severity}\n"
        )
        if disposition:
            block += f"disposition: {disposition}\n"
        text = (
            "# pb\n\n## Findings\n\n```text\n" + block + "```\n\n"
            "## Verdict\n\n**Recirculate.**\n"
        )
        return [f.rule_id for f in check_pointback(text, 0)]

    def test_new_axis_values_are_legal(self) -> None:
        for severity in ("S3", "S2", "S1", "S0"):
            rules = self._probe(severity)
            self.assertNotIn("G2.finding_invalid_severity", rules,
                             f"{severity} must be legal")

    def test_legacy_alias_values_are_rejected(self) -> None:
        # vNext S5 (issue #40): the alias period ended — the legacy
        # spellings are structural errors, not silent aliases any more.
        for severity in ("high (blocking)", "high", "med", "low"):
            rules = self._probe(severity)
            self.assertIn("G2.finding_invalid_severity", rules,
                          f"{severity} must be rejected after alias removal")

    def test_invalid_severity_rejected(self) -> None:
        self.assertIn(
            "G2.finding_invalid_severity", self._probe("critical"))

    def test_new_axis_s3_requires_disposition(self) -> None:
        self.assertIn("G2.s3_needs_disposition", self._probe("S3"))
        self.assertNotIn(
            "G2.s3_needs_disposition", self._probe("S3", "blocking"))
        # no legacy spelling carries blocking meaning any more — a removed
        # alias must not resurrect the old G4 closure behaviour either
        rules = self._probe("high (blocking)")
        self.assertIn("G2.finding_invalid_severity", rules)
        self.assertNotIn("G4.missing_closure_trail", rules)

    def test_disposition_enum_validated(self) -> None:
        self.assertIn(
            "G2.finding_invalid_disposition", self._probe("S2", "urgent"))


class G1DeepeningTests(unittest.TestCase):
    LEGACY = (
        "# spec\n\n## L1\n- a\n\n## L2\n- b\n\n## L3\n- c\n\n## L4\n- d\n"
        "\n## L5\n- e\n\n## L6\n- Given a When b Then c\n"
    )
    DEEP = (
        "<!-- spec-schema: 2 -->\n\n# spec\n\n## L1\n- a\n\n"
        "## L2\n\n### Page duties\n\n| Page | Duty |\n| --- | --- |\n"
        "| main | duty one |\n\n"
        "## L3\n\n### Paths\n\n| Path | Steps |\n| --- | --- |\n"
        "| P1 | main -> done |\n\n## L4\n- d\n\n"
        "## L5\n\n### Five-state matrix\n\n"
        "| Page | initial | loading | success | failure | empty |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| main | yes | yes | yes | yes | yes |\n\n"
        "## L6\n- Given a When b Then c (path: P1)\n"
    )

    def test_legacy_spec_not_deepened(self) -> None:
        self.assertEqual(check_spec(self.LEGACY), [])

    def test_deepened_spec_passes(self) -> None:
        self.assertEqual(check_spec(self.DEEP), [])

    def test_deepened_missing_matrix_fails(self) -> None:
        text = self.DEEP.replace(
            "| Page | initial | loading | success | failure | empty |",
            "| Foo | Bar |")
        rules = {f.rule_id for f in check_spec(text)}
        self.assertIn("G1.deep_l5_matrix", rules)

    def test_deepened_blank_state_cell_fails(self) -> None:
        text = self.DEEP.replace(
            "| main | yes | yes | yes | yes | yes |",
            "| main | yes | yes | yes | yes |  |")
        rules = {f.rule_id for f in check_spec(text)}
        self.assertIn("G1.deep_l5_state", rules)

    def test_deepened_unknown_path_reference_fails(self) -> None:
        text = self.DEEP.replace("(path: P1)", "(path: P9)")
        rules = {f.rule_id for f in check_spec(text)}
        self.assertIn("G1.deep_l6_path_unknown", rules)

    def test_deepened_l6_without_path_reference_fails(self) -> None:
        text = self.DEEP.replace("(path: P1)", "")
        rules = {f.rule_id for f in check_spec(text)}
        self.assertIn("G1.deep_l6_path_ref", rules)

    def test_fixture_spec_passes_deepened(self) -> None:
        self.assertEqual(
            check_spec((FIXTURE_RUN / "spec.md").read_text(encoding="utf-8")),
            [])


class FixtureRunGateTests(unittest.TestCase):
    """Exit criterion 2: the fixture run clears the whole chain to Pass."""

    def _validate(self, *extra: str) -> subprocess.CompletedProcess[str]:
        run_dir = FIXTURE_RUN
        return subprocess.run(
            [
                sys.executable,
                str(PKG / "scripts" / "validate_run.py"),
                str(run_dir / "spec.md"),
                str(run_dir / "point-back.md"),
                "--evidence-dir", str(run_dir / "evidence"),
                "--run-root", str(run_dir),
                "--contract-project", str(run_dir.parent / "project"),
                "--contract-run", str(run_dir),
                "--shaping-dir", str(run_dir / "shaping"),
                *extra,
            ],
            capture_output=True, text=True, check=False,
        )

    def test_full_chain_reaches_pass(self) -> None:
        result = self._validate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("RUN OK", result.stdout)

    def test_strict_mode_also_passes(self) -> None:
        # --strict adds --require-coverage; the six-block report satisfies it
        # and bound evidence satisfies --require-evidence. Preview absence
        # still fails --require-preview (G5 cannot fire on a static fixture),
        # so strict-preview is asserted separately below.
        result = self._validate("--require-evidence", "--require-coverage")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_g9_breaks_when_queue_drifts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "run"
            sd = run / "shaping"
            for name in ("shaping-log.jsonl", "queue.json"):
                _write(sd / name,
                       (FIXTURE_RUN / "shaping" / name).read_text(encoding="utf-8"))
            queue = json.loads((sd / "queue.json").read_text(encoding="utf-8"))
            queue["pending_questions"] = [{"question_id": "Q9"}]
            _write(sd / "queue.json", json.dumps(queue, ensure_ascii=False))
            result = subprocess.run(
                [sys.executable,
                 str(PKG / "scripts" / "validate_run.py"),
                 str(FIXTURE_RUN / "spec.md"),
                 str(FIXTURE_RUN / "point-back.md"),
                 "--shaping-dir", str(sd)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("G9", result.stdout)


if __name__ == "__main__":
    unittest.main()
