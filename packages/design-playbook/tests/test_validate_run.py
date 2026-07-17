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


def run(
        spec: Path,
        pointback: Path,
        *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), str(spec), str(pointback), *extra],
        capture_output=True,
        text=True,
    )


def expect_valid(
        failures: list[str], name: str, spec: Path, pointback: Path,
        *extra: str) -> None:
    if not spec.is_file() or not pointback.is_file():
        failures.append(f"{name}: fixture pair is incomplete")
        return
    result = run(spec, pointback, *extra)
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
        diagnostic: str, *extra: str) -> None:
    if not spec.is_file() or not pointback.is_file():
        failures.append(f"{name}: fixture pair is incomplete")
        return
    result = run(spec, pointback, *extra)
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


def _zero_findings_pair() -> tuple[Path, Path]:
    return PASS / "zero-findings.spec.md", PASS / "zero-findings.point-back.md"


def _g5_args(case_dir: Path) -> list[str]:
    preview = case_dir / "preview"
    report = case_dir / "decision-report.md"
    args = ["--preview-dir", str(preview)]
    if report.is_file():
        args.extend(["--decision-report", str(report)])
    return args


def _g6_args(case_dir: Path) -> list[str]:
    evidence = case_dir / "evidence"
    return ["--evidence-dir", str(evidence), "--run-root", str(case_dir)]


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

    # --- G5 conditional preview gate (matrix B) ---
    spec, pb = _zero_findings_pair()

    expect_valid(failures, "pass/g5-no-preview-omit-flag", spec, pb)
    expect_valid(
        failures,
        "pass/g5-no-preview-empty-dir",
        spec,
        pb,
        "--preview-dir",
        str(PASS / "g5-no-preview"),
    )

    for name in (
            "g5-preview-confirmed",
            "g5-multi-round-last-confirmed",
            "g5-aborted-then-confirmed",
            "g5-floor-fail-then-revised"):
        case = PASS / name
        expect_valid(
            failures, f"pass/{name}", spec, pb, *_g5_args(case))

    expect_invalid(
        failures,
        "g5-preview-without-confirm",
        spec,
        pb,
        "G5 preview",
        *_g5_args(FAIL / "g5-preview-without-confirm"),
    )
    expect_invalid(
        failures,
        "g5-confirm-bad-report-ref",
        spec,
        pb,
        "G5 preview",
        *_g5_args(FAIL / "g5-confirm-bad-report-ref"),
    )
    expect_invalid(
        failures,
        "g5-only-aborted",
        spec,
        pb,
        "G5 preview",
        *_g5_args(FAIL / "g5-only-aborted"),
    )
    expect_invalid(
        failures,
        "g5-confirm-false-only",
        spec,
        pb,
        "G5 preview",
        *_g5_args(FAIL / "g5-confirm-false-only"),
    )
    expect_invalid(
        failures,
        "g5-confirm-floor-fail",
        spec,
        pb,
        "failed feedback floor",
        *_g5_args(FAIL / "g5-confirm-floor-fail"),
    )

    # --- G6 conditional evidence-binding gate (matrix) ---
    g6_spec, _ = _zero_findings_pair()

    expect_valid(
        failures,
        "pass/g6-no-evidence",
        g6_spec,
        PASS / "g6-no-evidence" / "point-back.md",
    )
    expect_valid(
        failures,
        "pass/g6-no-evidence-omit-flag",
        g6_spec,
        PASS / "g6-no-evidence" / "point-back.md",
        "--evidence-dir",
        str(PASS / "g6-no-evidence" / "evidence"),
    )
    for name in (
            "g6-evidence-bound",
            "g6-multi-entry-latest",
            "g6-manual-provider"):
        case = PASS / name
        expect_valid(
            failures, f"pass/{name}", g6_spec,
            case / "point-back.md", *_g6_args(case))

    expect_invalid(
        failures, "g6-dangling-ref", g6_spec,
        FAIL / "g6-dangling-ref" / "point-back.md",
        "G6 evidence", *_g6_args(FAIL / "g6-dangling-ref"))
    expect_invalid(
        failures, "g6-missing-artifact", g6_spec,
        FAIL / "g6-missing-artifact" / "point-back.md",
        "G6 evidence", *_g6_args(FAIL / "g6-missing-artifact"))
    expect_invalid(
        failures, "g6-unknown-criterion", g6_spec,
        FAIL / "g6-unknown-criterion" / "point-back.md",
        "G6 evidence", *_g6_args(FAIL / "g6-unknown-criterion"))
    expect_invalid(
        failures, "g6-pass-without-valid-binding", g6_spec,
        FAIL / "g6-pass-without-valid-binding" / "point-back.md",
        "G6 evidence", *_g6_args(FAIL / "g6-pass-without-valid-binding"))

    # --- ADR-0008 adapter floor self-check (server.py) ---
    preview_server = PACKAGE.parent / "design-playbook-preview" / "server.py"
    if preview_server.is_file():
        sc = subprocess.run(
            [sys.executable, str(preview_server), "--self-check"],
            capture_output=True, text=True)
        if sc.returncode != 0 or "FLOOR SELF-CHECK PASSED" not in sc.stdout:
            failures.append(
                f"adapter floor self-check: exit {sc.returncode}; "
                f"stdout={sc.stdout!r} stderr={sc.stderr!r}")
        else:
            print("  ok    adapter floor self-check passed")
    else:
        failures.append("adapter floor self-check: server.py not found")

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
