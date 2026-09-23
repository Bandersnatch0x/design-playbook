#!/usr/bin/env python3
"""Tests for the decision-point eval runner (M-001 / T-055)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
if str(PACKAGE) not in sys.path:
    sys.path.insert(0, str(PACKAGE))

from design_playbook.scripts.eval_decisions import (  # noqa: E402
    SuiteError,
    load_suite,
    main,
    run_suite,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "eval-decisions"


class EvalDecisionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        template = (FIXTURES / "suite.template.jsonl").read_text(encoding="utf-8")
        rows = [json.loads(line) for line in template.splitlines() if line.strip()]
        # 现算好样本哈希（对 CRLF/LF 检出轮换免疫）；smoke-03 的占位错配哈希保留
        import hashlib

        for row in rows:
            for ref in row["context"]:
                ref["path"] = ref["path"].replace("CTX_DIR", FIXTURES.as_posix())
                if ref.get("sha256") and not ref["sha256"].startswith("0000"):
                    ref["sha256"] = hashlib.sha256(
                        Path(ref["path"]).read_bytes()
                    ).hexdigest()
        self.suite = self.tmp / "suite.jsonl"
        self.suite.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_mock_run_reports_and_marks_stale(self) -> None:
        report = run_suite(self.suite, "mock")
        self.assertEqual(report["total"], 3)
        self.assertEqual(report["evaluated"], 2)
        self.assertEqual(len(report["stale"]), 1)
        self.assertIn("smoke-03", report["stale"][0])
        self.assertIn("weighted_accuracy", report)
        self.assertEqual(report["latency"]["p50"], 0.0)  # mock is instant

    def test_run_writes_report_file(self) -> None:
        rc = main(["run", "--suite", str(self.suite), "--target", "mock"])
        self.assertEqual(rc, 0)
        written = self.tmp / "suite.report-mock.json"
        self.assertTrue(written.is_file())
        loaded = json.loads(written.read_text(encoding="utf-8"))
        self.assertEqual(loaded["target"], "mock")

    def test_engine_target_exits_with_reason(self) -> None:
        with self.assertRaises(SuiteError) as ctx:
            run_suite(self.suite, "engine")
        self.assertIn("not wired yet", str(ctx.exception))

    def test_missing_suite_names_correct_form(self) -> None:
        with self.assertRaises(SuiteError) as ctx:
            load_suite(self.tmp / "nope")
        self.assertIn("jsonl", str(ctx.exception))

    def test_bad_cost_class_rejected(self) -> None:
        bad = self.tmp / "bad.jsonl"
        bad.write_text(
            '{"id":"x","stage":"s","decision":"d","options":["a","b"],'
            '"gold":"a","cost_class":"bogus","context":[]}\n',
            encoding="utf-8",
        )
        with self.assertRaises(SuiteError):
            load_suite(bad)


if __name__ == "__main__":
    unittest.main()
