#!/usr/bin/env python3
"""Deterministic seam over Design I/O run artifacts. No dependencies.

Gates the run-level controls that the skills also declare in prose:
  G1 success shape       - L1-L6 present; every L6 item is Given/When/Then
  G2 evidence/point-back - every L6 item has one complete evidence row and
                           every finding has issue/source/fix/severity
  G3 verdict earned      - one explicit verdict; Pass requires all evidence to
                           pass and every blocking finding to have a closure
  G4 recirculation bound - closure coverage prevents blockers being dropped;
                           the two-cycle stop is machine-counted (vNext S4:
                           an unclosed blocking finding with rounds >= 2
                           must narrate close_reason: escalated-stop)
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
                           list (existence only; legacy reports unaffected).
                           S3: when the statement declares the five-state x
                           page sampling matrix, every spec-declared cell
                           needs sampling evidence or an explicit
                           unreviewed entry with a reason (gap check).
                           S6: the effective tier P3 makes the matrix block
                           mandatory (full-profile sampling obligation)
  G10 design decisions   - conditional: when the decision report carries DD
                           entry blocks (appended after the verbatim top
                           block), entries must satisfy the design-decision
                           machine face — tier/status enums, tier recording
                           obligations, supersedes existence + acyclicity,
                           preview decision_id linkage, R3 dd: challenge
                           resolution, and the stale three-exit review
  G6 method semantics    - conditional (S3): manifest entries carrying the
                           optional method-semantics keys must satisfy the
                           nine-value method enum, observation/interpret-
                           ation separation, and scope; human-subject
                           evidence missing population+ethics is unusable
                           and can never support a pass ledger row
  G2 dimensions          - conditional (S3): interaction-track findings may
                           annotate dimension/face/basis; subjective faces
                           are judgment class — advisory only, judgment
                           source declared, agent-judgment derives low
  G8 run-level registry  - conditional (S3): a craft-guard.md in the run
                           root is evaluated against the shared registry
                           parser; P2/P3 demand one audit row per advisory
                           entry (full predicate evaluation), P1 allows the
                           touch-related subset
  G12 tier boundary      - conditional (S4): when plan.md carries a
                           run-profile block, the actual declaration touch
                           (contract diff vs the bind snapshot, finding
                           routes, E-tier DD entries, blocking count, spec
                           L6 growth) must fit the declared tier's allowed
                           face; violations emit E1-E5 escalation signals
                           and require a recorded run-profile upgrade
                           (escalate-and-rewalk, never exemption)

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

Forgery boundary (ADR-0033 D12): a skeleton point-back carrying
``audited: false`` passes non-strict validation but is rejected by
--strict / --require-evidence / --require-coverage with the AUDIT.unaudited
finding; a present-but-ambiguous marker (duplicate, indented, commented,
or malformed) is likewise rejected with AUDIT.ambiguous_marker — no new
gate number; the marker facts come from the single audit_preferences
module. --require-preview alone does not reject: the preview confirmation
is a pre-audit floor and may legitimately precede the audit.
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

# Audit-preferences forgery boundary (ADR-0033 D12, issue #67): the marker
# facts are parsed by the single deep module; the strict-mode rejection
# policy is wired here beside the other require-flag findings.
from design_playbook.scripts.audit_preferences import (  # noqa: E402
    parse_audit_marker,
)
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
from design_playbook.scripts.shaping_log import (  # noqa: E402
    SHAPING_LOG,
    ShapingLogError,
    parse_shaping_log,
)

# G10 design-decision gate (vNext S2): fires only when the decision report
# carries DD entry blocks; discovery mirrors G9 (--decision-report explicit
# or <run-root>/decision-report.md).
from design_playbook.scripts.dd_entries import DD_HEADING  # noqa: E402
from design_playbook.scripts.g10_design_decisions import check_g10  # noqa: E402
from design_playbook.scripts.repair_rounds import check_rounds  # noqa: E402
from design_playbook.scripts.run_profile import validate_run_profile  # noqa: E402

# vNext S3 gates: method-semantics keys (G6-adjacent), interaction-track
# dimension annotations (G2-adjacent), sampling-matrix gaps (G11), and the
# run-level registry coverage (G8, sharing the rules_registry parser).
from design_playbook.scripts.g8_run_registry import (  # noqa: E402
    check_g8_run,
    load_registry,
)
from design_playbook.scripts.g11_coverage import check_sampling_matrix  # noqa: E402
from design_playbook.scripts.interaction_dimensions import (  # noqa: E402
    check_dimensions,
)
from design_playbook.scripts.method_semantics import check_method_semantics  # noqa: E402

# vNext S4 gates: G12 tier boundary (contract diff vs the declared face,
# E1-E6 escalation accounting) over the run-profile block and the G7 bind
# snapshot; runs without a run-profile block are not re-checked.
from design_playbook.scripts.dd_entries import parse_dd_entries  # noqa: E402
from design_playbook.scripts.escalation_signals import effective_tier  # noqa: E402
from design_playbook.scripts.g12_tier_boundary import (  # noqa: E402
    CRITERION_PATH,
    bind_fields,
    check_g12,
    contract_touch,
    load_bind_snapshot,
    load_effective_contract,
)


def _audit_marker_findings(
    pointback_text: str,
    *,
    require_evidence: bool,
    require_coverage: bool,
) -> list[Finding]:
    """Reject unaudited or ambiguous markers when audit gates are engaged."""
    engaged_flags = [
        flag for flag, on in (
            ("--require-evidence", require_evidence),
            ("--require-coverage", require_coverage),
        ) if on
    ]
    marker = parse_audit_marker(pointback_text)
    if not engaged_flags or not marker.present or marker.audited is True:
        return []
    engaged = " / ".join(engaged_flags)
    if marker.audited is False:
        return [finding(
            "AUDIT.unaudited",
            f"AUDIT: point-back carries 'audited: false' (skeleton, not "
            f"audited) while {engaged} is engaged — an unaudited skeleton "
            "cannot satisfy audit obligations",
            owner="point-back.md#audited",
            expected="an audited point-back, or no require flags",
            actual="audited: false with require flags engaged",
            repair="Run the ui-evaluator audit and replace the skeleton, "
                   "or drop the require flags for this unaudited run",
        )]
    return [finding(
        "AUDIT.ambiguous_marker",
        f"AUDIT: point-back has an ambiguous or malformed 'audited:' marker "
        f"({marker.marker_count} candidate(s)) while {engaged} is engaged",
        owner="point-back.md#audited",
        expected="exactly one unindented 'audited: true|false' marker",
        actual="present but ambiguous audit marker",
        repair="Remove duplicate or malformed audited markers, then run the "
               "ui-evaluator audit before claiming audited: true",
    )]


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
    profile = facts.run_profile
    if profile is not None:
        for error in validate_run_profile(profile):
            errs.append(finding(
                "G12.run_profile",
                f"run-profile invalid: {error}",
                owner="plan.md#run-profile",
                expected="supported v1 run-profile with valid tier and confirmation",
                actual=error,
                repair="Fix the run-profile block before running vNext gates",
            ))
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
    errs += _audit_marker_findings(
        pointback_text,
        require_evidence=require_evidence,
        require_coverage=require_coverage,
    )
    # G4 rounds (vNext S4): the two-cycle stop is machine-counted — an
    # unclosed blocking finding at rounds >= 2 must narrate escalated-stop.
    # Fires only when the report carries round annotations or a close_reason
    # (legacy reports without them stay silent).
    errs += check_rounds(pointback_text, verdict_facts=facts.verdict)
    # G11 (vNext S1): six-block reports must carry a Coverage statement with
    # the exhaustive status + explicit unreviewed list (existence only).
    errs += check_coverage(pointback_text, required=require_coverage)
    # G11 sampling matrix (vNext S3, Q3=A): when the statement declares the
    # five-state x page matrix, every spec-declared cell needs sampling
    # evidence or an explicit unreviewed entry with a reason.
    # vNext S6: the effective tier P3 makes the matrix block itself
    # mandatory (loop-prototype 1.2 "sampling matrix fully executed").
    errs += check_sampling_matrix(
        pointback_text, spec_text, evidence_dir=ed, tier=(
            effective_tier(profile.tier, profile.upgrades)
            if profile is not None else None
        ))
    # G2 dimensions (vNext S3): dimension/face/basis annotations on findings
    # — subjective faces are judgment class (advisory only, source declared).
    errs += check_dimensions(pointback_text)
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
    # G6 method semantics (vNext S3): the optional five keys are validated
    # where they live (the manifest); pass rows must not rest on unusable
    # human-subject evidence. Old manifests without the keys stay silent.
    method_rows = [
        (values[0].split()[0], row.values("result")[0], row.artifact_token)
        for row in facts.ledger.rows
        if (values := row.values("criterion")) and values[0]
        and row.values("result") and row.values("result")[0]
        and row.raw_observed
    ]
    method_errs, method_warns = check_method_semantics(entries, method_rows)
    errs += method_errs
    warns += method_warns
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
    shaping_events: list[dict] | None = (
        list(facts.shaping_events) if facts.shaping_events is not None else None
    )
    if sd is not None and (sd / Path(SHAPING_LOG).name).is_file():
        errs += check_g9(
            sd,
            project_dir=Path(contract_project) if contract_project else None,
            run_dir=Path(contract_run) if contract_run else rr,
        )
        # Explicit --shaping-dir may point outside the captured run root.
        # Default discovery already parsed the same log into RunFacts.
        if shaping_dir is not None:
            try:
                shaping_events = parse_shaping_log(
                    (sd / SHAPING_LOG).read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ShapingLogError):
                shaping_events = None

    # G10 (conditional): a decision report carrying DD entry blocks engages
    # the design-decision gate (top block stays verbatim; reports without
    # entry blocks keep passing — the extension is additive).
    dr_g10 = dr if dr is not None else (
        rr / "decision-report.md" if rr is not None else None
    )
    report_text = facts.decision_report_text if dr is None else ""
    if dr is not None and dr.is_file():
        try:
            report_text = dr.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            report_text = ""
    if report_text and DD_HEADING.search(report_text):
        errs += check_g10(
            report_text,
            report_path=dr_g10,
            preview_dir=pd,
            shaping_events=shaping_events,
            pointback_text=pointback_text,
            baseline_state=facts.baseline_state,
            run_profile_tier=(
                effective_tier(profile.tier, profile.upgrades)
                if profile is not None else None
            ),
        )

    # G8 run level (vNext S3): a craft-guard.md in the run root is checked
    # against the registry (shared parser). P2/P3 demand one audit row per
    # advisory entry; P1 and tier-less legacy runs keep the subset freedom.
    if facts.craft_guard_exists:
        try:
            craft_text = facts.craft_guard_text
            registry_entries, _ = load_registry()
        except (OSError, UnicodeError):
            errs.append(finding(
                "G8.run_registry",
                "G8 run: craft-guard.md present but the audit log or the "
                "registry could not be read",
                owner="craft-guard.md",
                expected="readable craft-guard.md and rules.md",
                actual="read error",
                repair="Restore the files or drop the audit log",
            ))
        else:
            errs += check_g8_run(craft_text, registry_entries, (
                effective_tier(profile.tier, profile.upgrades)
                if profile is not None else None
            ))

    # G12 tier boundary + escalation signals (vNext S4): fires when plan.md
    # carries a run-profile block; legacy runs without the block are not
    # re-checked. The contract diff basis is the G7 bind snapshot; without
    # contract paths the route / decision / blocking faces still fire.
    if profile is not None:
        touch = None
        bound_criteria = None
        if contract_project and contract_run:
            snapshot = load_bind_snapshot(Path(contract_run))
            effective = load_effective_contract(Path(contract_project))
            if snapshot is not None and effective is not None:
                bound = bind_fields(snapshot)
                if bound is not None:
                    touch = contract_touch(bound, effective)
                    bound_criteria = sum(
                        1 for path in bound if CRITERION_PATH.match(path))
        dd_explore = any(
            entry.tier == "explore" for entry in facts.decision_entries
        ) if dr is None else bool(
            report_text and DD_HEADING.search(report_text)
            and any(entry.tier == "explore"
                    for entry in parse_dd_entries(report_text))
        )
        g12_errs, g12_warns, _signals = check_g12(
            profile,
            pointback_text=pointback_text,
            touch=touch,
            bound_criteria=bound_criteria,
            spec_l6_count=len(_l6_items(spec_text)),
            dd_explore=dd_explore,
        )
        errs += g12_errs
        warns += g12_warns
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
