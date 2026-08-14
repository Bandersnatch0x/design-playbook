#!/usr/bin/env python3
"""Deterministic seam over Design I/O run artifacts. No dependencies.

Gates the run-level controls that the skills also declare in prose:
  G1 success shape       - L1-L6 present; every L6 item is Given/When/Then
  G2 evidence/point-back - every L6 item has one complete evidence row and
                           every finding has issue/source/fix/severity
  G3 verdict earned      - one explicit verdict; Pass requires all evidence to
                           pass and every blocking finding to have a closure
  G4 recirculation bound - closure coverage prevents blockers being dropped;
                           the two-cycle stop policy remains agent-enforced
  G5 preview confirm     - conditional: if preview occurred, require a
                           confirmed record whose report_ref matches the
                           current decision report (when provided)
  G6 evidence binding    - conditional: if a ledger `observed` references an
                           `evidence/` artifact, require the artifact to exist
                           and a manifest entry to bind it to the matching
                           L6.<n> (multi-entry: latest wins)
  G9 shaping exit        - conditional: when a shaping session exists
                           (shaping-log.jsonl), events must use the closed
                           enum, a projected mapping record must exist, the
                           derived queue.json must match re-derivation, and
                           (with contract paths) open=0 + assumed all acked
  G11 coverage statement - conditional: vNext six-block reports must carry
                           a Coverage statement with the exhaustive-review
                           completion status and the explicit unreviewed
                           list (existence only; legacy reports unaffected)

Reads plain Markdown, so it is host-neutral: it accepts artifacts produced by
any agent (Claude Code, Codex) that follow the declared shape.

Usage:
  validate_run.py <spec.md> <point-back.md>
      [--preview-dir <path>] [--decision-report <path>]
      [--evidence-dir <path>] [--run-root <path>]
      [--require-preview] [--require-evidence] [--strict]
      [--format text|json]
Exit 0 + "RUN OK"; exit 1 + one line per artifact violation; exit 2 on usage
or artifact I/O errors. JSON mode projects the same findings as a list.

Strict quality mode (opt-in):
  --require-preview   fail when preview did not occur (G5 must fire)
  --require-evidence  fail when no evidence/ binding is present (G6 must fire)
  --require-coverage  fail when the report lacks a Coverage statement (G11)
  --strict            shorthand for all require flags
"""
import argparse
import sys
from pathlib import Path

# One import seam (ADR-0022): package root on sys.path once, then absolute
# design_playbook.* imports below. No per-runtime sys.path adapters.
_PKG_ROOT = Path(__file__).resolve().parents[1]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

# Structured diagnostics (vNext ticket 02): one Finding model feeds text and
# JSON projections. Rule IDs stay stable; text keeps historical messages.
from design_playbook.scripts._diagnostics import (  # noqa: E402
    OUTPUT_FORMATS,
    Finding,
    finding,
    render_json,
    render_text,
    usage_finding,
)

# Gate modules own the individual rule sets (ADR-0023): the orchestrator
# below only wires artifact paths, strict-mode flags, and finding order.
from design_playbook.scripts.g1_spec import _l6_items, check_spec  # noqa: E402
from design_playbook.scripts.g2_g4_pointback import check_pointback  # noqa: E402
from design_playbook.scripts.g5_preview import check_preview  # noqa: E402
from design_playbook.scripts.g6_evidence import (  # noqa: E402
    check_evidence,
    manifest_read_findings,
)
from design_playbook.scripts.g6_warnings import (  # noqa: E402
    _ledger_has_evidence_binding,
    check_manifest_ts_warnings,
    check_superseded_ledger_warnings,
)

# Preview occurrence facts for the strict-mode G5 check; G5 rules themselves
# live in g5_preview.py (C1 / ADR-0004 keeps the integrity rules bundled).
from design_playbook.scripts.g6_records import ledger_observed  # noqa: E402
from design_playbook.scripts.run_facts import RunFacts, capture_run_facts  # noqa: E402

try:
    from design_playbook.scripts.g7_contract_drift import check_g7 as check_g7
except ImportError:  # pragma: no cover - optional until package scripts co-locate
    check_g7 = None  # type: ignore[assignment]

# G9 shaping-exit gate (vNext S1, decision Q8=A): fires only when a shaping
# session exists — either via --shaping-dir or discovered under --run-root.
from design_playbook.scripts.g9_shaping import check_g9  # noqa: E402
from design_playbook.scripts.g11_coverage import check_coverage  # noqa: E402
from design_playbook.scripts.shaping_log import SHAPING_LOG  # noqa: E402


def run(
        spec_path: str,
        pb_path: str,
        preview_dir: str | None = None,
        decision_report: str | None = None,
        evidence_dir: str | None = None,
        run_root: str | None = None,
        require_preview: bool = False,
        require_evidence: bool = False,
        contract_project: str | None = None,
        contract_run: str | None = None,
        shaping_dir: str | None = None,
        require_coverage: bool = False,
        run_facts: RunFacts | None = None) -> tuple[list[Finding], list[Finding]]:
    """Return ``(errors, warnings)``. Errors fail the run; warnings do not."""
    errs: list[Finding] = []
    warns: list[Finding] = []
    pd = Path(preview_dir) if preview_dir else None
    ed = Path(evidence_dir) if evidence_dir else None
    rr = Path(run_root) if run_root else None
    facts = run_facts or capture_run_facts(
        spec_path=Path(spec_path), pointback_path=Path(pb_path),
        preview_dir=pd, evidence_dir=ed, run_root=rr,
    )
    operational_errors = tuple(
        error for error in facts.read_errors if error.artifact != "manifest"
    )
    if operational_errors:
        failure = operational_errors[0]
        if failure.code == "missing":
            raise FileNotFoundError(
                2, "No such file or directory", str(failure.path)
            )
        raise OSError(failure.message)
    spec_text = facts.spec_text
    pointback_text = facts.pointback_text
    observed_rows = ledger_observed(pointback_text, facts.ledger)
    entries = list(facts.manifest_entries)
    errs += manifest_read_findings(facts.read_errors)
    errs += check_spec(spec_text)
    errs += check_pointback(
        pointback_text, len(_l6_items(spec_text)),
        ledger_facts=facts.ledger, verdict_facts=facts.verdict,
    )
    # G11 (vNext S1): six-block reports must carry a Coverage statement with
    # the exhaustive status + explicit unreviewed list (existence only).
    errs += check_coverage(pointback_text, required=require_coverage)
    preview_snapshot = facts.preview
    dr = Path(decision_report) if decision_report else None
    if require_preview and (
        preview_snapshot is None or not preview_snapshot.occurred
    ):
        errs.append(finding(
            "G5.require_preview",
            "G5 preview: --require-preview set but preview did not occur "
            "(pass --preview-dir with preview artifacts)",
            owner="--require-preview",
            expected="preview artifacts present",
            actual="preview did not occur",
            repair="Pass --preview-dir with preview artifacts or drop the flag",
        ))
    errs += check_preview(pd, dr, preview_snapshot)
    if require_evidence:
        if ed is None or not ed.is_dir():
            errs.append(finding(
                "G6.require_evidence_dir",
                "G6 evidence: --require-evidence set but --evidence-dir "
                "is missing or not a directory",
                owner="--require-evidence",
                expected="existing --evidence-dir",
                actual="missing or not a directory",
                repair="Pass --evidence-dir to a real evidence directory",
            ))
        elif not _ledger_has_evidence_binding(pointback_text, observed_rows):
            errs.append(finding(
                "G6.require_evidence_binding",
                "G6 evidence: --require-evidence set but no ledger "
                "`observed` references an evidence/ artifact",
                owner="point-back.md#evidence",
                expected="at least one observed: evidence/… row",
                actual="no evidence/ binding",
                repair="Bind at least one L6 criterion to an evidence artifact",
            ))
    errs += check_evidence(
        pointback_text, len(_l6_items(spec_text)), ed, rr,
        observed_rows=observed_rows, entries=entries,
    )
    warns += check_manifest_ts_warnings(ed, entries=entries)
    warns += check_superseded_ledger_warnings(
        pointback_text, ed, observed_rows=observed_rows, entries=entries,
    )
    if contract_project and contract_run:
        if check_g7 is None:
            errs.append(finding(
                "G7.missing_binding",
                "G7 contract: g7_contract_drift module unavailable",
                owner="validate_run.py",
                expected="packaged g7_contract_drift.py",
                actual="import failed",
                repair="Install the design-playbook scripts package intact",
            ))
        else:
            errs += check_g7(Path(contract_project), Path(contract_run))
    # G9 (conditional): a shaping session on disk engages the exit gate.
    sd = Path(shaping_dir) if shaping_dir else (
        rr / "shaping" if rr is not None else None
    )
    if sd is not None and (sd / Path(SHAPING_LOG).name).is_file():
        errs += check_g9(
            sd,
            project_dir=Path(contract_project) if contract_project else None,
            run_dir=Path(contract_run) if contract_run else rr,
        )
    return errs, warns


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="validate_run.py",
        description="Deterministic seam over Design I/O run artifacts.",
    )
    parser.add_argument("spec", help="path to spec.md")
    parser.add_argument("point_back", help="path to point-back.md")
    parser.add_argument(
        "--preview-dir",
        default=None,
        help="optional path to .scratch/<run>/preview/ for G5",
    )
    parser.add_argument(
        "--decision-report",
        default=None,
        help="optional path to current decision report for G5 report_ref match",
    )
    parser.add_argument(
        "--evidence-dir",
        default=None,
        help="optional path to .scratch/<run>/evidence/ for G6",
    )
    parser.add_argument(
        "--run-root",
        default=None,
        help="optional run root for resolving evidence/ paths in G6 "
             "(defaults to --evidence-dir parent)",
    )
    parser.add_argument(
        "--require-preview",
        action="store_true",
        help="strict mode: fail when preview did not occur",
    )
    parser.add_argument(
        "--require-evidence",
        action="store_true",
        help="strict mode: fail when no evidence/ binding is present",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="shorthand for --require-preview --require-evidence "
             "--require-coverage",
    )
    parser.add_argument(
        "--require-coverage",
        action="store_true",
        help="strict mode: fail when the point-back lacks a Coverage "
             "statement block even in legacy shape",
    )
    parser.add_argument(
        "--format",
        default="text",
        dest="output_format",
        help="output projection: text (default) or json",
    )
    parser.add_argument(
        "--contract-project",
        default=None,
        help="optional project dir containing contract.json for G7",
    )
    parser.add_argument(
        "--contract-run",
        default=None,
        help="optional run dir containing contract-bind.json for G7",
    )
    parser.add_argument(
        "--shaping-dir",
        default=None,
        help="optional path to .scratch/<run>/shaping/ for G9 "
             "(defaults to <run-root>/shaping when --run-root is set)",
    )
    args = parser.parse_args(argv[1:])
    if args.strict:
        args.require_preview = True
        args.require_evidence = True
        args.require_coverage = True
    return args


def main(argv: list[str]) -> int:
    try:
        args = _parse_args(argv)
    except SystemExit as exc:
        # argparse already printed usage
        code = exc.code if isinstance(exc.code, int) else 2
        return code if code else 2

    fmt = (args.output_format or "text").casefold()
    if fmt not in OUTPUT_FORMATS:
        bad = usage_finding(
            f"unknown --format {args.output_format!r}; expected text or json"
        )
        print(f"RUN ERROR: {bad.message}")
        return 2

    try:
        errs, warns = run(
            args.spec,
            args.point_back,
            preview_dir=args.preview_dir,
            decision_report=args.decision_report,
            evidence_dir=args.evidence_dir,
            run_root=args.run_root,
            require_preview=args.require_preview,
            require_evidence=args.require_evidence,
            contract_project=args.contract_project,
            contract_run=args.contract_run,
            shaping_dir=args.shaping_dir,
            require_coverage=args.require_coverage,
        )
    except (OSError, UnicodeError) as exc:
        if fmt == "json":
            print(render_json([finding(
                "USAGE.io_error",
                f"cannot read artifacts: {exc}",
                owner="validate_run.py",
                expected="readable spec and point-back paths",
                actual=str(exc),
                repair="Fix paths or file encodings",
            )], []))
        else:
            print(f"RUN ERROR: cannot read artifacts: {exc}")
        return 2

    if fmt == "json":
        print(render_json(errs, warns), end="")
    else:
        print(render_text(errs, warns), end="")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
