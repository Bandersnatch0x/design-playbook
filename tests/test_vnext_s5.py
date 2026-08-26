#!/usr/bin/env python3
"""vNext S5 unit tests: learning-candidate queue derivation (threshold
positive/negative), rules-governance.jsonl schema + append discipline,
G8 governance-ref wiring (machine-enforced entries need a promote
adjudication), and the severity new-axis-only domain (legacy aliases are
structural errors).

Issue #40 exit criteria: these hang off the existing CI unit-test step
(same wiring as test_vnext_s1..s4.py). Black-box where a CLI exists
(aggregate_runs.py); in-process for the parsers and gate functions.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages" / "design-playbook"

if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))
if str(PKG / "scripts") not in sys.path:
    sys.path.insert(0, str(PKG / "scripts"))

import rules_registry  # noqa: E402  (standalone seam, same as validate.py)
from design_playbook.scripts import learning_candidates as lc  # noqa: E402
from design_playbook.scripts import rules_governance as rg  # noqa: E402
from design_playbook.scripts.finding_syntax import severity_axis  # noqa: E402
from design_playbook.scripts.g2_g4_pointback import check_pointback  # noqa: E402

REGISTRY_TEXT = (PKG / "skills" / "design-playbook" / "references"
                 / "rules.md").read_text(encoding="utf-8")
GOVERNANCE_FIXTURE = (
    PKG / "examples" / "rules-governance" / "rules-governance.jsonl"
)
AGGREGATE = ROOT / "scripts" / "aggregate_runs.py"
FIXTURE_PASS = PKG / "tests" / "fixtures" / "pass"

SIGNAL = "trigger button has no busy state while export runs"


def _occurrence(run: str, context: str, *, issue: str = SIGNAL,
                date: str = "2026-08-14", severity: str = "S2",
                false_positive: bool = False,
                false_positive_note: str = "") -> lc.Occurrence:
    return lc.Occurrence(
        run=run, issue=issue, task_context=context, date=date,
        severity=severity, track="interaction", confidence="high",
        false_positive=false_positive, false_positive_note=false_positive_note,
    )


class CandidateDerivationTests(unittest.TestCase):
    """Threshold: distinct runs >= 3 AND contexts >= 2 AND unexplained FPs 0."""

    def HISTORY(self, *, runs: int = 3, contexts: tuple[str, ...] = ("a", "a", "b"),
                false_positives: list[lc.Occurrence] | None = None,
                ) -> list[lc.Occurrence]:
        history = [
            _occurrence(f"run-{index}", contexts[index] if index < len(contexts) else contexts[-1])
            for index in range(runs)
        ]
        return history + (false_positives or [])

    def test_qualifying_signal_enters_the_queue(self) -> None:
        candidates = lc.derive_candidates(self.HISTORY())
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertTrue(candidate.qualifies)
        self.assertEqual(candidate.distinct_runs, 3)
        self.assertEqual(candidate.distinct_task_contexts, 2)
        self.assertEqual(candidate.unexplained_false_positives, 0)
        self.assertEqual(candidate.gaps, [])
        self.assertRegex(candidate.candidate_id, r"^CAND-\d{4}-\d{2}-\d{2}$")
        self.assertEqual(len(candidate.occurrences), 3)  # contexts not merged

    def test_below_three_runs_reports_the_gap(self) -> None:
        candidates = lc.derive_candidates(self.HISTORY(runs=2))
        self.assertFalse(candidates[0].qualifies)
        self.assertIn("distinct_runs 2 < 3", candidates[0].gaps)

    def test_single_task_context_reports_the_gap(self) -> None:
        candidates = lc.derive_candidates(
            self.HISTORY(contexts=("a", "a", "a")))
        self.assertFalse(candidates[0].qualifies)
        self.assertIn("distinct_task_contexts 1 < 2",
                      candidates[0].gaps)

    def test_unexplained_false_positive_blocks_the_queue(self) -> None:
        history = self.HISTORY() + [
            _occurrence("run-99", "b", false_positive=True)]
        candidates = lc.derive_candidates(history)
        self.assertFalse(candidates[0].qualifies)
        self.assertIn("unexplained_false_positives 1 > 0",
                      candidates[0].gaps)

    def test_explained_false_positive_stays_in_the_notes(self) -> None:
        history = self.HISTORY() + [
            _occurrence("run-99", "b", false_positive=True,
                        false_positive_note="idempotent operation (listed exception)")]
        candidates = lc.derive_candidates(history)
        self.assertTrue(candidates[0].qualifies)
        self.assertEqual(candidates[0].false_positive_notes,
                         ["idempotent operation (listed exception)"])

    def test_normalization_groups_case_and_whitespace_variants(self) -> None:
        history = [
            _occurrence("run-1", "a", issue=SIGNAL),
            _occurrence("run-2", "a", issue=f"  {SIGNAL.upper()}  "),
            _occurrence("run-3", "b", issue=f"{SIGNAL.capitalize()} "),
        ]
        candidates = lc.derive_candidates(history)
        self.assertEqual(len(candidates), 1)
        self.assertTrue(candidates[0].qualifies)

    def test_positive_findings_never_enter_the_queue(self) -> None:
        history = self.HISTORY() + [
            _occurrence(f"run-pos-{index}", "c", severity="S0",
                        issue="export loop completes within the limit")
            for index in range(3)
        ]
        candidates = lc.derive_candidates(history)
        keys = [candidate.signal_key for candidate in candidates]
        self.assertNotIn(lc.normalize("export loop completes within the limit"),
                         keys)

    def test_invalid_severities_cannot_help_a_signal_qualify(self) -> None:
        history = [
            _occurrence("run-valid-1", "a", severity="S2"),
            _occurrence("run-valid-2", "b", severity="S1"),
        ] + [
            _occurrence(f"run-invalid-{index}", "c", severity=severity)
            for index, severity in enumerate(
                ("S0", "", " ", "high", "med", "low", "unknown"), 1
            )
        ]
        candidates = lc.derive_candidates(history)
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertFalse(candidate.qualifies)
        self.assertEqual(candidate.distinct_runs, 2)
        self.assertIn("distinct_runs 2 < 3", candidate.gaps)
        self.assertEqual(
            {occurrence.severity for occurrence in candidate.occurrences},
            {"S2", "S1"},
        )

    def test_view_shape_matches_the_protocol(self) -> None:
        view = lc.candidate_view(self.HISTORY())
        self.assertEqual(view["threshold"], {
            "distinct_runs": 3, "distinct_task_contexts": 2,
            "unexplained_false_positives": 0,
        })
        self.assertEqual(len(view["qualifying"]), 1)
        candidate = view["qualifying"][0]
        self.assertEqual(candidate["status"], "candidate")
        self.assertEqual(
            {occurrence["task_context"] for occurrence in candidate["occurrences"]},
            {"a", "b"},
        )
        self.assertEqual(view["below_threshold"], [])

    def test_unspecified_contexts_are_conservative(self) -> None:
        # contexts not supplied -> one unspecified context -> cannot qualify
        history = [
            _occurrence(f"run-{index}", "") for index in range(4)
        ]
        candidates = lc.derive_candidates(history)
        self.assertFalse(candidates[0].qualifies)
        self.assertIn("distinct_task_contexts 1 < 2", candidates[0].gaps)


class OccurrenceLoaderTests(unittest.TestCase):
    """Point-back text -> occurrences -> queue (the loader path)."""

    def _pointback(self, issue: str, severity: str = "S2") -> str:
        return (
            "# pb\n\n## Findings\n\n```text\n"
            f"issue:    {issue}\n"
            "source:   components\n"
            "fix:      disable the trigger while in flight\n"
            f"severity: {severity}\n"
            "track:    interaction\n"
            "confidence: high\n"
            "```\n\n## Verdict\n\n**Recirculate.**\n"
        )

    def test_multi_run_history_derivation(self) -> None:
        texts = {
            "2026-08-10-run-a": self._pointback(SIGNAL),
            "2026-08-12-run-b": self._pointback(f"  {SIGNAL.upper()} "),
            "2026-08-14-run-c": self._pointback(SIGNAL, severity="S1"),
        }
        contexts = {
            "2026-08-10-run-a": "data-export",
            "2026-08-12-run-b": "data-export",
            "2026-08-14-run-c": "batch-delete",
        }
        occurrences = lc.occurrences_from_pointbacks(texts, contexts)
        candidates = lc.derive_candidates(occurrences)
        self.assertEqual(len(candidates), 1)
        self.assertTrue(candidates[0].qualifies)
        self.assertEqual(candidates[0].distinct_runs, 3)
        self.assertEqual(candidates[0].distinct_task_contexts, 2)

    def test_extra_field_only_blocks_are_not_occurrences(self) -> None:
        occurrences = lc.occurrences_from_pointbacks(
            {"run-a": "## Notes\n\ntrack: product\n"})
        self.assertEqual(occurrences, [])

    def test_loader_preserves_raw_invalid_severity_for_fail_closed_derivation(self) -> None:
        occurrences = lc.occurrences_from_pointbacks({
            "run-a": self._pointback(SIGNAL, severity="high"),
        })
        self.assertEqual(occurrences[0].severity, "high")
        self.assertEqual(lc.derive_candidates(occurrences), [])


class GovernanceLogTests(unittest.TestCase):
    """Schema v1: enums, required fields, reference existence, append
    discipline (stable ids, supersedes -> earlier event, user-decisive
    events never written by an agent)."""

    EVENTS: list[dict]

    @classmethod
    def setUpClass(cls) -> None:
        cls.EVENTS = rg.parse_governance_log(
            GOVERNANCE_FIXTURE.read_text(encoding="utf-8"))

    def test_fixture_full_chain_is_valid(self) -> None:
        self.assertEqual(
            [event["event"] for event in self.EVENTS],
            ["candidate_opened", "evidence_appended", "adjudicated",
             "adjudicated"])
        self.assertEqual(rg.validate_governance_events(self.EVENTS), [])
        promotions = rg.promote_adjudications(self.EVENTS)
        self.assertEqual(promotions["ST-01"]["id"], "RG-0004")
        self.assertEqual(promotions["ST-01"]["target_status"],
                         "machine-enforced")

    def _mutate(self, **overrides) -> list[dict]:
        events = json.loads(json.dumps(self.EVENTS))  # deep copy
        first = events[0]
        for key, value in overrides.items():
            if value is None:
                first.pop(key, None)
            else:
                first[key] = value
        return events

    def test_unknown_event_rejected(self) -> None:
        errors = rg.validate_governance_events(
            self._mutate(event="auto_promoted"))
        self.assertTrue(any("not in" in error for error in errors))

    def test_decisive_event_never_written_by_agent(self) -> None:
        events = json.loads(json.dumps(self.EVENTS))
        events[2]["decided_by"] = "agent"  # adjudicated promote
        errors = rg.validate_governance_events(events)
        self.assertTrue(any("decided_by must be 'user'" in error
                            for error in errors))

    def test_blank_rationale_rejected(self) -> None:
        errors = rg.validate_governance_events(self._mutate(rationale="  "))
        self.assertTrue(any("rationale" in error for error in errors))

    def test_bad_timestamp_rejected(self) -> None:
        errors = rg.validate_governance_events(
            self._mutate(confirmed_at="yesterday"))
        self.assertTrue(any("ISO-8601" in error for error in errors))

    def test_bad_decision_enum_rejected(self) -> None:
        events = json.loads(json.dumps(self.EVENTS))
        events[2]["decision"] = "force"
        errors = rg.validate_governance_events(events)
        self.assertTrue(any("decision" in error for error in errors))

    def test_duplicate_id_rejected(self) -> None:
        events = json.loads(json.dumps(self.EVENTS))
        events[3]["id"] = events[0]["id"]
        errors = rg.validate_governance_events(events)
        self.assertTrue(any("duplicate event id" in error for error in errors))

    def test_dangling_supersedes_rejected(self) -> None:
        events = json.loads(json.dumps(self.EVENTS))
        events[0]["supersedes"] = "RG-9999"
        errors = rg.validate_governance_events(events)
        self.assertTrue(any("unknown event id" in error for error in errors))

    def test_forward_supersedes_rejected(self) -> None:
        events = json.loads(json.dumps(self.EVENTS))
        events[0]["supersedes"] = "RG-0004"  # later event
        errors = rg.validate_governance_events(events)
        self.assertTrue(any("earlier event" in error for error in errors))

    def test_machine_enforced_promotion_requires_six_criteria(self) -> None:
        events = json.loads(json.dumps(self.EVENTS))
        del events[3]["criteria"]["validation"]
        errors = rg.validate_governance_events(events)
        self.assertTrue(any("six criteria" in error for error in errors))

    def test_advisory_promotion_requires_the_weak_panel(self) -> None:
        events = json.loads(json.dumps(self.EVENTS))
        del events[2]["criteria"]["fp_cost"]
        errors = rg.validate_governance_events(events)
        self.assertTrue(any("authority/risk/fp_cost" in error for error in errors))

    def test_exemption_requires_rule_version_and_risk(self) -> None:
        event = {
            "id": "RG-0005", "event": "exemption_granted", "rule_id": "ST-01",
            "decided_by": "user", "confirmed_at": "2026-08-22T12:00:00Z",
            "rationale": "declared idempotent batch operation",
        }
        errors = rg.validate_governance_events([event])
        self.assertTrue(any("rule_version" in error for error in errors))
        self.assertTrue(any("risk" in error for error in errors))
        event.update({"rule_version": 2,
                      "risk": "duplicate side effects accepted for the drill env"})
        self.assertEqual(rg.validate_governance_events([event]), [])

    def test_candidate_events_require_evidence_refs(self) -> None:
        errors = rg.validate_governance_events(
            self._mutate(evidence_refs=[]))
        self.assertTrue(any("evidence_refs" in error for error in errors))

    def test_malformed_json_line_raises(self) -> None:
        with self.assertRaises(ValueError):
            rg.parse_governance_log('{"id": "RG-0001"\n')


class G8GovernanceRefTests(unittest.TestCase):
    """The S1 hook, wired in S5: machine-enforced entries must reference a
    promote -> machine-enforced adjudication in the governance log."""

    SYNTHETIC_ENTRY = """
## ST-01 — In-flight re-trigger guard

```yaml
id: ST-01
version: 2
title: In-flight re-trigger guard
capability-domain: D4
executes-in: D4:interaction
authority: platform-convention
applicability-applicable: spec L4 declares an async operation
applicability-not-applicable: no async declaration (reason required)
applicability-blocked: interaction trace unavailable and source insufficient
check-type: protocol-check
evidence-layers: interaction>=1, source>=1
severity-default: S2 / fact
owner: spec -> R2; implementation -> R4
provenance: promoted-from-findings
status: machine-enforced
governance-ref: RG-0004
related: []
history: 1 | 2026-08-14 | refine | advisory registration; 2 | 2026-08-22 | refine | machine-enforced promotion
```
"""

    def _registry(self, text: str) -> list:
        return rules_registry.parse_registry(text)

    def _events(self) -> list[dict]:
        return rg.parse_governance_log(
            GOVERNANCE_FIXTURE.read_text(encoding="utf-8"))

    def test_machine_enforced_ref_resolves_to_the_promotion(self) -> None:
        entries = self._registry(self.SYNTHETIC_ENTRY)
        errors = rules_registry.validate_registry(entries, self._events())
        self.assertEqual(
            [error for error in errors if "governance-ref" in error], [])

    def test_wrong_ref_is_rejected(self) -> None:
        text = self.SYNTHETIC_ENTRY.replace(
            "governance-ref: RG-0004", "governance-ref: RG-0003")
        errors = rules_registry.validate_registry(
            self._registry(text), self._events())
        self.assertTrue(any("does not resolve" in error for error in errors))

    def test_missing_ref_is_rejected(self) -> None:
        text = self.SYNTHETIC_ENTRY.replace("governance-ref: RG-0004\n", "")
        errors = rules_registry.validate_registry(
            self._registry(text), self._events())
        self.assertTrue(any("requires a governance" in error for error in errors))

    def test_version_pin_drift_is_rejected(self) -> None:
        text = self.SYNTHETIC_ENTRY.replace("version: 2", "version: 3", 1)
        errors = rules_registry.validate_registry(
            self._registry(text), self._events())
        self.assertTrue(any("pins ST-01@2" in error for error in errors))

    def test_shipped_registry_stays_dormant_but_wired(self) -> None:
        # 13 entries, all advisory/placeholder: passing governance events
        # changes nothing (no machine-enforced entry to resolve) — the
        # hook is wired and waiting for the first promotion.
        entries = rules_registry.parse_registry(REGISTRY_TEXT)
        self.assertFalse(any(
            entry.status == "machine-enforced" for entry in entries))
        without = rules_registry.validate_registry(entries)
        with_events = rules_registry.validate_registry(entries, self._events())
        self.assertEqual(without, [])
        self.assertEqual(with_events, [])


class SeverityNewAxisOnlyTests(unittest.TestCase):
    """Issue #40: G2/G4 only accept S3|S2|S1|S0 — the legacy spellings
    are structural errors (ADR-0028, breaking)."""

    def test_axis_only_maps_new_values(self) -> None:
        for value in ("S3", "S2", "S1", "S0"):
            self.assertEqual(severity_axis(value), value)
        for legacy in ("high (blocking)", "high", "med", "low"):
            self.assertIsNone(severity_axis(legacy))

    def _probe(self, severity: str, disposition: str = "") -> set[str]:
        block = (
            "issue:    probe\nsource:   components\nfix:      fix it\n"
            f"severity: {severity}\n"
        )
        if disposition:
            block += f"disposition: {disposition}\n"
        text = ("# pb\n\n## Findings\n\n```text\n" + block
                + "```\n\n## Verdict\n\n**Recirculate.**\n")
        return {finding.rule_id for finding in check_pointback(text, 0)}

    def test_legacy_values_are_structural_errors(self) -> None:
        for legacy in ("high (blocking)", "high", "med", "low"):
            rules = self._probe(legacy)
            self.assertIn("G2.finding_invalid_severity", rules)
            self.assertNotIn("G2.s3_needs_disposition", rules)

    def test_legacy_blocking_no_longer_closes(self) -> None:
        # the removed alias must not resurrect G4 blocking behaviour
        text = (
            "# pb\n\n## Findings\n\n```text\nissue: probe\nsource: s\n"
            "fix: f\nseverity: high (blocking)\n```\n\n## Verdict\n\n"
            "**Pass.**\n"
        )
        rules = {finding.rule_id for finding in check_pointback(text, 0)}
        self.assertIn("G2.finding_invalid_severity", rules)
        self.assertNotIn("G4.missing_closure_trail", rules)

    def test_new_axis_passes_and_s3_needs_disposition(self) -> None:
        for value in ("S2", "S1", "S0"):
            self.assertNotIn(
                "G2.finding_invalid_severity", self._probe(value))
        self.assertIn("G2.s3_needs_disposition", self._probe("S3"))
        self.assertNotIn("G2.s3_needs_disposition",
                         self._probe("S3", "blocking"))

    def test_migrated_pass_fixture_still_validates(self) -> None:
        # the S0-era fixture carries the migrated axis values end to end
        text = (FIXTURE_PASS / "point-back.md").read_text(encoding="utf-8")
        self.assertEqual(check_pointback(text, 5), [])


class AggregateCandidatesTests(unittest.TestCase):
    """The additive JSON key on scripts/aggregate_runs.py (end to end)."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.scratch = self.cwd / ".scratch" / "s5-effort" / "dogfood"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _make_run(self, name: str, findings: str) -> Path:
        run_dir = self.scratch / name
        run_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FIXTURE_PASS / "spec.md", run_dir / "spec.md")
        pb = (FIXTURE_PASS / "point-back.md").read_text(encoding="utf-8")
        pb = pb.rstrip() + "\n\n## More findings\n\n```text\n" + findings + "\n```\n"
        (run_dir / "point-back.md").write_text(pb, encoding="utf-8")
        return run_dir

    def _aggregate(self, *extra: str) -> dict:
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        proc = subprocess.run(
            [sys.executable, str(AGGREGATE), *extra],
            cwd=self.cwd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=env, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return json.loads(proc.stdout)

    def test_existing_keys_unchanged_and_view_added(self) -> None:
        self._make_run("2026-01-01-001", f"issue: {SIGNAL}\nsource: components\nfix: f\nseverity: S2\n")
        payload = self._aggregate()
        for key in ("generated", "scratch_root", "runs_total", "runs",
                    "rollup", "repeat_blockers"):
            self.assertIn(key, payload)
        view = payload["learning_candidates"]
        self.assertIn("threshold", view)
        self.assertEqual(view["threshold"]["distinct_runs"], 3)

    def test_qualifying_candidate_end_to_end(self) -> None:
        finding = f"issue: {SIGNAL}\nsource: components\nfix: f\nseverity: S2\n"
        for name in ("2026-01-01-001", "2026-01-02-002", "2026-01-03-003"):
            self._make_run(name, finding)
        # without contexts: conservative — the context gap is reported
        payload = self._aggregate()
        self.assertEqual(payload["learning_candidates"]["qualifying"], [])
        below = payload["learning_candidates"]["below_threshold"]
        self.assertTrue(any(
            "distinct_task_contexts 1 < 2" in candidate["gaps"]
            for candidate in below))

        # with the context map (contract/spec/manifest provenance): qualifies
        contexts = self.cwd / "contexts.json"
        contexts.write_text(json.dumps({
            "2026-01-01-001": "data-export",
            "2026-01-02-002": "data-export",
            "2026-01-03-003": "batch-delete",
        }), encoding="utf-8")
        payload = self._aggregate("--candidate-contexts", str(contexts))
        qualifying = payload["learning_candidates"]["qualifying"]
        # the shared fixture findings ride along (same text across the same
        # three runs and two contexts — they qualify by the same rule); the
        # probe signal must be among them with the exact threshold face
        by_key = {candidate["signal_key"]: candidate
                  for candidate in qualifying}
        probe = by_key[lc.normalize(SIGNAL)]
        self.assertTrue(probe["qualifies"])
        self.assertEqual(probe["distinct_runs"], 3)
        self.assertEqual(probe["distinct_task_contexts"], 2)
        self.assertEqual(probe["unexplained_false_positives"], 0)

    def test_markdown_view_lists_the_queue(self) -> None:
        finding = f"issue: {SIGNAL}\nsource: components\nfix: f\nseverity: S2\n"
        for name in ("2026-01-01-001", "2026-01-02-002", "2026-01-03-003"):
            self._make_run(name, finding)
        contexts = self.cwd / "contexts.json"
        contexts.write_text(json.dumps({
            "2026-01-01-001": "data-export",
            "2026-01-02-002": "batch-delete",
            "2026-01-03-003": "settings-import",
        }), encoding="utf-8")
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        proc = subprocess.run(
            [sys.executable, str(AGGREGATE), "--md",
             "--candidate-contexts", str(contexts)],
            cwd=self.cwd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=env, check=False,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("## Rule candidates (derived, vNext S5)", proc.stdout)
        self.assertIn("| CAND-", proc.stdout)


if __name__ == "__main__":
    unittest.main()
