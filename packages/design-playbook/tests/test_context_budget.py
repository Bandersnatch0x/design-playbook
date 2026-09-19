"""Context budget tool — report-only semantics (spec 2026-09-19)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

PACKAGE = Path(__file__).resolve().parent.parent
if str(PACKAGE) not in sys.path:
    sys.path.insert(0, str(PACKAGE))

from design_playbook.scripts import context_budget as cb  # noqa: E402

REAL_PKG = PACKAGE


class TestEstimate:
    def test_ascii_runs_divide_by_four(self) -> None:
        assert cb.estimate_tokens("a" * 40) == 10

    def test_non_ascii_counts_one_each(self) -> None:
        assert cb.estimate_tokens("设" * 5) == 5

    def test_mixed_text(self) -> None:
        # 8 ascii chars + 2 CJK chars -> 8//4 + 2 = 4
        assert cb.estimate_tokens("disabled设计") == 4


class TestMeasureSkills:
    def test_eight_skills_covered_and_numbers_match_bytes(self) -> None:
        report = cb.measure_skills(REAL_PKG)
        assert len(report["skills"]) == 8
        by_name = {s["skill"]: s for s in report["skills"]}
        # wc -c cross-check for one known skill (orchestrator).
        raw = (REAL_PKG / "skills" / "design-playbook" / "SKILL.md").read_text(
            encoding="utf-8", errors="replace"
        )
        assert by_name["design-playbook"]["skill_md"]["chars"] == len(raw)
        assert by_name["design-playbook"]["skill_tokens_est"] == cb.estimate_tokens(raw)
        assert by_name["design-playbook"]["references"], "orchestrator has references"

    def test_per_skill_totals_are_the_sum(self) -> None:
        report = cb.measure_skills(REAL_PKG)
        for s in report["skills"]:
            refs = sum(r["tokens_est"] for r in s["references"])
            assert s["references_tokens_est"] == refs
            assert s["total_tokens_est"] == s["skill_tokens_est"] + refs

    def test_estimate_markers_present(self) -> None:
        report = cb.measure_skills(REAL_PKG)
        assert report["estimate"] is True
        assert "estimate" in report["estimate_note"].lower()
        text = cb._text_view(report)
        assert "estimate" in text.lower()

    def test_heaviest_files_sorted_desc(self) -> None:
        report = cb.measure_skills(REAL_PKG)
        counts = [f["tokens_est"] for f in report["heaviest_files"]]
        assert counts == sorted(counts, reverse=True)
        assert counts, "surface is non-empty"


class TestReadOnlyBoundary:
    def test_never_writes_or_opens_for_write(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom(*args: object, **kwargs: object) -> None:
            raise AssertionError("context budget must not write")

        monkeypatch.setattr(Path, "write_text", _boom)
        monkeypatch.setattr(Path, "mkdir", _boom)
        report = cb.measure_skills(REAL_PKG)
        assert report["total"]["worst_case_pipeline_tokens_est"] > 0


class TestCLI:
    def test_json_and_text_outputs(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert cb.main(["--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["estimate"] is True
        assert len(payload["skills"]) == 8

        assert cb.main([]) == 0
        text = capsys.readouterr().out
        assert "TOTAL" in text and "context budget" in text

    def test_exit_zero_constant(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert cb.main(["--json"]) == 0

    def test_module_runs_as_script(self) -> None:
        result = subprocess.run(
            [sys.executable, str(REAL_PKG / "scripts" / "context_budget.py"), "--json"],
            capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["total"]["worst_case_pipeline_tokens_est"] > 0
