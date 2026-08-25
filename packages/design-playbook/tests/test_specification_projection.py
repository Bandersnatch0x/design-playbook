"""Public-seam tests for the Specification owner's intent projection."""
from __future__ import annotations

import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]

if str(PACKAGE) not in sys.path:
    sys.path.insert(0, str(PACKAGE))

from design_playbook.scripts.g1_spec import (  # noqa: E402
    SpecificationCriterion,
    SpecificationProjection,
    SpecificationProjectionError,
    check_spec,
    project_specification,
)


class SpecificationProjectionTests(unittest.TestCase):
    def test_projects_summary_and_ordered_criteria(self) -> None:
        text = """# Spec

## L1 Goal

- Outcome summary: Deliver a safe checkout.

## L2 Structure
Page.
## L3 Flow
Flow.
## L4 Details
Details.
## L5 Edges
Edges.
## L6 Acceptance

1. Happy path: Given a valid cart, When checkout runs, Then an order exists.
2. Given an empty cart, When checkout runs, Then an error is shown.
"""

        self.assertEqual(
            project_specification(text),
            SpecificationProjection(
                summary="Deliver a safe checkout.",
                criteria=(
                    SpecificationCriterion(
                        criterion_id="L6.1",
                        title="Happy path",
                        given="a valid cart",
                        when="checkout runs",
                        then="an order exists.",
                    ),
                    SpecificationCriterion(
                        criterion_id="L6.2",
                        title=None,
                        given="an empty cart",
                        when="checkout runs",
                        then="an error is shown.",
                    ),
                ),
            ),
        )

    def test_rejects_incomplete_or_out_of_order_criteria(self) -> None:
        cases = {
            "incomplete": (
                "Given a cart, Then an order exists.",
                "criterion-incomplete",
            ),
            "out-of-order": (
                "When checkout runs, Given a cart, Then an order exists.",
                "criterion-out-of-order",
            ),
        }

        for name, (criterion, code) in cases.items():
            with self.subTest(name=name):
                text = f"""# Spec

## L1 Goal
- Goal: Deliver checkout.
## L2 Structure
Page.
## L3 Flow
Flow.
## L4 Details
Details.
## L5 Edges
Edges.
## L6 Acceptance
- {criterion}
"""
                with self.assertRaises(SpecificationProjectionError) as caught:
                    project_specification(text)
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(str(caught.exception), code)

    def test_rejects_missing_summary_criteria_and_normalized_duplicates(self) -> None:
        cases = {
            "empty-summary": (
                "",
                "- Given a cart, When checkout runs, Then an order exists.",
                "summary-missing",
            ),
            "missing-criteria": (
                "- Goal: Deliver checkout.",
                "No acceptance item.",
                "criteria-missing",
            ),
            "duplicate-criteria": (
                "- Goal: Deliver checkout.",
                """- Given a cart, When checkout runs, Then an order exists.
- Given   a cart,   When checkout runs,   Then an order exists.""",
                "criterion-duplicate",
            ),
        }

        for name, (summary, criteria, code) in cases.items():
            with self.subTest(name=name):
                text = f"""# Spec

## L1 Goal
{summary}
## L2 Structure
Page.
## L3 Flow
Flow.
## L4 Details
Details.
## L5 Edges
Edges.
## L6 Acceptance
{criteria}
"""
                with self.assertRaises(SpecificationProjectionError) as caught:
                    project_specification(text)
                self.assertEqual(caught.exception.code, code)

    def test_rejects_empty_given_when_or_then_values(self) -> None:
        for criterion in (
            "Given, When checkout runs, Then an order exists.",
            "Given a cart, When, Then an order exists.",
            "Given a cart, When checkout runs, Then",
        ):
            with self.subTest(criterion=criterion):
                text = f"""# Spec

## L1 Goal
- Goal: Deliver checkout.
## L2 Structure
Page.
## L3 Flow
Flow.
## L4 Details
Details.
## L5 Edges
Edges.
## L6 Acceptance
- {criterion}
"""
                with self.assertRaises(SpecificationProjectionError) as caught:
                    project_specification(text)
                self.assertEqual(caught.exception.code, "criterion-malformed")

    def test_keeps_untrusted_text_as_data_without_runtime_path_disclosure(self) -> None:
        text = """# Spec

## L1 Goal
- Goal: <script>alert('summary')</script> mentions ## L6 inline.
## L2 Structure
Page.
## L3 Flow
Flow.
## L4 Details
Details.
## L5 Edges
Edges.
## L6 Acceptance
- Given ../../run/private, When <img src=x onerror=alert(1)> is shown, Then ## L1 stays text.
"""

        projection = project_specification(text)

        self.assertEqual(
            projection.summary,
            "<script>alert('summary')</script> mentions ## L6 inline.",
        )
        self.assertEqual(projection.criteria[0].given, "../../run/private")
        self.assertEqual(
            projection.criteria[0].when,
            "<img src=x onerror=alert(1)> is shown",
        )
        self.assertEqual(projection.criteria[0].then, "## L1 stays text.")
        self.assertNotIn(str(PACKAGE.parent), repr(projection))

    def test_projection_values_are_immutable(self) -> None:
        projection = project_specification("""# Spec

## L1 Goal
- Goal: Deliver checkout.
## L2 Structure
Page.
## L3 Flow
Flow.
## L4 Details
Details.
## L5 Edges
Edges.
## L6 Acceptance
- Given a cart, When checkout runs, Then an order exists.
""")

        with self.assertRaises(FrozenInstanceError):
            projection.summary = "changed"
        with self.assertRaises(FrozenInstanceError):
            projection.criteria[0].given = "changed"
        self.assertIsInstance(projection.criteria, tuple)

    def test_check_spec_diagnostics_remain_exact_for_existing_fixtures(self) -> None:
        fail = PACKAGE / "tests" / "fixtures" / "fail"
        cases = {
            "g1-spec-no-criteria.spec.md": {
                "actual": "missing Given, When, Then",
                "expected": "Given, When, Then present",
                "message": "G1 spec: L6.1 missing Given, When, Then",
                "owner": "spec.md#L6.1",
                "repair": "Complete Given/When/Then for L6.1",
                "rule_id": "G1.missing_gwt",
                "severity": "error",
            },
            "g1-missing-when.spec.md": {
                "actual": "missing When",
                "expected": "Given, When, Then present",
                "message": "G1 spec: L6.1 missing When",
                "owner": "spec.md#L6.1",
                "repair": "Complete Given/When/Then for L6.1",
                "rule_id": "G1.missing_gwt",
                "severity": "error",
            },
            "g1-missing-then.spec.md": {
                "actual": "missing Then",
                "expected": "Given, When, Then present",
                "message": "G1 spec: L6.1 missing Then",
                "owner": "spec.md#L6.1",
                "repair": "Complete Given/When/Then for L6.1",
                "rule_id": "G1.missing_gwt",
                "severity": "error",
            },
        }

        for name, expected in cases.items():
            with self.subTest(name=name):
                findings = check_spec((fail / name).read_text(encoding="utf-8"))
                self.assertEqual([item.to_dict() for item in findings], [expected])

    def test_existing_specification_fixtures_have_exact_typed_results(self) -> None:
        fixtures = PACKAGE / "tests" / "fixtures"
        projection = project_specification(
            (fixtures / "pass" / "spec.md").read_text(encoding="utf-8")
        )

        self.assertEqual(
            projection.summary,
            "查看所有模拟运行的实时状态、失败重试与资源占用的队列监控页。",
        )
        self.assertEqual(
            projection.criteria,
            (
                SpecificationCriterion(
                    "L6.1", None, "一条 failed", "展开详情",
                    "可见失败原因 + 资源峰值，且可触发重试。",
                ),
                SpecificationCriterion(
                    "L6.2", None, "一条 failed", "重试成功",
                    "行转 queued 并可刷新到 running/completed。",
                ),
                SpecificationCriterion(
                    "L6.3", None, "无运行", "打开运行列表",
                    "非白屏空态 + CTA。",
                ),
                SpecificationCriterion(
                    "L6.4", None, "viewer", "查看运行操作",
                    "重试/中止不可执行且有原因。",
                ),
                SpecificationCriterion(
                    "L6.5", None, "批量重试", "提交执行",
                    "二次确认 + 后果文案后才执行。",
                ),
            ),
        )

        fail = fixtures / "fail"
        for name in (
            "g1-missing-then.spec.md",
            "g1-missing-when.spec.md",
            "g1-spec-no-criteria.spec.md",
        ):
            with self.subTest(name=name):
                with self.assertRaises(SpecificationProjectionError) as caught:
                    project_specification((fail / name).read_text(encoding="utf-8"))
                self.assertEqual(caught.exception.code, "criterion-incomplete")


if __name__ == "__main__":
    unittest.main()
