#!/usr/bin/env python3
"""Regression-test the deterministic run seam and its diagnostics."""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
VALIDATOR = PACKAGE / "scripts" / "validate_run.py"
FIX = HERE / "fixtures"
PASS = FIX / "pass"
FAIL = FIX / "fail"


def run(spec: Path, pointback: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), str(spec), str(pointback)],
        capture_output=True,
        text=True,
    )


def expect_valid(
        failures: list[str], name: str, spec: Path, pointback: Path) -> None:
    if not spec.is_file() or not pointback.is_file():
        failures.append(f"{name}: fixture pair is incomplete")
        return
    result = run(spec, pointback)
    if result.returncode != 0:
        failures.append(
            f"{name}: expected exit 0, got {result.returncode}; "
            f"stdout={result.stdout!r} stderr={result.stderr!r}")
    elif result.stderr:
        failures.append(f"{name}: unexpected stderr {result.stderr!r}")
    elif "RUN OK" not in result.stdout:
        failures.append(f"{name}: success diagnostic missing")
    else:
        print(f"  ok    {name} is valid")


def expect_invalid(
        failures: list[str], name: str, spec: Path, pointback: Path,
        diagnostic: str) -> None:
    if not spec.is_file() or not pointback.is_file():
        failures.append(f"{name}: fixture pair is incomplete")
        return
    result = run(spec, pointback)
    if result.returncode != 1:
        failures.append(
            f"{name}: expected artifact-invalid exit 1, got "
            f"{result.returncode}; stdout={result.stdout!r} "
            f"stderr={result.stderr!r}")
    elif result.stderr:
        failures.append(f"{name}: unexpected stderr {result.stderr!r}")
    elif diagnostic not in result.stdout:
        failures.append(
            f"{name}: expected diagnostic {diagnostic!r}; "
            f"stdout={result.stdout!r}")
    else:
        print(f"  ok    {name} rejects with {diagnostic!r}")


def main() -> int:
    failures: list[str] = []

    pass_specs = sorted(PASS.glob("*spec.md"))
    if not pass_specs:
        failures.append("no pass fixtures found")
    for spec in pass_specs:
        pointback = spec.with_name(
            spec.name.replace("spec.md", "point-back.md"))
        name = spec.name.replace(".spec.md", "").replace("spec", "default")
        expect_valid(failures, f"pass/{name}", spec, pointback)

    expect_valid(
        failures,
        "pass/recirculate-mentions-pass",
        PASS / "zero-findings.spec.md",
        PASS / "recirculate-mentions-pass.point-back.md",
    )
    expect_valid(
        failures,
        "showcase/direct",
        PACKAGE / "showcase" / "01-spec.md",
        PACKAGE / "showcase" / "03-point-back.md",
    )

    cases = [
        ("g1-spec-no-criteria", FAIL / "g1-spec-no-criteria.spec.md",
         FAIL / "g1-spec-no-criteria.point-back.md",
         "spec: L6.1 missing Given, When, Then"),
        ("g1-missing-when", FAIL / "g1-missing-when.spec.md",
         FAIL / "g1-spec-no-criteria.point-back.md",
         "spec: L6.1 missing When"),
        ("g1-missing-then", FAIL / "g1-missing-then.spec.md",
         FAIL / "g1-spec-no-criteria.point-back.md",
         "spec: L6.1 missing Then"),
        ("g2-empty-source", FAIL / "g2-empty-source.spec.md",
         FAIL / "g2-empty-source.point-back.md", "has empty source"),
        ("g2-empty-issue", PASS / "zero-findings.spec.md",
         FAIL / "g2-empty-issue.point-back.md", "has empty issue"),
        ("g2-empty-fix", PASS / "zero-findings.spec.md",
         FAIL / "g2-empty-fix.point-back.md", "has empty fix"),
        ("g2-empty-severity", PASS / "zero-findings.spec.md",
         FAIL / "g2-empty-severity.point-back.md", "has empty severity"),
        ("g2-missing-evidence", PASS / "zero-findings.spec.md",
         FAIL / "g2-missing-evidence.point-back.md",
         "evidence: no criterion-shaped ledger entries"),
        ("g2-empty-observed", PASS / "zero-findings.spec.md",
         FAIL / "g2-empty-observed.point-back.md",
         "evidence: row 3 has empty observed"),
        ("g2-missing-l6", PASS / "zero-findings.spec.md",
         FAIL / "g2-missing-l6.point-back.md",
         "evidence: missing ledger row for L6.5"),
        ("g2-repeated-l6", PASS / "zero-findings.spec.md",
         FAIL / "g2-repeated-l6.point-back.md",
         "evidence: repeated ledger rows for L6.4"),
        ("g2-unknown-l6", PASS / "zero-findings.spec.md",
         FAIL / "g2-unknown-l6.point-back.md",
         "evidence: ledger references unknown L6.6"),
        ("g2-pass-failed-evidence", PASS / "zero-findings.spec.md",
         FAIL / "g2-pass-failed-evidence.point-back.md",
         "evidence: Pass requires row 3 result pass, got 'fail'"),
        ("g2-invalid-evidence-result", PASS / "zero-findings.spec.md",
         FAIL / "g2-invalid-evidence-result.point-back.md",
         "evidence: row 3 has invalid result 'maybe'"),
        ("g3-fake-closure", FAIL / "g3-fake-closure.spec.md",
         FAIL / "g3-fake-closure.point-back.md",
         "Pass verdict but no '0 blocking' closure trail"),
        ("g3-pass-no-closure", FAIL / "g3-pass-no-closure.spec.md",
         FAIL / "g3-pass-no-closure.point-back.md",
         "Pass verdict but no '0 blocking' closure trail"),
        ("g3-missing-verdict", PASS / "zero-findings.spec.md",
         FAIL / "g3-missing-verdict.point-back.md",
         "missing explicit Verdict section"),
        ("g4-underloop", FAIL / "g4-underloop.spec.md",
         FAIL / "g4-underloop.point-back.md",
         "no matching closure trail for issue 'abort run without confirm'"),
    ]
    for name, spec, pointback, diagnostic in cases:
        expect_invalid(failures, name, spec, pointback, diagnostic)

    missing = run(PASS / "zero-findings.spec.md", HERE / "__missing__.md")
    if missing.returncode != 2 or "RUN ERROR" not in missing.stdout:
        failures.append(
            "missing input must be an operational exit 2, not artifact exit 1")
    else:
        print("  ok    missing input exits 2")

    print()
    if failures:
        for failure in failures:
            print(f"  FAIL  {failure}")
        print(f"SEAM TEST FAILED: {len(failures)} issue(s)")
        return 1
    print("SEAM TEST PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
