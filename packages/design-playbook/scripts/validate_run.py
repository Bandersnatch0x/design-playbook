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
  G10 design decisions   - conditional: when the decision report exists, its
                           top block must declare scene / density / template
                           / regions / components (T-153); when it also
                           carries DD entry blocks (appended after the
                           verbatim top block), entries must satisfy the
                           design-decision machine face — tier/status enums,
                           tier recording obligations, supersedes existence +
                           acyclicity, preview decision_id linkage, R3 dd:
                           challenge resolution, and the stale three-exit
                           review
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
  G13 reference contract - conditional: when the run carries
                           reference/contract.md (ADR-0011), it must declare
                           every contract-template axis; a run without
                           reference material is never a finding (T-153)

Reads plain Markdown, so it is host-neutral: it accepts artifacts produced by
any agent (Claude Code, Codex) that follow the declared shape.

Usage:
  validate_run.py <spec.md> <point-back.md>
      [--preview-dir <path>] [--decision-report <path>]
      [--evidence-dir <path>] [--run-root <path>]
      [--legacy] [--require-preview] [--require-evidence]
      [--require-coverage] [--strict] [--format text|json]
Exit 0 + "RUN OK"; exit 1 + one line per artifact violation; exit 2 on usage
or artifact I/O errors. JSON mode projects the same findings as a list.
In-process consumers construct ``RunInputs`` and call ``run(inputs)``; their
defaults stay legacy so existing projections (run_status, aggregate) keep
their published meaning. Only the CLI default changed; a caller that wants
the complete profile requirement sets ``RunInputs.require_run_profile`` and,
for repair-proof obligations, ``RunInputs.require_repair_evidence``.

Strict quality mode (CLI default, fail closed):
  --require-preview   fail when preview did not occur (G5 must fire)
  --require-evidence  fail when no evidence/ binding is present (G6 must fire)
  --require-coverage  fail when the report lacks a Coverage statement (G11)
  --strict            shorthand for all three require flags
  --legacy            explicit opt-out for old reports: the three require
                      checks above stay disengaged. Cannot be combined
                      with --strict or any --require-* flag.
A bare invocation (no strictness flag at all) behaves as --strict. Passing
one --require-* flag explicitly keeps its historical meaning: only that
check engages (so --require-preview alone does not inspect the audit
marker, and --require-coverage checks G11 alone rather than turning on
preview, evidence, run-profile, baseline, or repair proof).

Repair evidence (T-152 / T-159, ADR-0045 2026-11-07 amendment):
  Complete acceptance (bare or --strict) derives one proof obligation from
  every blocking finding that exactly one closure claims to close. The
  finding must name its L6 criteria (`criteria:`), the spec must declare a
  known proof type for each, visible-state (screenshot) repairs must carry one
  named before/after pair belonging to that closure, and the criterion's
  current ledger row must pass. Before must be the finding's own failure
  artifact; after must be the exact artifact the current ledger row observes.
  --legacy and explicit --require-* selections keep the structural reading:
  an annotation that exists is validated through the same G6 owner, but no
  pair or proof-type obligation is invented and the run must not be reported
  as complete acceptance. Artifact bytes are frozen during the explicit
  snapshot capture; supplying a snapshot without those facts fails as
  unavailable rather than re-reading disk.

Run profile (ADR-0029 D2):
  Every mode reads one plan location: <run-root>/plan.md when --run-root is
  given, otherwise the positional point-back's own directory. There is no
  existence fallback and no cwd, spec-dir, or ancestor search. A bare or
  --strict call requires that plan's run-profile block, so a missing plan,
  an empty plan, and a readable plan without the block all exit 1 with
  G12.run_profile. --legacy and an explicit --require-* selection do not
  add the profile requirement, but they read the same plan: a profile the
  shared parser recognizes as malformed fails G12 in every mode. A plan
  read or encoding failure stays an operational exit 2.

Forgery boundary (ADR-0033 D12): a skeleton point-back carrying
``audited: false`` is rejected by the default CLI and by
--strict / --require-evidence / --require-coverage with the AUDIT.unaudited
finding; a present-but-ambiguous marker (duplicate, indented, commented,
or malformed) is likewise rejected with AUDIT.ambiguous_marker — no new
gate number; the marker facts come from the single audit_preferences
module. --require-preview alone does not reject: the preview confirmation
is a pre-audit floor and may legitimately precede the audit. When the user
legitimately skips the optional audit, the skeleton keeps its marker, its
skip reason, and its limitation statement; ``--legacy`` checks that
report's structure only, and its RUN OK must never be reported as an audit
pass.
"""
import argparse
import hashlib
import sys
from dataclasses import dataclass
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
from design_playbook.scripts.g1_spec import (  # noqa: E402
    SpecificationProjectionError,
    _l6_items,
    check_spec,
    project_proof_requirements,
)
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
from design_playbook.scripts.run_facts import (  # noqa: E402
    STATE_MISSING,
    BaselineCapture,
    RunFacts,
    capture_run_facts,
)

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

# G13 reference contract (T-153 / research I4): fires only when the run
# carries reference/contract.md; absence stays silent (ADR-0011 s5).
from design_playbook.scripts.g13_reference_contract import (  # noqa: E402
    check_g13,
    contract_unreadable_finding,
)
from design_playbook.scripts.repair_rounds import check_rounds  # noqa: E402
from design_playbook.scripts.repair_evidence import (  # noqa: E402
    check_repair_evidence,
)
from design_playbook.scripts.run_profile import validate_run_profile  # noqa: E402

# vNext S3 gates: method-semantics keys (G6-adjacent), interaction-track
# dimension annotations (G2-adjacent), sampling-matrix gaps (G11), and the
# run-level registry coverage (G8, sharing the rules_registry parser).
from design_playbook.scripts.g8_run_registry import (  # noqa: E402
    check_g8_run,
    load_registry,
)
from design_playbook.scripts.rules_registry import (  # noqa: E402
    RegistryLayoutError,
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
            repair="Run the ui-evaluator audit and replace the skeleton; "
                   "if the user legitimately skipped that optional audit, "
                   "keep the marker, skip reason, and limitation statement "
                   "and check structure with --legacy (never as an audit "
                   "pass)",
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


@dataclass(frozen=True)
class RunInputs:
    """One validator invocation: artifact paths, strict-mode flags, and an
    optional pre-captured run snapshot. The CLI builds it from argparse;
    in-process callers construct it directly."""

    spec_path: str
    point_back_path: str
    preview_dir: str | None = None
    decision_report: str | None = None
    evidence_dir: str | None = None
    run_root: str | None = None
    require_preview: bool = False
    require_evidence: bool = False
    require_coverage: bool = False
    contract_project: str | None = None
    contract_run: str | None = None
    shaping_dir: str | None = None
    run_facts: RunFacts | None = None
    require_run_profile: bool = False
    # Complete acceptance (bare or --strict CLI) also verifies a present
    # design baseline from the captured RunFacts snapshot. The default keeps
    # in-process, selective, legacy, status and aggregate callers read-only;
    # completeness is never inferred from arbitrary --require-* combinations.
    require_baseline_verification: bool = False
    # Complete acceptance derives repair-proof obligations from each uniquely
    # closed blocking finding. Set from the same complete-profile value; an
    # explicit --require-* selection keeps its narrower structural reading.
    require_repair_evidence: bool = False


BASELINE_FINDINGS_SCHEMA = "design-baseline-findings/v1"
_BASELINE_SEVERITIES = frozenset({"error", "warning", "advisory"})


def _baseline_binding_finding(
        message: str, *, owner: str, repair: str) -> Finding:
    """Named blocking error for an unusable/absent baseline capture."""
    return finding(
        "baseline.binding-invalid",
        message,
        owner=owner,
        expected="verified baseline binding (fresh, identity-matched capture)",
        actual=message,
        repair=repair,
    )


def _baseline_binding_identity(value: object) -> tuple[object, object] | None:
    """Normalize one baseline binding the way the owner reports it.

    A non-dict (including ``None``) means "no binding"; otherwise the owner's
    path/sha256 pair is compared. Comparing normalized values keeps a genuine
    owner failure (e.g. ready state without a binding) from being rewritten
    as a snapshot mismatch, while a changed binding still fails.
    """
    if not isinstance(value, dict):
        return None
    return (value.get("path"), value.get("sha256"))


def _baseline_acceptance_findings(
        inputs: RunInputs,
        facts: RunFacts,
) -> tuple[list[Finding], list[Finding]]:
    """Project the captured baseline result; never re-read or re-verify.

    Complete acceptance consumes one immutable capture. The baseline owner is
    not called from ``run()`` and no baseline/DESIGN/source file is reopened
    here: a supplied snapshot stays exactly as captured. Baseline codes become
    ``rule_id`` values, findings paths become owners, and severities/messages
    are preserved (errors block; warnings and advisories stay visible).
    """
    errs: list[Finding] = []
    warns: list[Finding] = []
    rr = Path(inputs.run_root) if inputs.run_root else None
    run_authority = (
        rr.resolve() if rr is not None
        else Path(inputs.point_back_path).resolve().parent
    )
    if inputs.contract_run:
        declared_run = Path(inputs.contract_run).resolve()
        if declared_run != run_authority:
            errs.append(_baseline_binding_finding(
                f"--contract-run {str(declared_run)!r} is not this run's root "
                f"{str(run_authority)!r}; complete acceptance takes the run "
                "from --run-root or the explicit point-back parent",
                owner="--contract-run",
                repair="Pass the same run root to --contract-run, or omit it",
            ))

    payload = facts.baseline_findings
    if payload is None:
        if facts.baseline_state_error is not None:
            errs.append(_baseline_binding_finding(
                facts.baseline_state_error,
                owner="design-baseline/state.json",
                repair="Repair the baseline state through design-baseline "
                       "prepare/confirm and re-run acceptance",
            ))
        elif facts.artifact_state("baseline") != STATE_MISSING:
            errs.append(_baseline_binding_finding(
                "baseline state is present but complete acceptance has no "
                "fresh captured result; pass --contract-project so the "
                "baseline owner can verify it",
                owner="--contract-project",
                repair="Pass --contract-project <project root> (and --run-root "
                       "when it differs from the point-back directory)",
            ))
        # No state at all: complete acceptance adds no DESIGN.md obligation.
        return errs, warns

    if not inputs.contract_project:
        errs.append(_baseline_binding_finding(
            "captured baseline result has no authorized project; complete "
            "acceptance requires the explicit --contract-project",
            owner="--contract-project",
            repair="Pass --contract-project <project root>",
        ))
        return errs, warns
    expected_project = str(Path(inputs.contract_project).resolve())
    if facts.baseline_capture_project != expected_project:
        errs.append(_baseline_binding_finding(
            f"captured baseline project {facts.baseline_capture_project!r} "
            f"does not match --contract-project {expected_project!r}",
            owner="--contract-project",
            repair="Recapture from the project root this invocation verifies",
        ))
    if facts.baseline_capture_run != str(run_authority):
        errs.append(_baseline_binding_finding(
            f"captured baseline run {facts.baseline_capture_run!r} does not "
            f"match this run {str(run_authority)!r}",
            owner="--run-root",
            repair="Capture from this run root (--run-root / point-back parent)",
        ))
    if errs:
        # A capture for another identity must not be projected as this run's.
        return errs, warns
    # The findings payload is only meaningful for the state text that was
    # verified. Recompute the recorded digest from the frozen text and bind
    # the payload's waiver/baseline identity to that frozen state, so a
    # supplied snapshot cannot pair clean findings with an altered state
    # (e.g. decision=None) or a missing digest. No file is reopened here.
    state_text = facts.baseline_state_text
    state_digest = facts.baseline_capture_state_sha256
    if not state_text or not state_digest:
        errs.append(_baseline_binding_finding(
            "captured baseline result lacks its frozen state text or digest",
            owner="design-baseline/state.json",
            repair="Re-capture with the packaged baseline owner; never "
                   "hand-build a findings-only snapshot",
        ))
        return errs, warns
    actual_digest = hashlib.sha256(state_text.encode("utf-8")).hexdigest()
    if actual_digest != state_digest:
        errs.append(_baseline_binding_finding(
            "captured baseline state text does not match its recorded digest; "
            "the frozen result was modified after capture",
            owner="design-baseline/state.json",
            repair="Re-capture the baseline; never edit a frozen capture",
        ))
        return errs, warns
    frozen_state = facts.baseline_state
    if not isinstance(frozen_state, dict):
        errs.append(_baseline_binding_finding(
            "captured baseline state text is not an object",
            owner="design-baseline/state.json",
            repair="Re-capture with the packaged baseline owner",
        ))
        return errs, warns
    waived_flag = payload.get("waived")
    status = frozen_state.get("status")
    captured_rows = payload.get("findings")
    captured_gate = payload.get("gate")
    has_error_row = isinstance(captured_rows, list) and any(
        isinstance(row, dict) and row.get("severity") == "error"
        for row in captured_rows)
    gate_failed = (
        isinstance(captured_gate, dict)
        and captured_gate.get("verdict") == "fail")
    if status == "ready":
        consistent = waived_flag is False
    elif status == "waived":
        # A valid waiver carries waived=True; the owner's rejected-waiver
        # capture legitimately carries waived=False plus a failing payload.
        consistent = waived_flag is True or (has_error_row and gate_failed)
    else:
        # Pending/ambiguous/unreadable states always carry a failure row.
        consistent = has_error_row and gate_failed
    if not consistent:
        errs.append(_baseline_binding_finding(
            f"captured findings and frozen state disagree on the waiver/state "
            f"(waived={waived_flag!r}, status={status!r})",
            owner="design-baseline/state.json",
            repair="Re-capture the baseline so findings and state come from "
                   "one verification",
        ))
        return errs, warns
    if status == "ready":
        if _baseline_binding_identity(payload.get("baseline")) != (
                _baseline_binding_identity(frozen_state.get("baseline"))):
            errs.append(_baseline_binding_finding(
                "captured findings binding does not match the frozen state "
                "baseline",
                owner="design-baseline/state.json",
                repair="Re-capture the baseline so findings and state come "
                       "from one verification",
            ))
            return errs, warns
    if payload.get("schema") != BASELINE_FINDINGS_SCHEMA:
        errs.append(_baseline_binding_finding(
            f"captured baseline findings schema is not {BASELINE_FINDINGS_SCHEMA}",
            owner="design-baseline/state.json",
            repair="Re-capture with the packaged baseline owner",
        ))
        return errs, warns
    rows = payload.get("findings")
    gate = payload.get("gate")
    gate_verdict = gate.get("verdict") if isinstance(gate, dict) else None
    if not isinstance(rows, list) or gate_verdict not in {"pass", "fail"}:
        errs.append(_baseline_binding_finding(
            "captured baseline findings payload is malformed",
            owner="design-baseline/state.json",
            repair="Re-capture with the packaged baseline owner",
        ))
        return errs, warns
    error_rows = 0
    for row in rows:
        if (
            not isinstance(row, dict)
            or row.get("severity") not in _BASELINE_SEVERITIES
            or not isinstance(row.get("code"), str)
            or not isinstance(row.get("path"), str)
            or not isinstance(row.get("message"), str)
        ):
            errs.append(_baseline_binding_finding(
                "captured baseline findings payload has a malformed row",
                owner="design-baseline/state.json",
                repair="Re-capture with the packaged baseline owner",
            ))
            return errs, warns
        projected = finding(
            row["code"],
            row["message"],
            owner=row["path"],
            expected="baseline satisfies its bound declaration and provenance",
            actual=row["message"],
            repair="Run `design-baseline findings <project> <run>` for the "
                   "full report, then repair the named baseline/source artifact",
            severity=row["severity"],
        )
        if row["severity"] == "error":
            error_rows += 1
            errs.append(projected)
        else:
            warns.append(projected)
    if gate_verdict == "fail" and error_rows == 0:
        errs.append(_baseline_binding_finding(
            "captured baseline gate failed without an error row",
            owner="design-baseline/state.json",
            repair="Re-capture with the packaged baseline owner",
        ))
    return errs, warns


def _proof_requirements(spec_text: str):
    """G1 proof requirements, or none when the spec cannot be projected.

    A malformed spec already fails G1 with named findings; this projection
    must not turn that into a traceback. No projection means no known proof
    type, so a complete-acceptance repair obligation stays blocked rather
    than guessing.
    """
    try:
        return project_proof_requirements(spec_text)
    except SpecificationProjectionError:
        return ()


def run(inputs: RunInputs) -> tuple[list[Finding], list[Finding]]:
    """Return ``(errors, warnings)``. Errors fail the run; warnings do not."""
    spec_path = inputs.spec_path
    pb_path = inputs.point_back_path
    decision_report = inputs.decision_report
    require_preview = inputs.require_preview
    require_evidence = inputs.require_evidence
    require_coverage = inputs.require_coverage
    contract_project = inputs.contract_project
    contract_run = inputs.contract_run
    shaping_dir = inputs.shaping_dir
    require_baseline_verification = inputs.require_baseline_verification
    errs: list[Finding] = []
    warns: list[Finding] = []
    pd = Path(inputs.preview_dir) if inputs.preview_dir else None
    ed = Path(inputs.evidence_dir) if inputs.evidence_dir else None
    rr = Path(inputs.run_root) if inputs.run_root else None
    # Narrow complete-acceptance probe: with no supplied snapshot and no
    # --run-root, the explicit point-back parent is where a present baseline
    # state may be *detected* (never where the project/DESIGN/source authority
    # comes from). Other optional artifacts keep their existing discovery.
    baseline_run_root = None
    if inputs.run_facts is None and require_baseline_verification:
        baseline_run_root = (
            rr if rr is not None else Path(pb_path).resolve().parent)
    facts = inputs.run_facts or capture_run_facts(
        spec_path=Path(spec_path), pointback_path=Path(pb_path),
        preview_dir=pd, evidence_dir=ed, run_root=rr,
        baseline_run_root=baseline_run_root,
    )
    # Operational read failures settle before profile policy (exit 2).
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
    # Snapshot only: the plan is never re-read here to fill a gap.
    profile = facts.run_profile
    if profile is not None or inputs.require_run_profile:
        for error in validate_run_profile(profile):
            errs.append(finding(
                "G12.run_profile",
                f"run-profile invalid: {error}",
                owner="plan.md#run-profile",
                expected="supported v1 run-profile with valid tier and confirmation",
                actual=error,
                repair="Fix the run-profile block before running vNext gates",
            ))
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
    # G4 repair evidence (T-152 / T-159): complete acceptance derives proof
    # obligations from each uniquely closed blocking finding - declared
    # criteria, known proof type, one named pair for visible-state repairs,
    # and a passing current retest. Legacy and explicit --require-* selections
    # validate annotations that exist without inventing new obligations.
    # Every reference resolves through the one G6 owner over frozen facts.
    errs += check_repair_evidence(
        pointback_text,
        entries,
        requirements=_proof_requirements(spec_text),
        ledger=facts.ledger,
        artifact_facts=facts.evidence_artifacts,
        require_complete=inputs.require_repair_evidence,
    )
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
            "G5 preview: --require-preview (or the CLI fail-closed default) "
            "is engaged but preview did not occur (pass --preview-dir with "
            "preview artifacts)",
            owner="--require-preview",
            expected="preview artifacts present",
            actual="preview did not occur",
            repair="Pass --preview-dir with preview artifacts so the "
                   "preview confirmation can be checked; --legacy is only "
                   "for structural inspection of an old or unaudited report "
                   "and does not waive the preview-confirmation requirement "
                   "for acceptance",
        ))
    errs += check_preview(pd, dr, preview_snapshot)
    if require_evidence:
        if ed is None or not ed.is_dir():
            errs.append(finding(
                "G6.require_evidence_dir",
                "G6 evidence: --require-evidence (or the CLI fail-closed "
                "default) is engaged but --evidence-dir is missing or not a "
                "directory",
                owner="--require-evidence",
                expected="existing --evidence-dir",
                actual="missing or not a directory",
                repair="Pass --evidence-dir to a real evidence directory",
            ))
        elif not _ledger_has_evidence_binding(pointback_text, observed_rows):
            errs.append(finding(
                "G6.require_evidence_binding",
                "G6 evidence: --require-evidence (or the CLI fail-closed "
                "default) is engaged but no ledger `observed` references an "
                "evidence/ artifact",
                owner="point-back.md#evidence",
                expected="at least one observed: evidence/… row",
                actual="no evidence/ binding",
                repair="Bind at least one L6 criterion to an evidence artifact",
            ))
    errs += check_evidence(
        pointback_text, len(_l6_items(spec_text)), ed, rr,
        observed_rows=observed_rows, entries=entries,
        # A supplied snapshot is never re-read: ``None`` (facts not captured)
        # becomes an explicit empty tuple, so every needed reference reports
        # G6.artifact_facts_unavailable instead of falling back to disk.
        artifact_facts=(
            facts.evidence_artifacts
            if facts.evidence_artifacts is not None else ()),
    )
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

    # G10 (conditional): a decision report engages the design-decision gate.
    # A present report is checked for its top-block axes (T-153); the DD
    # entry rules beyond that stay conditional on entry blocks existing
    # (top block stays verbatim; reports without entry blocks keep passing —
    # the extension is additive). No report at all is never a finding.
    dr_g10 = dr if dr is not None else (
        rr / "decision-report.md" if rr is not None else None
    )
    if dr is None or (
        rr is not None and dr.resolve() == (rr / "decision-report.md").resolve()
    ):
        # Standard path (default, or an explicit path naming the captured
        # standard file): presence and text both ride the RunFacts snapshot.
        # Re-statting here would let one snapshot's verdict flip when the file
        # is created or deleted after capture (ADR-0039).
        report_present = (
            facts.artifact_state("decision_report") != STATE_MISSING
        )
        report_text = facts.decision_report_text
    else:
        # Explicit path may point outside the captured run root (same
        # justification as the explicit --shaping-dir re-read above); it has
        # no snapshot fact, so presence and text come from this read.
        try:
            report_text = dr.read_text(encoding="utf-8") if dr.is_file() else ""
        except (OSError, UnicodeError):
            report_text = ""
        report_present = bool(report_text) or dr.is_file()
    if report_present:
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

    # Baseline acceptance (T-158): only the complete profile consumes a
    # present baseline, and only from the immutable capture in RunFacts.
    # run() never calls the baseline owner or reopens state/DESIGN/sources;
    # an uncaptured or identity-mismatched result blocks instead of passing.
    if require_baseline_verification:
        baseline_errs, baseline_warns = _baseline_acceptance_findings(
            inputs, facts)
        errs += baseline_errs
        warns += baseline_warns

    # G13 (conditional, T-153): a contract on disk is checked for its
    # declared axes. The run-level discovery is <run-root>/reference/
    # contract.md; a run with no reference material reports nothing, and an
    # unreadable contract is a finding rather than an operational exit.
    if facts.reference_contract_text is not None:
        errs += check_g13(facts.reference_contract_text)
    elif facts.reference_contract_error is not None:
        errs.append(contract_unreadable_finding())

    # G8 run level (vNext S3): a craft-guard.md in the run root is checked
    # against the registry (shared parser). P2/P3 demand one audit row per
    # advisory entry; P1 and tier-less legacy runs keep the subset freedom.
    if facts.craft_guard_exists:
        try:
            craft_text = facts.craft_guard_text
            registry_entries, _ = load_registry()
        except (OSError, UnicodeError, RegistryLayoutError) as exc:
            errs.append(finding(
                "G8.run_registry",
                "G8 run: craft-guard.md present but the audit log or the "
                "registry could not be read",
                owner="craft-guard.md",
                expected="readable craft-guard.md and rules.md",
                actual=(str(exc) if isinstance(exc, RegistryLayoutError)
                        else "read error"),
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
        epilog=(
            "A single --require-* flag engages only its own check: "
            "--require-coverage alone does not turn on preview, evidence, "
            "run-profile, baseline, or repair proof. --legacy cannot be "
            "combined with --strict or any --require-*."
        ),
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
             "--require-coverage; kept for compatibility (the bare CLI "
             "default is already strict)",
    )
    parser.add_argument(
        "--require-coverage",
        action="store_true",
        help="strict mode: fail when the point-back lacks a Coverage "
             "statement block (G11 must fire)",
    )
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="opt out of the default strict mode for old reports: leaves "
             "--require-preview, --require-evidence, and --require-coverage "
             "disengaged and does not require the run-profile for this "
             "invocation (a malformed profile is still rejected); cannot be "
             "combined with --strict or any --require-* flag",
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
        help="optional project dir containing contract.json for G7; also the "
             "explicit project authorization for complete-acceptance baseline "
             "verification",
    )
    parser.add_argument(
        "--contract-run",
        default=None,
        help="optional run dir containing contract-bind.json for G7; when "
             "complete acceptance verifies a baseline it must agree with "
             "--run-root (or the explicit point-back parent)",
    )
    parser.add_argument(
        "--shaping-dir",
        default=None,
        help="optional path to .scratch/<run>/shaping/ for G9 "
             "(defaults to <run-root>/shaping when --run-root is set)",
    )
    args = parser.parse_args(argv[1:])
    # Taken before --strict expands below, so an explicit trio is not --strict.
    # The complete profile is one selection: bare CLI or --strict. Selective
    # --require-* invocations and --legacy keep their existing narrower scope
    # and never inherit complete-acceptance baseline verification.
    complete_profile = not args.legacy and (
        args.strict
        or not (
            args.require_preview
            or args.require_evidence
            or args.require_coverage
        )
    )
    args.require_run_profile = complete_profile
    args.require_baseline_verification = complete_profile
    args.require_repair_evidence = complete_profile
    if args.strict:
        # --strict keeps its historical shorthand meaning.
        args.require_preview = True
        args.require_evidence = True
        args.require_coverage = True
    strictness_flags = (
        ("--strict", args.strict),
        ("--require-preview", args.require_preview),
        ("--require-evidence", args.require_evidence),
        ("--require-coverage", args.require_coverage),
    )
    if args.legacy:
        engaged = [flag for flag, on in strictness_flags if on]
        if engaged:
            parser.error(
                f"--legacy cannot be combined with {' / '.join(engaged)}; "
                "drop --legacy for the default strict mode, or drop the "
                "strictness flag to keep the explicit legacy opt-out"
            )
        # Explicit opt-out: every require flag stays off (argparse default).
        return args
    if not any(on for _flag, on in strictness_flags):
        # Fail closed by default: a bare CLI invocation behaves as --strict.
        # An explicit --require-* keeps its own historical meaning (only that
        # flag engages), and --legacy above is the only way to opt out.
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
        rr = Path(args.run_root) if args.run_root else None
        plan_path = (
            rr / "plan.md" if rr is not None
            else Path(args.point_back).parent / "plan.md"
        )
        # Complete acceptance captures a present baseline once, with the
        # explicit project authorization. Without --contract-project no
        # project content is read; the state file at this run authority is
        # still probed for presence so a present baseline cannot disappear.
        # The run is --run-root or the explicit point-back parent, never a
        # search; --contract-run is compared in run().
        baseline_run = (
            rr if rr is not None else Path(args.point_back).parent)
        baseline_capture = None
        if args.require_baseline_verification and args.contract_project:
            baseline_capture = BaselineCapture(
                project_root=Path(args.contract_project),
                run_root=baseline_run,
            )
        facts = capture_run_facts(
            spec_path=Path(args.spec),
            pointback_path=Path(args.point_back),
            preview_dir=Path(args.preview_dir) if args.preview_dir else None,
            evidence_dir=Path(args.evidence_dir) if args.evidence_dir else None,
            run_root=rr,
            plan_path=plan_path,
            baseline_capture=baseline_capture,
            baseline_run_root=(
                baseline_run if args.require_baseline_verification else None
            ),
        )
        errs, warns = run(RunInputs(
            spec_path=args.spec,
            point_back_path=args.point_back,
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
            run_facts=facts,
            require_run_profile=args.require_run_profile,
            require_baseline_verification=args.require_baseline_verification,
            require_repair_evidence=args.require_repair_evidence,
        ))
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
        if errs:
            print(
            "NOTE: gates can run left-shifted at authoring time — each "
            "skill's Done-when names the single-gate script to run right "
            "after writing its artifact (g1_spec / g9_shaping / "
            "g10_design_decisions / g5_preview / g6_evidence / "
            "g8_run_registry / g2_g4_pointback). This end-of-run sweep "
            "should find zero."
        )
    return 1 if errs else 0


if __name__ == "__main__":
    for _candidate in Path(__file__).resolve().parents:
        if (_candidate / "design_playbook.py").is_file():
            sys.path.insert(0, str(_candidate))
            break
    from design_playbook.scripts.stdio_encoding import configure_piped_utf8

    configure_piped_utf8()
    sys.exit(main(sys.argv))
