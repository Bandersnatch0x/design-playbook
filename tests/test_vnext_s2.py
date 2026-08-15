#!/usr/bin/env python3
"""vNext S2 unit tests: DD entry parsing, G10 gate, R/C/E tier obligations,
preview riding, R3 supersedes re-entry, stale three-exit review.

Issue #37 exit criteria: these hang off the existing CI unit-test step
(same wiring as test_vnext_s1.py). Black-box where a CLI exists
(validate_run.py / g10_design_decisions.py); in-process for the parsers.
"""
from __future__ import annotations

import json
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

from design_playbook.scripts.dd_entries import (  # noqa: E402
    collect_e_signals,
    dd_refs_in_pointback,
    parse_dd_entries,
)
from design_playbook.scripts.g10_design_decisions import check_g10  # noqa: E402

P2_RUN = PKG / "examples" / "export-entry" / "run"
P3_BASE = PKG / "examples" / "export-upgrade"
P3_RUN = P3_BASE / "run"
P3_REPORT = (P3_RUN / "decision-report.md").read_text(encoding="utf-8")
P3_POINTBACK = (P3_RUN / "point-back.md").read_text(encoding="utf-8")
P3_STATE = json.loads(
    (P3_RUN / "design-baseline" / "state.json").read_text(encoding="utf-8"))
SHA = "a" * 64
OTHER_SHA = "b" * 64


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _rules(report: str, **kwargs) -> set[str]:
    return {f.rule_id for f in check_g10(report, **kwargs)}


R_BLOCK = """## DD-0001 — trigger

```yaml
id: DD-0001
tier: record
question: trigger shape
status: confirmed-agent
constraints:
  baseline: waived: none bound this run
  spec: [l4.export-trigger]
selection: {candidate: Button (icon + label), rationale: role table names it}
confirmation:
  kind: agent
  via: agent-record
  confirmed_at: 2026-08-14T10:16:00Z
supersedes: null
```
"""

C_BLOCK = """## DD-0002 — naming

```yaml
id: DD-0002
tier: compare
question: file naming
status: confirmed-agent
constraints:
  baseline: DESIGN.md sha256:%s
  spec: [l1.target_user]
candidates:
  - {id: A, source: agent, created_at: 2026-08-14T10:20:00Z, fidelity: description, summary: range name, deviations: none, assets: []}
  - {id: B, source: agent, created_at: 2026-08-14T10:20:00Z, fidelity: description, summary: fixed name plus stamp, deviations: none, assets: []}
comparison:
  axes:
    - {axis: archive lookup (l1.target_user), A: supports, B: hurts}
  tradeoffs: "A trades naming freedom for readability"
selection:
  candidate: A
  rationale: archive lookup is the primary task
  rejected:
    - {candidate: B, reason: needs rename first}
confirmation:
  kind: agent
  via: agent-record
  confirmed_at: 2026-08-14T10:22:00Z
supersedes: null
```
""" % SHA


def _e_block(entry_id: str = "DD-0003", *, tier: str = "explore",
             status: str = "confirmed-user", supersedes: str = "null",
             via: str = "report-batch", stale: str = "",
             review: str = "") -> str:
    lines = [
        f"## {entry_id} — question",
        "",
        "```yaml",
        f"id: {entry_id}",
        f"tier: {tier}",
        "question: status composition",
        f"status: {status}",
        "constraints:",
        f"  baseline: DESIGN.md sha256:{SHA}",
        "  spec: [l6.c1]",
        "  rules: [CRAFT-01@1]",
        "candidates:",
        "  - {id: A, source: agent, created_at: 2026-08-14T10:58:00Z, fidelity: description, summary: inline, deviations: none, assets: []}",
        "  - {id: B, source: provider-adapter, adapter: provider-a, created_at: 2026-08-14T11:00:00Z, fidelity: sketch, summary: global region, deviations: none, assets: []}",
        "comparison:",
        "  axes:",
        "    - {axis: task fit (l1.scenes), A: hurts, B: supports}",
        "  tradeoffs: \"A trades context for space; B trades distance for reach\"",
        "selection:",
        "  candidate: B",
        "  rationale: task-fit axis supports B",
        "  rejected:",
        "    - {candidate: A, reason: loses state across views}",
        "confirmation:",
        "  kind: user",
        f"  via: {via}",
        "  confirmed_at: 2026-08-14T11:06:00Z",
        f"supersedes: {supersedes}",
    ]
    if stale:
        lines.append(f"stale: {stale}")
    if review:
        lines.append(f"stale_review: {review}")
    lines.append("```")
    return "\n".join(lines) + "\n"


def _report(*blocks: str) -> str:
    return ("# Decision report\n\n```text\nscene: fixture\nbaseline-changes:"
            " none\n```\n\n" + "\n".join(blocks))


class DDEntryParseTests(unittest.TestCase):
    def test_p2_fixture_entries_parse(self) -> None:
        entries = parse_dd_entries(
            (P2_RUN / "decision-report.md").read_text(encoding="utf-8"))
        self.assertEqual([entry.id for entry in entries],
                         ["DD-0001", "DD-0002"])
        record, compare = entries
        self.assertEqual(record.tier, "record")
        # R-tier minimal form: single-line flow-map selection parses
        self.assertEqual(record.selection["candidate"], "Button (icon + label)")
        self.assertTrue(record.selection["rationale"])
        self.assertEqual(record.supersedes_ref, "")
        self.assertEqual(compare.tier, "compare")
        self.assertEqual(compare.candidate_ids(), ["A", "B"])
        self.assertEqual(len(compare.comparison_axes), 2)
        self.assertEqual(compare.rejected[0]["candidate"], "B")
        self.assertEqual(compare.rules_refs, ("CRAFT-01@1",))

    def test_p3_fixture_entries_parse(self) -> None:
        entries = parse_dd_entries(P3_REPORT)
        self.assertEqual([entry.id for entry in entries],
                         ["DD-0003", "DD-0004"])
        old, new = entries
        self.assertEqual(old.status, "invalidated")
        self.assertEqual(old.preview_link[0], 1)
        self.assertEqual(new.supersedes_ref, "DD-0003")
        self.assertEqual(new.preview_link[0], 2)
        self.assertEqual(old.stale_review["exit"], "keep")
        self.assertIn("sha256:", old.stale_review["note"])
        provider = old.candidates[1]
        self.assertEqual(provider["source"], "provider-adapter")
        self.assertEqual(provider["adapter"], "provider-a")
        self.assertIn("sha256:", provider["assets"])

    def test_null_supersedes_normalizes_empty(self) -> None:
        entry = parse_dd_entries(_report(R_BLOCK))[0]
        self.assertEqual(entry.supersedes, "null")
        self.assertEqual(entry.supersedes_ref, "")

    def test_report_without_entries_is_ignored(self) -> None:
        text = "# Decision report\n\n```text\nscene: x\n```\n"
        self.assertEqual(parse_dd_entries(text), [])
        self.assertEqual(check_g10(text), [])

    def test_folded_flow_map_items_parse_like_single_line(self) -> None:
        # Issue #44: a `- {…}` item may fold onto following lines while its
        # braces stay unbalanced (the shape the decisions.md schema example
        # shows). The folded parse must equal the single-line parse.
        single = parse_dd_entries(_report(C_BLOCK))[0]
        folded_text = C_BLOCK.replace(
            "  - {id: B, source: agent, created_at: 2026-08-14T10:20:00Z,"
            " fidelity: description, summary: fixed name plus stamp,"
            " deviations: none, assets: []}\n",
            "  - {id: B, source: agent, created_at: 2026-08-14T10:20:00Z,\n"
            "     fidelity: description, summary: fixed name plus stamp,\n"
            "     deviations: none, assets: []}\n",
        ).replace(
            "    - {axis: archive lookup (l1.target_user), A: supports,"
            " B: hurts}\n",
            "    - {axis: archive lookup (l1.target_user), A: supports,\n"
            "       B: hurts}\n",
        ).replace(
            "    - {candidate: B, reason: needs rename first}\n",
            "    - {candidate: B,\n       reason: needs rename first}\n",
        )
        folded = parse_dd_entries(_report(folded_text))[0]
        self.assertEqual(folded.candidates, single.candidates)
        self.assertEqual(folded.comparison_axes, single.comparison_axes)
        self.assertEqual(folded.rejected, single.rejected)
        self.assertEqual(_rules(_report(folded_text)), set())

    def test_unterminated_flow_map_fold_fails_closed(self) -> None:
        # Dropping the closing brace leaves the fold unterminated: the item
        # swallows the rest of the block and the shape checks reject it
        # (never a silent partial parse).
        broken = C_BLOCK.replace(
            "summary: fixed name plus stamp, deviations: none, assets: []}\n",
            "summary: fixed name plus stamp, deviations: none, assets: []\n",
        )
        rules = _rules(_report(broken))
        self.assertIn("G10.bad_candidate", rules)
        self.assertIn("G10.missing_comparison", rules)


class TierSignalTests(unittest.TestCase):
    def test_t3_and_reentry_signals_are_machine_judgeable(self) -> None:
        events = [{"event": "asked", "question_id": "Q9", "tier": "T3",
                   "text": "visual direction"}]
        signals = collect_e_signals(
            parse_dd_entries(_report(_e_block())),
            shaping_events=events,
            pointback_text="issue: x\nsource: design\ndd: DD-0003\n",
            report_text=_report(_e_block()),
        )
        self.assertIn("upstream-route", signals.fired)
        self.assertIn("re-entry", signals.fired)
        self.assertEqual(signals.dd_targets, ("DD-0003",))
        self.assertEqual(signals.t3_questions, ("Q9",))

    def test_baseline_change_signal(self) -> None:
        text = _report(_e_block()).replace(
            "baseline-changes: none", "baseline-changes: enable status region")
        signals = collect_e_signals(
            parse_dd_entries(text), report_text=text)
        self.assertTrue(signals.baseline_changed)
        self.assertIn("baseline-conflict", signals.fired)

    def test_baseline_change_none_tolerates_trailing_note(self) -> None:
        # Issue #44: commentary after the none value token never turns
        # none into a declared change; lookalike values stay fail-closed.
        for note in ("none", "none — no change this run",
                     "none（本 run 无变更）"):
            text = _report(_e_block()).replace(
                "baseline-changes: none", f"baseline-changes: {note}")
            signals = collect_e_signals(
                parse_dd_entries(text), report_text=text)
            self.assertFalse(signals.baseline_changed, note)
            self.assertNotIn("baseline-conflict", signals.fired)
        for value in ("enable status region", "nonempty", "none-such"):
            text = _report(_e_block()).replace(
                "baseline-changes: none", f"baseline-changes: {value}")
            self.assertTrue(collect_e_signals(
                parse_dd_entries(text), report_text=text).baseline_changed,
                value)

    def test_declared_deviations_raise_identity_signal(self) -> None:
        block = _e_block().replace("deviations: none, assets: []}",
                                   "deviations: drops toast convention, assets: []}", 1)
        signals = collect_e_signals(parse_dd_entries(_report(block)))
        self.assertIn("identity", signals.fired)


class TierObligationTests(unittest.TestCase):
    def test_record_tier_requires_rationale(self) -> None:
        broken = R_BLOCK.replace(
            "rationale: role table names it", "rationale: ")
        rules = _rules(_report(broken))
        self.assertIn("G10.missing_selection", rules)

    def test_compare_tier_needs_two_candidates(self) -> None:
        broken = C_BLOCK.replace(
            "  - {id: B, source: agent, created_at: 2026-08-14T10:20:00Z,"
            " fidelity: description, summary: fixed name plus stamp,"
            " deviations: none, assets: []}\n", "")
        rules = _rules(_report(broken))
        self.assertIn("G10.candidate_count", rules)

    def test_compare_tier_needs_tradeoff_statement(self) -> None:
        broken = C_BLOCK.replace(
            'tradeoffs: "A trades naming freedom for readability"',
            "tradeoffs: \"\"")
        rules = _rules(_report(broken))
        self.assertIn("G10.missing_comparison", rules)

    def test_compare_tier_needs_rejection_reason(self) -> None:
        broken = C_BLOCK.replace(
            "- {candidate: B, reason: needs rename first}",
            "- {candidate: B, reason: }")
        rules = _rules(_report(broken))
        self.assertIn("G10.missing_rejected", rules)

    def test_explore_tier_requires_user_confirmation(self) -> None:
        broken = _e_block().replace("kind: user", "kind: agent")
        rules = _rules(_report(broken))
        self.assertIn("G10.e_needs_user_confirmation", rules)

    def test_rc_tier_rejects_user_confirmation(self) -> None:
        broken = R_BLOCK.replace("kind: agent", "kind: user")
        rules = _rules(_report(broken))
        self.assertIn("G10.rc_confirmation_not_agent", rules)
        broken_status = R_BLOCK.replace(
            "status: confirmed-agent", "status: confirmed-user")
        self.assertIn(
            "G10.bad_confirmation", _rules(_report(broken_status)))

    def test_provider_candidate_needs_anonymous_adapter(self) -> None:
        broken = _e_block().replace("adapter: provider-a, ", "")
        rules = _rules(_report(broken))
        self.assertIn("G10.bad_candidate", rules)
        named = _e_block().replace("adapter: provider-a", "adapter: SomeVendor")
        self.assertIn("G10.bad_candidate", _rules(_report(named)))

    def test_unknown_candidate_selection_rejected(self) -> None:
        broken = _e_block().replace("  candidate: B", "  candidate: C")
        self.assertIn("G10.unknown_candidate", _rules(_report(broken)))

    def test_enum_and_reference_negatives(self) -> None:
        self.assertIn(
            "G10.invalid_tier",
            _rules(_report(_e_block(tier="deep-dive"))))
        self.assertIn(
            "G10.invalid_status",
            _rules(_report(_e_block(status="done"))))
        self.assertIn(
            "G10.bad_rules_ref",
            _rules(_report(_e_block().replace(
                "rules: [CRAFT-01@1]", "rules: [CRAFT-99@1]"))))
        self.assertIn(
            "G10.bad_rules_ref",
            _rules(_report(_e_block().replace(
                "rules: [CRAFT-01@1]", "rules: [CRAFT-01@9]"))))
        self.assertIn(
            "G10.bad_baseline",
            _rules(_report(_e_block().replace(
                f"baseline: DESIGN.md sha256:{SHA}",
                "baseline: DESIGN.md (old)"))))

    def test_duplicate_id_rejected(self) -> None:
        rules = _rules(_report(R_BLOCK, R_BLOCK))
        self.assertIn("G10.duplicate_id", rules)

    def test_bad_heading_id_surface(self) -> None:
        text = _report(R_BLOCK) + "\n## DD-1 — broken\n\n```yaml\nid: DD-1\n```\n"
        self.assertIn("G10.bad_id", _rules(text))


class PositiveDDFieldTests(unittest.TestCase):
    """Issue #44: ``dd:`` is the R3 challenge channel, never an
    observation link — positive (S0) findings must not carry it."""

    def _pointback(self, severity: str) -> str:
        return (
            "## Positive findings\n\n```text\n"
            "issue:    follows the bound baseline\n"
            "source:   design\n"
            "fix:      none — observation link only\n"
            f"severity: {severity}\n"
            "dd:       DD-0001\n"
            "```\n"
        )

    def test_dd_on_s0_is_a_structural_error(self) -> None:
        rules = _rules(_report(R_BLOCK), pointback_text=self._pointback("S0"))
        self.assertIn("G10.dd_on_positive_finding", rules)
        # the misread challenge face no longer fires alongside the error
        self.assertNotIn("G10.dd_challenge_unresolved", rules)

    def test_dd_on_non_positive_still_reads_as_challenge(self) -> None:
        rules = _rules(_report(R_BLOCK), pointback_text=self._pointback("S2"))
        self.assertNotIn("G10.dd_on_positive_finding", rules)
        self.assertIn("G10.dd_challenge_unresolved", rules)

    def test_positive_dd_never_fires_reentry_signal(self) -> None:
        signals = collect_e_signals(
            parse_dd_entries(_report(R_BLOCK)),
            pointback_text=self._pointback("S0"),
            report_text=_report(R_BLOCK),
        )
        self.assertEqual(signals.dd_targets, ())
        self.assertNotIn("re-entry", signals.fired)
        self.assertEqual(
            dd_refs_in_pointback(self._pointback("S2")), ("DD-0001",))


class SupersedesTests(unittest.TestCase):
    def test_unknown_and_active_targets_rejected(self) -> None:
        self.assertIn(
            "G10.supersedes_unknown",
            _rules(_report(_e_block(supersedes="DD-0099"))))
        active = _report(
            _e_block("DD-0003", status="confirmed-user", supersedes="null"),
            _e_block("DD-0004", supersedes="DD-0003"),
        )
        rules = _rules(active, pointback_text="dd: DD-0003\n")
        self.assertIn("G10.supersedes_target_active", rules)
        self.assertIn("G10.dd_challenge_unresolved", rules)

    def test_supersedes_cycle_rejected(self) -> None:
        cyclic = _report(
            _e_block("DD-0003", status="invalidated", supersedes="DD-0004"),
            _e_block("DD-0004", status="invalidated", supersedes="DD-0003"),
        )
        self.assertIn("G10.supersedes_cycle", _rules(cyclic))

    def test_retired_entry_needs_superseder(self) -> None:
        lonely = _report(_e_block(status="invalidated"))
        self.assertIn("G10.retired_without_superseder", _rules(lonely))

    def test_revision_of_challenged_entry_must_stay_explore(self) -> None:
        report = _report(
            _e_block("DD-0003", status="invalidated", supersedes="null"),
            _e_block("DD-0004", tier="compare", status="confirmed-agent",
                     supersedes="DD-0003", via="agent-record"),
        )
        rules = _rules(report, pointback_text="dd: DD-0003\n")
        self.assertIn("G10.dd_revision_not_explore", rules)
        self.assertNotIn("G10.dd_challenge_unresolved", rules)

    def test_unknown_dd_reference_rejected(self) -> None:
        self.assertIn(
            "G10.dd_ref_unknown",
            _rules(_report(_e_block()), pointback_text="dd: DD-0042\n"))

    def test_cross_run_reference_is_structural_only(self) -> None:
        # <run>/DD-#### cross-run refs cannot resolve here; no finding fires
        self.assertEqual(
            _rules(_report(_e_block()),
                   pointback_text="dd: prior-run/DD-0003\n"), set())


class StaleReviewTests(unittest.TestCase):
    def test_stale_without_review_rejected(self) -> None:
        rules = _rules(_report(_e_block(
            stale="source hash drift 2026-08-14")))
        self.assertIn("G10.stale_no_review", rules)

    def test_keep_exit_cites_new_sha(self) -> None:
        good = _e_block(
            stale="drift detected",
            review=f"{{exit: keep, note: re-check passed; rebound sha256:{SHA}}}")
        self.assertEqual(_rules(_report(good)), set())
        missing = _e_block(
            stale="drift detected",
            review="{exit: keep, note: still conforms}")
        self.assertIn("G10.stale_keep_missing_sha", _rules(_report(missing)))

    def test_drift_state_comparison(self) -> None:
        state = {"status": "ready",
                 "baseline": {"sha256": OTHER_SHA}}
        # entry pins SHA, binding is OTHER_SHA, no stale mark -> flagged
        rules = _rules(_report(_e_block()),
                       baseline_state=state)
        self.assertIn("G10.stale_unmarked", rules)
        marked = _e_block(
            stale="drift detected",
            review=f"{{exit: keep, note: rebound sha256:{OTHER_SHA}}}")
        rules = _rules(_report(marked), baseline_state=state)
        self.assertEqual(rules, set())

    def test_keep_exit_must_cite_the_current_binding(self) -> None:
        state = {"status": "ready", "baseline": {"sha256": OTHER_SHA}}
        wrong = _e_block(
            stale="drift detected",
            review=f"{{exit: keep, note: rebound sha256:{SHA}}}")
        rules = _rules(_report(wrong), baseline_state=state)
        self.assertIn("G10.stale_keep_missing_sha", rules)

    def test_revise_exit_requires_superseder(self) -> None:
        lonely = _e_block(
            stale="drift detected",
            review="{exit: revise, note: composition changed}")
        self.assertIn(
            "G10.stale_revise_no_superseder", _rules(_report(lonely)))
        pair = _report(
            _e_block("DD-0003", status="invalidated", stale="drift",
                     review="{exit: revise, note: composition changed}"),
            _e_block("DD-0004", supersedes="DD-0003"),
        )
        self.assertNotIn("G10.stale_revise_no_superseder", _rules(pair))

    def test_escalate_exit_needs_note(self) -> None:
        bare = _e_block(stale="drift detected",
                        review="{exit: escalate, note: }")
        self.assertIn("G10.stale_no_review", _rules(_report(bare)))
        noted = _e_block(
            stale="drift detected",
            review="{exit: escalate, note: question back at direction level}")
        self.assertEqual(_rules(_report(noted)), set())

    def test_p3_fixture_stale_reviews_pass(self) -> None:
        self.assertEqual(_rules(P3_REPORT, baseline_state=P3_STATE), set())


class PreviewRidingTests(unittest.TestCase):
    def test_decision_id_linkage_against_confirm_record(self) -> None:
        preview = P3_RUN / "preview"
        self.assertEqual(
            _rules(P3_REPORT, preview_dir=preview,
                   pointback_text=P3_POINTBACK),
            set())
        # break only DD-0004's link: wrong decision_id in via
        did2 = parse_dd_entries(P3_REPORT)[1].preview_link[1]
        broken = P3_REPORT.replace(f"decision_id:{did2}",
                                   "decision_id:" + "0" * len(did2))
        rules = _rules(broken, preview_dir=preview)
        self.assertIn("G10.preview_link_broken", rules)

    def test_missing_confirm_file_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "preview"
            empty.mkdir()
            rules = _rules(P3_REPORT, preview_dir=empty)
            self.assertIn("G10.preview_link_broken", rules)

    def test_absent_adapter_falls_back_to_report_batch(self) -> None:
        # preview_dir None (adapter absent): no linkage check fires even
        # though the fixture entries ride transactions on record
        self.assertEqual(_rules(P3_REPORT, preview_dir=None), set())
        batch = _report(_e_block(via="report-batch"))
        self.assertEqual(_rules(batch), set())

    def test_e_confirmation_via_bad_channel_rejected(self) -> None:
        broken = _e_block(via="verbal confirmation")
        self.assertIn("G10.bad_confirmation", _rules(_report(broken)))


class RunProfileSignalTests(unittest.TestCase):
    def test_p1_profile_rejects_decision_entries(self) -> None:
        self.assertIn(
            "G10.p1_decision_entries",
            _rules(_report(_e_block()), run_profile_tier="P1"))
        self.assertEqual(
            _rules(_report(_e_block()), run_profile_tier="P3"), set())

    def test_t3_route_requires_explore_entry(self) -> None:
        events = [{"event": "asked", "question_id": "Q9", "tier": "T3"}]
        rules = _rules(_report(R_BLOCK), shaping_events=events)
        self.assertIn("G10.t3_route_needs_explore", rules)
        rules = _rules(_report(R_BLOCK, _e_block()), shaping_events=events)
        self.assertNotIn("G10.t3_route_needs_explore", rules)

    def test_baseline_change_requires_explore_entry(self) -> None:
        text = _report(R_BLOCK).replace("baseline-changes: none",
                                        "baseline-changes: status region on")
        self.assertIn("G10.baseline_change_needs_explore", _rules(text))


class FixtureWalkthroughTests(unittest.TestCase):
    """Issue #37: the fixture run demonstrates the whole E-tier arc."""

    def _validate(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(PKG / "scripts" / "validate_run.py"),
                str(P3_RUN / "spec.md"),
                str(P3_RUN / "point-back.md"),
                "--preview-dir", str(P3_RUN / "preview"),
                "--decision-report", str(P3_RUN / "decision-report.md"),
                "--evidence-dir", str(P3_RUN / "evidence"),
                "--run-root", str(P3_RUN),
                "--contract-project", str(P3_BASE / "project"),
                "--contract-run", str(P3_RUN),
                "--shaping-dir", str(P3_RUN / "shaping"),
                *extra,
            ],
            capture_output=True, text=True, check=False,
        )

    def test_full_p3_chain_reaches_pass_with_preview(self) -> None:
        result = self._validate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("RUN OK", result.stdout)

    def test_strict_mode_passes(self) -> None:
        # preview occurred on this fixture, so --require-preview can fire
        result = self._validate("--strict")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_g10_breaks_when_decision_id_link_drifts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "run"
            shutil.copytree(P3_RUN, run)
            did2 = parse_dd_entries(P3_REPORT)[1].preview_link[1]
            _write(run / "decision-report.md",
                   P3_REPORT.replace(f"decision_id:{did2}",
                                     "decision_id:" + "f" * len(did2)))
            result = subprocess.run(
                [sys.executable,
                 str(PKG / "scripts" / "validate_run.py"),
                 str(run / "spec.md"), str(run / "point-back.md"),
                 "--decision-report", str(run / "decision-report.md"),
                 "--run-root", str(run),
                 "--preview-dir", str(run / "preview")],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("G10", result.stdout)
            self.assertIn("provenance must match the transaction",
                          result.stdout)

    def test_g10_cli_on_fixture_run(self) -> None:
        import os

        env = dict(os.environ)
        env["PYTHONPATH"] = str(PKG) + os.pathsep + env.get("PYTHONPATH", "")
        result = subprocess.run(
            [sys.executable,
             str(PKG / "scripts" / "g10_design_decisions.py"),
             str(P3_RUN / "decision-report.md")],
            capture_output=True, text=True, check=False, env=env,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("G10 OK", result.stdout)

    def test_p2_fixture_chain_with_dd_blocks(self) -> None:
        # S2 extends the S1 P2 fixture in place: R/C entries pass G10 with
        # discovery via --run-root (no explicit --decision-report needed)
        result = subprocess.run(
            [sys.executable,
             str(PKG / "scripts" / "validate_run.py"),
             str(P2_RUN / "spec.md"), str(P2_RUN / "point-back.md"),
             "--evidence-dir", str(P2_RUN / "evidence"),
             "--run-root", str(P2_RUN),
             "--contract-project", str(P2_RUN.parent / "project"),
             "--contract-run", str(P2_RUN),
             "--shaping-dir", str(P2_RUN / "shaping")],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("RUN OK", result.stdout)

    def test_top_block_stays_verbatim_before_dd_blocks(self) -> None:
        text = (P2_RUN / "decision-report.md").read_text(encoding="utf-8")
        top_block = text.split("```text", 1)[1].split("```", 1)[0]
        for line in (
            "scene: ops console data export",
            "components:",
            "  batch export -> Button (single primary; busy state while exporting)",
            "  - hidden sensitive columns -> export.column_scope assumption acknowledged",
        ):
            self.assertIn(line, top_block)
        self.assertLess(text.index("```text"), text.index("## DD-0001"))


if __name__ == "__main__":
    unittest.main()
