#!/usr/bin/env python3
"""Regression-test the deterministic run seam and its diagnostics."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
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


def _write_text(path: Path, text: str) -> None:
    """Create parent dirs and write a UTF-8 file inside a temp run root."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _confirm_record(
        round_n: int, *,
        confirmed: bool = True,
        floor_pass: bool = True,
        report_ref: str = "decision-report.md",
        prototype_html_hash: str | None = None,
        floor_failure: str = "") -> dict:
    """Build a confirm-round JSON payload mirroring trusted-side confirm.py.

    ``prototype_html_hash`` is omitted by default so legacy-style records can
    still be constructed; pass an explicit value to exercise the hash gate.
    """
    record: dict = {
        "round": round_n,
        "report_ref": report_ref,
        "confirmed": confirmed,
        "floor_pass": floor_pass,
        "selected_options": ["确认通过"],
        "feedback": "确认通过，无修改意见",
        "timestamp": "2026-07-21T12:00:00+08:00",
        "prototype_path": f"preview/round-{round_n}.html",
    }
    if prototype_html_hash is not None:
        record["prototype_html_hash"] = prototype_html_hash
    if floor_failure:
        record["floor_failure"] = floor_failure
    return record


# Point-back with one ``evidence/`` observed that escapes the evidence/
# subtree via ``..`` (issue 04/G6). Otherwise shaped to pass G1-G4 against
# the zero-findings spec (5 L6 items, Pass verdict, no findings).
_G6_ESCAPE_POINTBACK = """# Point-back findings - escape probe

## Verdict

**Pass.**

## Evidence ledger

```text
criterion: L6.1
required: declared proof for L6.1
observed: fixture evidence for L6.1
result: pass

criterion: L6.2
required: declared proof for L6.2
observed: fixture evidence for L6.2
result: pass

criterion: L6.3
required: declared proof for L6.3
observed: evidence/../spec.md
result: pass

criterion: L6.4
required: declared proof for L6.4
observed: fixture evidence for L6.4
result: pass

criterion: L6.5
required: declared proof for L6.5
observed: fixture evidence for L6.5
result: pass
```
"""


def _g6_probe_pointback(observed_l6_1: str) -> str:
    """Build a G6-probe point-back: L6.1's observed is the probe; L6.2-L6.5
    are free-text pass rows. Pass verdict + no findings keeps G1-G4 happy
    against the zero-findings spec (5 L6 items), so only G6 fires on L6.1."""
    return f"""# Point-back findings - G6 probe

## Verdict

**Pass.**

## Evidence ledger

```text
criterion: L6.1
required: declared proof for L6.1
observed: {observed_l6_1}
result: pass

criterion: L6.2
required: declared proof for L6.2
observed: fixture evidence for L6.2
result: pass

criterion: L6.3
required: declared proof for L6.3
observed: fixture evidence for L6.3
result: pass

criterion: L6.4
required: declared proof for L6.4
observed: fixture evidence for L6.4
result: pass

criterion: L6.5
required: declared proof for L6.5
observed: fixture evidence for L6.5
result: pass
```
"""


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
    expect_valid(
        failures,
        "showcase/preview-g5",
        PACKAGE / "showcase" / "01-spec.md",
        PACKAGE / "showcase" / "03-point-back.md",
        "--preview-dir", str(PACKAGE / "showcase" / "preview"),
        "--decision-report", str(PACKAGE / "showcase" / "preview" / "decision-report.md"),
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
            "g6-observed-with-commentary",
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

    # --- G5 latest numeric round + prototype hash (issues 02 / 03) ---
    # round-1 confirmed, round-2 prototype exists with NO confirm: the
    # round-1 confirm is stale and must not satisfy the gate.
    spec, pb = _zero_findings_pair()
    with tempfile.TemporaryDirectory() as tmp:
        run_root = Path(tmp)
        preview = run_root / "preview"
        _write_text(preview / "round-1.html", "<html>round-1</html>")
        _write_text(preview / "round-2.html", "<html>round-2</html>")
        h1 = hashlib.sha256(b"<html>round-1</html>").hexdigest()
        _write_text(
            preview / "confirm-round-1.json",
            json.dumps(
                _confirm_record(1, prototype_html_hash=h1),
                ensure_ascii=False, indent=2),
        )
        _write_text(run_root / "decision-report.md", "# decision report\n")
        expect_invalid(
            failures, "g5-stale-old-round-confirmed", spec, pb,
            "stale",
            "--preview-dir", str(preview),
            "--decision-report", str(run_root / "decision-report.md"))

    # prototype on disk no longer hashes to the recorded prototype_html_hash
    # (prototype altered after confirm) -> G5 fail.
    with tempfile.TemporaryDirectory() as tmp:
        run_root = Path(tmp)
        preview = run_root / "preview"
        _write_text(preview / "round-1.html", "<html>round-1</html>")
        _write_text(
            preview / "confirm-round-1.json",
            json.dumps(
                _confirm_record(1, prototype_html_hash="0" * 64),
                ensure_ascii=False, indent=2),
        )
        _write_text(run_root / "decision-report.md", "# decision report\n")
        expect_invalid(
            failures, "g5-prototype-hash-mismatch", spec, pb,
            "prototype_html_hash",
            "--preview-dir", str(preview),
            "--decision-report", str(run_root / "decision-report.md"))

    # A current, confirmed, hash-matching record still passes (hash happy path
    # guards against the gate becoming a blanket reject).
    with tempfile.TemporaryDirectory() as tmp:
        run_root = Path(tmp)
        preview = run_root / "preview"
        _write_text(preview / "round-1.html", "<html>round-1</html>")
        h1 = hashlib.sha256(b"<html>round-1</html>").hexdigest()
        _write_text(
            preview / "confirm-round-1.json",
            json.dumps(
                _confirm_record(1, prototype_html_hash=h1),
                ensure_ascii=False, indent=2),
        )
        _write_text(run_root / "decision-report.md", "# decision report\n")
        expect_valid(
            failures, "g5-prototype-hash-match", spec, pb,
            "--preview-dir", str(preview),
            "--decision-report", str(run_root / "decision-report.md"))

    # CRLF working-tree bytes must match an LF-normalized confirm hash
    # (Windows core.autocrlf vs Linux CI checkout of the same blob).
    with tempfile.TemporaryDirectory() as tmp:
        run_root = Path(tmp)
        preview = run_root / "preview"
        body = b"<html>round-1</html>\n"
        (preview).mkdir(parents=True, exist_ok=True)
        (preview / "round-1.html").write_bytes(body.replace(b"\n", b"\r\n"))
        h_lf = hashlib.sha256(body).hexdigest()
        _write_text(
            preview / "confirm-round-1.json",
            json.dumps(
                _confirm_record(1, prototype_html_hash=h_lf),
                ensure_ascii=False, indent=2),
        )
        _write_text(run_root / "decision-report.md", "# decision report\n")
        expect_valid(
            failures, "g5-prototype-hash-crlf-normalized", spec, pb,
            "--preview-dir", str(preview),
            "--decision-report", str(run_root / "decision-report.md"))

    # --- G6 observed containment (issue 04): observed must not escape
    # the evidence/ subtree via ".." ---
    with tempfile.TemporaryDirectory() as tmp:
        run_root = Path(tmp)
        evidence = run_root / "evidence"
        _write_text(evidence / ".keep", "")  # evidence/ must be a directory
        _write_text(
            run_root / "spec.md",
            "# real spec at run root (escape target, must NOT be reached)")
        g6_spec, _ = _zero_findings_pair()
        g6_pb = run_root / "point-back.md"
        _write_text(g6_pb, _G6_ESCAPE_POINTBACK)
        expect_invalid(
            failures, "g6-observed-escape-dotdot", g6_spec, g6_pb,
            "escapes evidence/",
            "--evidence-dir", str(evidence),
            "--run-root", str(run_root))

    # --- M6: realpath defence against symlink escape. Mirror evidence/
    # server.py _resolve_artifact_path on the read side: Path.resolve and
    # os.path.realpath can disagree on symlink chains across platforms, so a
    # symlink under evidence/ that resolves outside must be caught here too.
    with tempfile.TemporaryDirectory() as tmp:
        run_root = Path(tmp)
        evidence = run_root / "evidence"
        evidence.mkdir()
        secret = run_root / "secret.txt"
        secret.write_text("secret at run root", encoding="utf-8")
        link = evidence / "link.txt"
        try:
            os.symlink(secret, link)
        except (OSError, NotImplementedError):
            # Windows without developer mode refuses symlinks; skip rather
            # than false-fail. The escape is still exercised on Linux/CI.
            print("  skip  g6-symlink-escape (symlinks unavailable on this OS)")
        else:
            _write_text(
                evidence / "manifest.jsonl",
                json.dumps({
                    "criterion": "L6.1",
                    "artifact": "link.txt",
                    "ts": "2026-07-21T00:00:00+08:00",
                }) + "\n",
            )
            g6_spec, _ = _zero_findings_pair()
            g6_pb = run_root / "point-back.md"
            _write_text(g6_pb, _g6_probe_pointback("evidence/link.txt"))
            expect_invalid(
                failures, "g6-symlink-escape-via-realpath", g6_spec, g6_pb,
                "escapes evidence/",
                "--evidence-dir", str(evidence),
                "--run-root", str(run_root))

    # --- LOW-3: observed prefix check is case-insensitive. An uppercase
    # EVIDENCE/ row must still bind to G6 (write boundary is casefold on
    # Windows; the read side was case-sensitive, an asymmetry that let
    # EVIDENCE/<x> skip the gate). Without the fix this row is silently
    # skipped and a missing artifact goes unflagged.
    with tempfile.TemporaryDirectory() as tmp:
        run_root = Path(tmp)
        evidence = run_root / "evidence"
        evidence.mkdir()
        _write_text(
            evidence / "manifest.jsonl",
            json.dumps({
                "criterion": "L6.1",
                "artifact": "missing.png",
                "ts": "2026-07-21T00:00:00+08:00",
            }) + "\n",
        )
        g6_spec, _ = _zero_findings_pair()
        g6_pb = run_root / "point-back.md"
        _write_text(g6_pb, _g6_probe_pointback("EVIDENCE/missing.png"))
        expect_invalid(
            failures, "g6-uppercase-observed-prefix-binds", g6_spec, g6_pb,
            "artifact missing",
            "--evidence-dir", str(evidence),
            "--run-root", str(run_root))

    # --- LOW-2: _prototype_target must keep prototype resolution inside
    # preview/. A prototype_path that resolves outside preview/ (e.g.
    # ../secret.txt) is treated as a missing prototype; the validator must
    # never hash files outside preview/ even when their hash matches the
    # recorded one. log.md triggers preview_occurred without any round-*.html
    # so the round-fallback candidate does not exist.
    spec, pb = _zero_findings_pair()
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        run_root = base / "run"
        preview = run_root / "preview"
        preview.mkdir(parents=True)
        secret = base / "secret.txt"  # at run_root.parent, outside preview/
        secret.write_text("<html>secret</html>", encoding="utf-8")
        secret_hash = hashlib.sha256(b"<html>secret</html>").hexdigest()
        _write_text(preview / "log.md", "# preview log\n")
        _write_text(
            preview / "confirm-round-1.json",
            json.dumps(
                {
                    "report_ref": "decision-report.md",
                    "confirmed": True,
                    "floor_pass": True,
                    "selected_options": ["确认通过"],
                    "feedback": "确认通过",
                    "timestamp": "2026-07-21T12:00:00+08:00",
                    "prototype_path": "../secret.txt",
                    "prototype_html_hash": secret_hash,
                },
                ensure_ascii=False, indent=2),
        )
        _write_text(run_root / "decision-report.md", "# decision report\n")
        expect_invalid(
            failures, "g5-prototype-path-escapes-preview", spec, pb,
            "prototype html is missing",
            "--preview-dir", str(preview),
            "--decision-report", str(run_root / "decision-report.md"))

    # --- ADR-0008 adapter floor self-check (bundled runtime) ---
    preview_server = PACKAGE / "mcp" / "preview" / "server.py"
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
        failures.append("adapter floor self-check: bundled server.py not found")

    # --- Strict quality mode (opt-in require flags) ---
    strict_spec, strict_pb = _zero_findings_pair()
    strict_no_preview = run(strict_spec, strict_pb, "--require-preview")
    if strict_no_preview.returncode != 1 or "require-preview" not in strict_no_preview.stdout:
        failures.append(
            "strict require-preview: expected exit 1 with diagnostic; "
            f"got {strict_no_preview.returncode} {strict_no_preview.stdout!r}"
        )
    else:
        print("  ok    strict --require-preview fails without preview")
    strict_no_evidence = run(strict_spec, strict_pb, "--require-evidence")
    if (
        strict_no_evidence.returncode != 1
        or "require-evidence" not in strict_no_evidence.stdout
    ):
        failures.append(
            "strict require-evidence: expected exit 1 with diagnostic; "
            f"got {strict_no_evidence.returncode} {strict_no_evidence.stdout!r}"
        )
    else:
        print("  ok    strict --require-evidence fails without evidence")
    g6_case = PASS / "g6-evidence-bound"
    g5_case = PASS / "g5-preview-confirmed"
    req_ev = run(
        g6_spec,
        g6_case / "point-back.md",
        "--require-evidence",
        *_g6_args(g6_case),
    )
    if req_ev.returncode != 0:
        failures.append(
            f"strict require-evidence on bound fixture failed: {req_ev.stdout!r}"
        )
    else:
        print("  ok    strict --require-evidence passes with bound evidence")
    req_prev = run(
        strict_spec,
        strict_pb,
        "--require-preview",
        *_g5_args(g5_case),
    )
    if req_prev.returncode != 0:
        failures.append(
            f"strict require-preview on confirmed fixture failed: {req_prev.stdout!r}"
        )
    else:
        print("  ok    strict --require-preview passes with confirmed preview")

    # --- ADR-0008 frontend floor JS intercept (playwright) ---
    # CI has no playwright (see ci.yml: browser suites stay local/release).
    # Skip when unavailable so seam stays green; run locally when installed.
    frontend_test = HERE / "test_floor_frontend.py"
    if not frontend_test.is_file():
        failures.append("frontend floor test: test_floor_frontend.py not found")
    else:
        has_pw = subprocess.run(
            [sys.executable, "-c", "import playwright"],
            capture_output=True,
        ).returncode == 0
        if not has_pw:
            print("  skip  frontend floor intercept (playwright not installed)")
        else:
            ft = subprocess.run(
                [sys.executable, str(frontend_test)],
                capture_output=True, text=True)
            if ft.returncode != 0 or "FRONTEND FLOOR TEST PASSED" not in ft.stdout:
                failures.append(
                    f"frontend floor test: exit {ft.returncode}; "
                    f"stdout={ft.stdout[-400:]!r} stderr={ft.stderr[-400:]!r}")
            else:
                print("  ok    frontend floor intercept test passed")

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
