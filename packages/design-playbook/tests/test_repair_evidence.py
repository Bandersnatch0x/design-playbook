#!/usr/bin/env python3
"""T-152: a repaired blocker closes on a bound pair, never on a sentence.

The unit cases judge ``check_repair_evidence`` against a hand-built manifest;
the end-to-end cases run the real validator over the real pass fixture with a
``repair-evidence:`` annotation added, so "only the repaired half" is proven
invalid (blocked, not pass) and a bound pair keeps the existing verdict path.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
if str(PACKAGE) not in sys.path:
    sys.path.insert(0, str(PACKAGE))

from design_playbook.scripts.repair_evidence import (  # noqa: E402
    check_repair_evidence,
    parse_repair_evidence,
)

FIX = Path(__file__).resolve().parent / "fixtures"
VALIDATOR = PACKAGE / "scripts" / "validate_run.py"

VIEWPORT = {
    "width": 1280, "height": 800,
    "devicePixelRatio": 1.0, "colorScheme": "light",
}
FREEZE = {"enabled": True, "waitFonts": True, "networkIdle": False}


def _entry(
        artifact: str, digest: str, *,
        criterion: str = "L6.1",
        viewport: dict | None = None,
        ts: str = "2026-11-06T10:00:00+08:00") -> dict:
    return {
        "ts": ts,
        "criterion": criterion,
        "artifact": artifact,
        "sha256": digest,
        "request": {
            "schemaVersion": 1,
            "viewport": viewport or dict(VIEWPORT),
            "freeze": dict(FREEZE),
        },
    }


BOTH = (
    "## Recirculate closure trail\n\n"
    "- closes: batch retry has no confirm step -> fix -> re-eval -> 0 blocking\n"
    "  repair-evidence: before=evidence/L6.1-r1.png after=evidence/L6.1-r2.png\n"
)


def _rules(findings: list) -> set[str]:
    return {item.rule_id for item in findings}


class ParseTests(unittest.TestCase):
    def test_both_halves_are_read(self) -> None:
        self.assertEqual(
            parse_repair_evidence(BOTH),
            [{"before": "evidence/L6.1-r1.png",
              "after": "evidence/L6.1-r2.png"}],
        )

    def test_a_report_without_the_annotation_declares_no_pair(self) -> None:
        self.assertEqual(parse_repair_evidence("## Verdict\n\n**Pass.**\n"), [])


class PairTests(unittest.TestCase):
    def test_a_bound_pair_passes(self) -> None:
        entries = [
            _entry("evidence/L6.1-r1.png", "a" * 64),
            _entry("evidence/L6.1-r2.png", "b" * 64),
        ]
        self.assertEqual(check_repair_evidence(BOTH, entries), [])

    def test_the_repaired_half_alone_is_blocked(self) -> None:
        text = BOTH.replace("before=evidence/L6.1-r1.png ", "")
        findings = check_repair_evidence(text, [_entry("evidence/L6.1-r2.png", "b" * 64)])
        self.assertEqual(_rules(findings), {"G4.repair_evidence_unpaired"})

    def test_the_failing_half_alone_is_blocked(self) -> None:
        text = BOTH.replace(" after=evidence/L6.1-r2.png", "")
        findings = check_repair_evidence(text, [_entry("evidence/L6.1-r1.png", "a" * 64)])
        self.assertEqual(_rules(findings), {"G4.repair_evidence_unpaired"})

    def test_an_unbound_half_is_blocked(self) -> None:
        entries = [_entry("evidence/L6.1-r1.png", "a" * 64)]
        findings = check_repair_evidence(BOTH, entries)
        self.assertEqual(_rules(findings), {"G4.repair_evidence_unbound"})

    def test_a_different_viewport_is_blocked(self) -> None:
        entries = [
            _entry("evidence/L6.1-r1.png", "a" * 64),
            _entry("evidence/L6.1-r2.png", "b" * 64,
                   viewport={**VIEWPORT, "width": 480}),
        ]
        findings = check_repair_evidence(BOTH, entries)
        self.assertEqual(_rules(findings), {"G4.repair_evidence_mismatch"})

    def test_a_different_criterion_is_blocked(self) -> None:
        entries = [
            _entry("evidence/L6.1-r1.png", "a" * 64),
            _entry("evidence/L6.1-r2.png", "b" * 64, criterion="L6.2"),
        ]
        findings = check_repair_evidence(BOTH, entries)
        self.assertEqual(_rules(findings), {"G4.repair_evidence_mismatch"})

    def test_unchanged_bytes_are_blocked_as_a_standing_deviation(self) -> None:
        entries = [
            _entry("evidence/L6.1-r1.png", "a" * 64),
            _entry("evidence/L6.1-r2.png", "a" * 64, ts="2026-11-06T11:00:00+08:00"),
        ]
        findings = check_repair_evidence(BOTH, entries)
        self.assertEqual(_rules(findings), {"G4.repair_evidence_unchanged"})

    def test_a_legacy_report_without_the_face_is_silent(self) -> None:
        legacy = BOTH.replace(
            "  repair-evidence: before=evidence/L6.1-r1.png "
            "after=evidence/L6.1-r2.png\n", "")
        self.assertEqual(check_repair_evidence(legacy, []), [])


class ValidatorEndToEndTests(unittest.TestCase):
    """The real CLI: an unpaired closure is invalid, a bound pair is not."""

    def _run_dir(self, annotation: str, entries: list[dict]) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="t152-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        shutil.copy(FIX / "pass" / "spec.md", tmp / "spec.md")
        pointback = (FIX / "pass" / "point-back.md").read_text(encoding="utf-8")
        pointback = pointback.replace(
            "- closes: batch retry has no confirm step -> reopen `domain` -> "
            "fix: confirm Dialog + consequence -> re-eval: confirm present "
            "before execute -> **0 blocking**",
            "- closes: batch retry has no confirm step -> fix -> re-eval -> "
            "0 blocking\n" + annotation,
        )
        (tmp / "point-back.md").write_text(pointback, encoding="utf-8")
        evidence = tmp / "evidence"
        evidence.mkdir()
        (evidence / "manifest.jsonl").write_text(
            "".join(json.dumps(entry) + "\n" for entry in entries),
            encoding="utf-8",
        )
        for entry in entries:
            (evidence / Path(entry["artifact"]).name).write_bytes(b"png")
        return tmp

    def _validate(
            self, run_dir: Path,
            *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VALIDATOR), str(run_dir / "spec.md"),
             str(run_dir / "point-back.md"), "--legacy", *extra],
            capture_output=True, text=True, encoding="utf-8",
        )

    def test_the_repaired_half_alone_is_not_pass(self) -> None:
        run_dir = self._run_dir(
            "  repair-evidence: after=evidence/L6.1-r2.png\n",
            [_entry("evidence/L6.1-r2.png", "b" * 64)],
        )
        result = self._validate(run_dir)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("G4 repair-evidence", result.stdout)
        self.assertNotIn("RUN OK", result.stdout)

    def test_a_bound_pair_leaves_the_verdict_path_alone(self) -> None:
        run_dir = self._run_dir(
            "  repair-evidence: before=evidence/L6.1-r1.png "
            "after=evidence/L6.1-r2.png\n",
            [_entry("evidence/L6.1-r1.png", "a" * 64),
             _entry("evidence/L6.1-r2.png", "b" * 64)],
        )
        result = self._validate(run_dir, "--evidence-dir",
                                str(run_dir / "evidence"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("RUN OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
