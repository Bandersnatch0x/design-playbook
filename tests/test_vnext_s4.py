#!/usr/bin/env python3
"""vNext S4 unit tests: repair-round machine counting (two-round escalated
stop), G12 tier-boundary diff judgment (positive/negative criterion table),
E1-E6 escalation signals with run-profile upgrade accounting, and the
run-status re-entry narration (rounds / W-event counts / signals / waiting
states / close_reason).

Issue #39 exit criteria: these hang off the existing CI unit-test step
(same wiring as test_vnext_s1/s2/s3.py). Black-box where a CLI exists
(validate_run.py / run_status.py); in-process for the parsers and gate
functions.
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

from design_playbook.scripts.escalation_signals import (  # noqa: E402
    collect_signals,
    effective_tier,
    parse_routes,
    route_hits,
)
from design_playbook.scripts.g12_tier_boundary import (  # noqa: E402
    ContractTouch,
    check_g12,
    contract_touch,
    covering_tier,
)
from design_playbook.scripts.repair_rounds import (  # noqa: E402
    check_rounds,
    parse_close_reason,
    parse_round_facts,
)
from design_playbook.scripts.run_profile import (  # noqa: E402
    RunProfile,
    parse_run_profile,
)

UPGRADE_RUN = PKG / "examples" / "export-pointfix-upgrade" / "run"
STOP_RUN = PKG / "examples" / "export-retry-stop" / "run"
STOP_PB = (STOP_RUN / "point-back.md").read_text(encoding="utf-8")
UPGRADE_PB = (UPGRADE_RUN / "point-back.md").read_text(encoding="utf-8")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _rules(findings) -> set[str]:
    return {f.rule_id for f in findings}


def _finding_block(issue: str = "probe", *, severity: str = "S3",
                   disposition: str = "blocking", route: str = "",
                   rounds: str = "", extra: str = "") -> str:
    lines = [
        f"issue:    {issue}",
        "source:   components",
        "fix:      fix it",
        f"severity: {severity}",
    ]
    if disposition:
        lines.append(f"disposition: {disposition}")
    if route:
        lines.append(f"route:    {route}")
    if rounds:
        lines.append(f"rounds:   {rounds}")
    if extra:
        lines.append(extra)
    return "\n".join(lines) + "\n"


def _pointback(*blocks: str, verdict: str = "**Recirculate.**",
               close_reason: str = "") -> str:
    body = "# pb\n\n## Findings\n\n```text\n" + "\n```\n\n```text\n".join(
        blocks) + "\n```\n\n## Verdict\n\n" + verdict + "\n"
    if close_reason:
        body += f"\nclose_reason: {close_reason}\n"
    return body


class RepairRoundsTests(unittest.TestCase):
    """Machine counting of the two-round stop (loop-prototype 5.1 / 2.2)."""

    def test_stop_fixture_round_facts(self) -> None:
        facts = parse_round_facts(STOP_PB)
        self.assertEqual(facts.rounds_by_issue, (("导出失败后重试按钮点击无响应", 2),))
        self.assertEqual(facts.invalidated_rounds, (1, 2))
        self.assertEqual(facts.max_rounds, 2)
        self.assertEqual(facts.close_reason, "escalated-stop")
        self.assertEqual(check_rounds(STOP_PB), [])

    def test_upgrade_fixture_rounds_ride_the_normal_chain(self) -> None:
        # one repair round -> closure -> Pass: the existing chain keeps
        # working with the round annotation present.
        facts = parse_round_facts(UPGRADE_PB)
        self.assertEqual(facts.rounds_by_issue, (("空数据集导出无反馈且不产出文件", 1),))
        self.assertEqual(facts.max_rounds, 1)
        self.assertEqual(facts.close_reason, "pass")
        self.assertEqual(check_rounds(UPGRADE_PB), [])

    def test_two_round_unclosed_blocking_requires_the_stop(self) -> None:
        text = _pointback(_finding_block(rounds="2"))
        self.assertIn("G4.round_stop_missing", _rules(check_rounds(text)))
        narrated = _pointback(_finding_block(rounds="2"),
                              close_reason="escalated-stop")
        self.assertEqual(check_rounds(narrated), [])

    def test_orphan_stop_rejected(self) -> None:
        text = _pointback(_finding_block(rounds="1"),
                          close_reason="escalated-stop")
        self.assertIn("G4.round_stop_orphan", _rules(check_rounds(text)))
        no_rounds = _pointback(_finding_block(),
                               close_reason="escalated-stop")
        self.assertIn("G4.round_stop_orphan", _rules(check_rounds(no_rounds)))

    def test_pass_never_carries_the_stop(self) -> None:
        text = _pointback(_finding_block(rounds="2"),
                          verdict="**Pass.**",
                          close_reason="escalated-stop")
        rules = _rules(check_rounds(text))
        self.assertIn("G4.round_stop_pass_conflict", rules)

    def test_closed_after_two_rounds_is_the_normal_chain(self) -> None:
        text = _pointback(
            _finding_block(rounds="2"),
            verdict="**Pass.**",
            close_reason="pass",
        ) + "\n- closes: probe -> recirculate -> fix -> re-eval -> 0 blocking\n"
        self.assertEqual(check_rounds(text), [])

    def test_invalid_counts_and_values(self) -> None:
        self.assertIn("G4.rounds_invalid",
                      _rules(check_rounds(_pointback(
                          _finding_block(rounds="soon")))))
        self.assertIn("G4.close_reason_invalid",
                      _rules(check_rounds(_pointback(
                          _finding_block(rounds="0"),
                          close_reason="gave-up"))))
        text = (_pointback(_finding_block(rounds="1")) + "\ninvalidated:\n"
                "  - criterion: L6.1\n    artifacts: []\n"
                "    reason: r\n    round: 0\n")
        self.assertIn("G4.rounds_invalid", _rules(check_rounds(text)))

    def test_advisory_rounds_never_stop(self) -> None:
        block = _finding_block(severity="S2", disposition="advisory",
                               rounds="2")
        self.assertEqual(
            check_rounds(_pointback(block, close_reason="")),
            [])

    def test_legacy_reports_stay_silent(self) -> None:
        legacy = "# pb\n\n## Findings\n\n```text\nissue: a\nsource: s\n" \
                 "fix: f\nseverity: high (blocking)\n```\n\n## Verdict\n\n" \
                 "Recirculate\n"
        self.assertEqual(check_rounds(legacy), [])
        self.assertIsNone(parse_close_reason(legacy))


class EscalationSignalTests(unittest.TestCase):
    """E1-E4 derivation from findings, E6 from recorded re-grades."""

    def test_route_parsing_and_hits(self) -> None:
        text = _pointback(
            _finding_block(route="R4"),
            _finding_block("two layers", severity="S2",
                           disposition="advisory", route="R2-structural R4"),
            _finding_block("spec gap", severity="S2",
                           disposition="advisory", route="R1"),
        )
        routes = parse_routes(text)
        self.assertEqual(len(routes), 3)
        self.assertEqual(routes[1][2], frozenset({"R2-structural", "R4"}))
        hits = route_hits(text)
        self.assertEqual(hits, {"R1": 1, "R2-structural": 1, "R4": 2})

    def test_signal_derivation(self) -> None:
        r1_only = _pointback(_finding_block("ownerless", severity="S2",
                                            disposition="advisory",
                                            route="R1"))
        signals = {s.signal: s for s in collect_signals(r1_only)}
        self.assertEqual(signals["E1"].required_tier, "P2")
        signals_rev = {
            s.signal: s for s in collect_signals(
                r1_only, touch_revises=True)}
        self.assertEqual(signals_rev["E1"].required_tier, "P3")

        structural = _pointback(_finding_block("path break", severity="S2",
                                               disposition="advisory",
                                               route="R2-structural"))
        self.assertEqual(
            [s.signal for s in collect_signals(structural)], ["E2"])

        r3 = _pointback(_finding_block("dd challenge", severity="S2",
                                       disposition="advisory",
                                       route="R3",
                                       extra="dd:       DD-0001"))
        self.assertEqual(
            [s.signal for s in collect_signals(r3)], ["E3"])
        self.assertEqual(
            [s.required_tier for s in collect_signals(r3)], ["P3"])
        explore_only = collect_signals(
            _pointback(_finding_block(route="R4")), dd_explore=True)
        self.assertEqual([s.signal for s in explore_only], ["E3"])

        cross = _pointback(_finding_block(route="R2-line R4"))
        self.assertEqual(
            [s.signal for s in collect_signals(cross)], ["E4"])

    def test_upgrade_parsing_and_effective_tier(self) -> None:
        upgrades = (
            "2026-08-14T12:40:00Z E5 added criterion l6.c4 beyond the P1 "
            "face -> P2 (incremental shaping session opened, artifacts kept)",
            "2026-08-14T13:00:00Z E3 explore entry recorded -> P3",
        )
        self.assertEqual(effective_tier("P1", upgrades), "P3")
        self.assertEqual(effective_tier("P1", ("no tier token here",)), "P1")
        self.assertEqual(effective_tier("P2", ()), "P2")

    def test_route_annotation_validation(self) -> None:
        from design_playbook.scripts.escalation_signals import check_routes
        bad = _pointback(_finding_block(route="R9"))
        self.assertIn("G12.route_invalid", _rules(check_routes(bad)))
        repeated = _pointback(
            _finding_block(route="R4") + "route:    R5\n")
        self.assertIn("G12.route_repeated", _rules(check_routes(repeated)))
        self.assertEqual(check_routes(_pointback(_finding_block())), [])


class ContractTouchTests(unittest.TestCase):
    """The bind-snapshot diff basis (G7 comparison ability, not rebuilt)."""

    BOUND = {
        "l1.goal": {"value": "a", "provenance": "observed",
                    "resolution": "decided"},
        "l6.c1": {"value": "c1", "provenance": "observed",
                  "resolution": "decided"},
        "export.row_cap": {"value": 1, "provenance": "inferred",
                           "resolution": "assumed"},
    }

    def test_untouched(self) -> None:
        touch = contract_touch(self.BOUND, dict(self.BOUND))
        self.assertTrue(touch.empty)
        self.assertEqual(touch.summary(), "no contract touch")

    def test_categories(self) -> None:
        current = dict(self.BOUND)
        current["l1.goal"] = {"value": "b", "provenance": "observed",
                              "resolution": "decided"}     # revised
        current["l6.c2"] = {"value": "c2", "provenance": "observed",
                            "resolution": "decided"}       # added criterion
        current["export.format"] = {"value": "csv", "provenance": "inferred",
                                    "resolution": "assumed"}  # added field
        current["l1.scenes"] = {"value": "s", "provenance": "inferred",
                                "resolution": "assumed"}   # added l1.*
        del current["export.row_cap"]                       # removed
        touch = contract_touch(self.BOUND, current)
        self.assertEqual(touch.revised, ("l1.goal",))
        self.assertEqual(
            touch.added, ("export.format", "l1.scenes", "l6.c2"))
        self.assertEqual(touch.added_criteria, ("l6.c2",))
        self.assertEqual(touch.removed, ("export.row_cap",))
        self.assertEqual(set(touch.l1_changes), {"l1.goal", "l1.scenes"})


class G12TierTableTests(unittest.TestCase):
    """Positive/negative table over the tier faces (loop-prototype 1.2)."""

    def _profile(self, tier: str, upgrades: tuple[str, ...] = ()) -> RunProfile:
        return RunProfile(
            tier=tier, confirmed_by="user + 2026-08-14T12:00:00Z",
            upgrades=upgrades)

    def _check(self, tier: str, pb_text: str, *, touch=None, upgrades=(),
               bound_criteria=None, spec_l6_count=0, dd_explore=False):
        errs, warns, signals = check_g12(
            self._profile(tier, upgrades), pointback_text=pb_text,
            touch=touch, bound_criteria=bound_criteria,
            spec_l6_count=spec_l6_count, dd_explore=dd_explore)
        return _rules(errs), _rules(warns), [
            (s.signal, s.required_tier) for s in signals]

    def test_covering_tier_table(self) -> None:
        add_only = ContractTouch(added=("l6.c4",),
                                 added_criteria=("l6.c4",))
        revise = ContractTouch(revised=("l1.goal",))
        l1_add = ContractTouch(added=("l1.scenes",),
                               l1_changes=("l1.scenes",))
        self.assertEqual(covering_tier(), "P1")
        self.assertEqual(covering_tier(routes={"R4"}), "P1")
        self.assertEqual(covering_tier(routes={"R5", "R2-line"}), "P1")
        self.assertEqual(covering_tier(touch=add_only), "P2")
        self.assertEqual(covering_tier(touch=revise), "P3")
        self.assertEqual(covering_tier(touch=l1_add), "P3")
        self.assertEqual(covering_tier(routes={"R2-structural"}), "P2")
        self.assertEqual(covering_tier(routes={"R1"}), "P2")
        self.assertEqual(covering_tier(routes={"R3"}), "P3")
        self.assertEqual(covering_tier(dd_explore=True), "P3")
        self.assertEqual(covering_tier(blocking=2), "P2")
        self.assertEqual(
            covering_tier(spec_l6_count=4, bound_criteria=3), "P2")

    def test_p1_face(self) -> None:
        clean = self._check("P1", _pointback(_finding_block(route="R4")),
                            bound_criteria=2, spec_l6_count=2)
        self.assertEqual(clean[0], set())
        line_patch = self._check(
            "P1", _pointback(_finding_block(
                "empty row", severity="S1", disposition="advisory",
                route="R2-line")), bound_criteria=2, spec_l6_count=2)
        self.assertEqual(line_patch[0], set())   # P1 allows R2 line patches

        added = ContractTouch(added=("l6.c4",), added_criteria=("l6.c4",))
        errs, _w, signals = self._check(
            "P1", _pointback(_finding_block(route="R4")), touch=added,
            bound_criteria=3, spec_l6_count=4)
        self.assertIn("G12.escalation_outstanding", errs)
        self.assertIn(("E5", "P2"), signals)

        revised = ContractTouch(revised=("l1.goal",))
        errs, _w, signals = self._check(
            "P1", _pointback(_finding_block(route="R4")), touch=revised)
        self.assertIn("G12.escalation_outstanding", errs)
        self.assertIn(("E5", "P3"), signals)     # decided revision is P3

        structural = self._check(
            "P1", _pointback(_finding_block("path break", severity="S2",
                                            disposition="advisory",
                                            route="R2-structural")))
        self.assertIn("G12.escalation_outstanding", structural[0])
        self.assertIn(("E2", "P2"), structural[2])

        r1 = self._check(
            "P1", _pointback(_finding_block("ownerless", severity="S2",
                                            disposition="advisory",
                                            route="R1")))
        self.assertIn("G12.escalation_outstanding", r1[0])
        self.assertIn(("E1", "P2"), r1[2])

        two_blocking = self._check(
            "P1", _pointback(_finding_block("a", route="R4"),
                             _finding_block("b", route="R5")))
        self.assertIn("G12.escalation_outstanding", two_blocking[0])

        growth = self._check(
            "P1", _pointback(_finding_block(route="R4")),
            bound_criteria=3, spec_l6_count=4)
        self.assertIn("G12.escalation_outstanding", growth[0])

    def test_p1_violation_covered_by_recorded_upgrade(self) -> None:
        added = ContractTouch(added=("l6.c4",), added_criteria=("l6.c4",))
        upgrades = (
            "2026-08-14T12:40:00Z E5 added criterion l6.c4 beyond the P1 "
            "face -> P2 (incremental session opened, artifacts kept)",)
        errs, warns, signals = self._check(
            "P1", _pointback(_finding_block(route="R4")), touch=added,
            upgrades=upgrades, bound_criteria=3, spec_l6_count=4)
        self.assertEqual(errs, set())
        self.assertIn("G12.escalation_recorded", warns)
        self.assertIn(("E6", "P2"), signals)

    def test_p2_face(self) -> None:
        additions = ContractTouch(added=("l6.c4", "export.format"),
                                  added_criteria=("l6.c4",))
        clean = self._check("P2", _pointback(_finding_block(route="R1")),
                            touch=additions)
        self.assertEqual(clean[0], set())        # R1 new-criteria class: P2-legal

        revised = ContractTouch(
            revised=("export.row_cap",))
        errs, _w, signals = self._check(
            "P2", _pointback(_finding_block(route="R4")), touch=revised)
        self.assertIn("G12.escalation_outstanding", errs)
        self.assertIn(("E5", "P3"), signals)

        l1 = ContractTouch(added=("l1.scenes",), l1_changes=("l1.scenes",))
        errs, _w, _s = self._check(
            "P2", _pointback(_finding_block(route="R4")), touch=l1)
        self.assertIn("G12.escalation_outstanding", errs)

        explore = self._check("P2", _pointback(_finding_block(route="R4")),
                              dd_explore=True)
        self.assertIn("G12.escalation_outstanding", explore[0])
        self.assertIn(("E3", "P3"), explore[2])

    def test_p3_face_allows_everything(self) -> None:
        full = ContractTouch(
            revised=("l1.goal",), added=("l6.c4",),
            added_criteria=("l6.c4",), l1_changes=("l1.goal",))
        errs, warns, signals = self._check(
            "P3", _pointback(_finding_block(route="R3",
                                          extra="dd:       DD-0001")),
            touch=full, dd_explore=True)
        self.assertEqual(errs, set())
        self.assertEqual(warns, set())           # E3 required == declared
        self.assertIn(("E3", "P3"), signals)

    def test_legacy_runs_without_profile_are_not_rechecked(self) -> None:
        # validate_run skips G12 when plan.md carries no run-profile block;
        # the module contract mirrors that via the orchestrator (None check).
        self.assertIsNone(parse_run_profile("# plan\nbody only\n"))


class FixtureWalkthroughTests(unittest.TestCase):
    """Issue #39: the two fixture runs demonstrate the S4 faces end to end."""

    def _validate(self, run_dir: Path) -> subprocess.CompletedProcess[str]:
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
                *(["--shaping-dir", str(run_dir / "shaping")]
                  if (run_dir / "shaping").is_dir() else []),
            ],
            capture_output=True, text=True, check=False,
        )

    def _copy(self, example: str, tmp: str) -> Path:
        base = shutil.copytree(PKG / "examples" / example,
                               Path(tmp) / example)
        return base / "run"

    def test_boundary_escalation_fixture_reaches_pass(self) -> None:
        result = self._validate(UPGRADE_RUN)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("RUN OK", result.stdout)
        # the recorded escalation narrates through the warnings channel
        self.assertIn("escalation E5 -> P2 recorded", result.stdout)
        self.assertIn("escalation E1 -> P2 recorded", result.stdout)

    def test_unrecorded_escalation_fails_the_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = self._copy("export-pointfix-upgrade", tmp)
            plan = (run / "plan.md").read_text(encoding="utf-8")
            plan = plan.replace(
                "  - 2026-08-14T12:40:00Z E5 added criterion l6.c4 + R1 "
                "finding beyond the P1 face -> P2 (incremental shaping "
                "session opened, DD-0101 recorded, artifacts kept)\n", "")
            _write(run / "plan.md", plan)
            result = self._validate(run)
            self.assertEqual(result.returncode, 1)
            self.assertIn("G12 tier: escalation signals exceed", result.stdout)
            self.assertIn("escalate to P2", result.stdout)

    def test_two_round_stop_fixture_is_a_clean_waiting_state(self) -> None:
        result = self._validate(STOP_RUN)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("RUN OK", result.stdout)

    def test_unnarrated_stop_breaks_the_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = self._copy("export-retry-stop", tmp)
            pb = (run / "point-back.md").read_text(encoding="utf-8")
            _write(run / "point-back.md",
                   pb.replace("\nclose_reason: escalated-stop\n", ""))
            result = self._validate(run)
            self.assertEqual(result.returncode, 1)
            self.assertIn("G4 rounds: blocking finding", result.stdout)
            self.assertIn("close_reason: escalated-stop", result.stdout)

    def test_orphan_stop_breaks_the_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = self._copy("export-retry-stop", tmp)
            pb = (run / "point-back.md").read_text(encoding="utf-8")
            _write(run / "point-back.md", pb.replace("rounds:   2",
                                                     "rounds:   1"))
            result = self._validate(run)
            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "G4 rounds: close_reason escalated-stop without", result.stdout)


class RunStatusNarrationTests(unittest.TestCase):
    """Re-entry narration: rounds, W-event counts, signals, close_reason."""

    def _run(self, *args: str) -> dict:
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        result = subprocess.run(
            [sys.executable, str(PKG / "scripts" / "run_status.py"), *args],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=env, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout) if "--json" in args else {
            "text": result.stdout}

    def test_boundary_fixture_narration(self) -> None:
        payload = self._run(str(UPGRADE_RUN), "--json")
        profile = payload["run_profile"]
        self.assertEqual(profile["tier"], "P1")
        self.assertEqual(profile["effective_tier"], "P2")
        self.assertEqual(len(profile["upgrades"]), 1)
        repair = payload["repair"]
        self.assertEqual(repair["rounds"], 1)
        self.assertEqual(repair["routes"], {"R1": 1, "R2-line": 1, "R4": 1})
        self.assertEqual(repair["close_reason"], "pass")
        self.assertFalse(repair["wait_user"])
        signals = {s["signal"]: s["required_tier"]
                   for s in repair["signals"]}
        self.assertEqual(signals, {"E1": "P2", "E6": "P2"})

    def test_stop_fixture_narration(self) -> None:
        payload = self._run(str(STOP_RUN), "--json")
        repair = payload["repair"]
        self.assertEqual(repair["rounds"], 2)
        self.assertEqual(repair["routes"], {"R4": 1})
        self.assertEqual(repair["close_reason"], "escalated-stop")
        self.assertTrue(repair["wait_user"])
        self.assertEqual(payload["verdict"], "Recirculate")
        self.assertIn("Escalated stop", payload["next"])
        self.assertIn("user disposition", payload["next"])

    def test_stop_fixture_text_narration(self) -> None:
        out = self._run(str(STOP_RUN))["text"]
        self.assertIn("repair: 2 round(s); routes R4 x1", out)
        self.assertIn(
            "close_reason: escalated-stop (waiting user disposition)", out)

    def test_plain_run_has_no_repair_face(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "run-plain"
            run.mkdir()
            (run / "spec.md").write_text("# L1\n", encoding="utf-8")
            payload = self._run(str(run), "--json")
            self.assertIsNone(payload["repair"])
            self.assertIsNone(payload["run_profile"])


if __name__ == "__main__":
    unittest.main()
