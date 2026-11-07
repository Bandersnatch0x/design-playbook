"""G6 evidence-binding gate (ADR-0023, ADR-0025, ADR-0026, T-159).

Conditional: if a ledger ``observed`` references an ``evidence/`` artifact,
require the artifact to exist and a manifest entry to bind it to the
matching L6.<n> (multi-entry: latest by ts wins). The soft manifest-ts and
superseded-artifact warnings live in ``g6_warnings.py``. Bound manifest
request snapshots validate through the bundled Evidence runtime's
``validate_capture_snapshot`` (ADR-0018 enforcement site 3).

Ledger rows are no longer parsed here (ADR-0025): the ``(criterion, observed)``
pairs come from ``g6_records.ledger_observed``, the G6 projection over the
single Evidence ledger syntax-facts module (``mcp.evidence.ledger_syntax``).
Artifact path containment is no longer enforced here (ADR-0026): it is
delegated to ``mcp.evidence.containment.read_artifact``, whose stable reason
codes this module maps to G6.escape and G6.artifact_missing.

T-159 splits the gate into one pure verification owner and one explicit I/O
seam:

* ``validate_references`` accepts already-captured artifact facts and returns
  one typed binding result per ``(criterion, token)`` reference. It never
  opens a file: a snapshot without a required fact fails as unavailable
  instead of falling back to disk.
* ``check_evidence`` keeps its historical CLI/legacy call shape: it collects
  the facts for its own observed rows once, then delegates to the pure owner.
  Observed, repair-before, and repair-after references therefore share one
  binding, capture-contract, proof-type, and declared-hash rule.
"""
from __future__ import annotations

import argparse
import dataclasses
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# One import seam (ADR-0022): package root on sys.path once, then absolute
# design_playbook.* imports below. No per-runtime sys.path adapters.
_PKG_ROOT = Path(__file__).resolve().parent.parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.scripts._diagnostics import Finding, finding  # noqa: E402
from design_playbook.scripts.g6_records import (  # noqa: E402
    REASON_UNREADABLE,
    EvidenceArtifactFact,
    binding_instant,
    collect_evidence_artifacts,
    latest_by_instant,
    ledger_observed,
    manifest_entries,
    normalise_evidence_reference,
)
from design_playbook.scripts.run_facts import ArtifactReadFact  # noqa: E402
from design_playbook.scripts.stages import EVIDENCE_PREFIX  # noqa: E402
from design_playbook.mcp.evidence.capture_contract import validate_capture_snapshot  # noqa: E402
from design_playbook.mcp.evidence import containment  # noqa: E402

# The manifest capture vocabulary the declared proof types select. One map,
# shared by G6 and the frontend review projection: a second copy is the exact
# drift this owner exists to prevent.
PROOF_CAPTURE_TYPES = {
    "screenshot": "screenshot",
    "a11y_tree": "a11y tree",
    "interaction_trace": "interaction trace",
}
_CANONICAL_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def manifest_read_findings(
        errors: tuple[ArtifactReadFact, ...]) -> list[Finding]:
    """Project manifest read facts into stable G6 diagnostics."""
    findings: list[Finding] = []
    rule_ids = {
        "malformed_json": "G6.manifest_json",
        "invalid_entry": "G6.manifest_entry",
        "unreadable": "G6.manifest_unreadable",
    }
    expectations = {
        "malformed_json": "one valid JSON object per non-empty line",
        "invalid_entry": "one JSON object per non-empty line",
        "unreadable": "UTF-8 readable manifest.jsonl",
    }
    for error in errors:
        if error.artifact != "manifest":
            continue
        rule_id = rule_ids.get(error.code, "G6.manifest_read")
        findings.append(finding(
            rule_id,
            f"G6 evidence: {error.message}",
            owner="evidence/manifest.jsonl",
            expected=expectations.get(error.code, "readable manifest entries"),
            actual=error.message,
            repair=(
                "Rewrite the named manifest line as one valid JSON object"
                if error.line_number is not None
                else "Restore evidence/manifest.jsonl as UTF-8 JSON Lines"
            ),
        ))
    return findings


def _capture_fact_diagnostic(snapshot: object) -> "ReferenceDiagnostic | None":
    """Map one capture-contract fact to the binding's stable diagnostic.

    ADR-0018 enforcement site 3 keeps its historical first-failure shape:
    the bound entry's request snapshot is validated through
    ``validate_capture_snapshot`` and the first failing fact wins.
    """
    for fact in validate_capture_snapshot(snapshot):
        if fact.code in ("missing_schema_version", "unsupported_schema_version"):
            return ReferenceDiagnostic(
                "capture_schema",
                f"missing schemaVersion=1 (got {fact.actual})")
        if fact.code == "missing_viewport":
            return ReferenceDiagnostic("capture_viewport", "missing")
        if fact.code == "bad_viewport_shape":
            return ReferenceDiagnostic("capture_viewport_shape", fact.detail)
        if fact.code == "missing_freeze":
            return ReferenceDiagnostic("capture_freeze", "missing")
        if fact.code == "bad_freeze_shape":
            return ReferenceDiagnostic("capture_freeze", fact.detail)
        if fact.code == "bad_design_shape":
            return ReferenceDiagnostic("capture_design_shape", fact.detail)
        # Every capture-contract fact is a failure. A code this mapping has
        # not learned yet must keep its own identity and block, never fall
        # through as a valid snapshot.
        return ReferenceDiagnostic(
            "capture_contract", f"{fact.code}: {fact.detail}")
    return None


@dataclass(frozen=True)
class EvidenceReference:
    """One artifact reference to verify through the shared G6 path.

    ``role`` names the reference's position (``observed``, ``before``,
    ``after``, or a finding-evidence role) for diagnostics only. ``proof`` is
    the exact G1 proof token when the reference must evidence a declared
    requirement; nonvisual roles pass ``None``. ``require_hash`` marks the
    references whose bytes must carry a declared, matching digest (repair
    pairs that complete acceptance requires).
    """

    criterion: str
    token: str
    role: str = "observed"
    proof: str | None = None
    require_hash: bool = False


@dataclass(frozen=True)
class ReferenceDiagnostic:
    """One stable binding or integrity failure with bounded detail."""

    code: str
    detail: str = ""


@dataclass(frozen=True)
class ReferenceBinding:
    """The verified (or failed) binding for one reference.

    ``entry`` is the selected manifest entry when binding reached that stage;
    ``viewport`` and ``capture_type`` are its provider snapshot values, so
    callers compare values without re-parsing the manifest entry. ``sha256``
    and ``size`` are the captured bytes facts; ``None`` means the artifact
    was not readable or facts were not captured.
    """

    reference: EvidenceReference
    canonical: str
    entry: dict | None = None
    diagnostics: tuple[ReferenceDiagnostic, ...] = ()
    sha256: str | None = None
    size: int | None = None
    viewport: object | None = None
    capture_type: str | None = None
    capture_state: object | None = None
    capture_artifact_path: object | None = None

    @property
    def ok(self) -> bool:
        return not self.diagnostics


def select_bound_entry(entries: list[dict], criterion: str, artifact: str) -> dict | None:
    """The latest binding for one criterion/artifact; ambiguous heads fail closed.

    ``ts`` decides the winner as a real instant, not as a string: ``Z`` and
    ``+08:00`` stamps of one manifest must order by capture time (P2-3).
    Malformed, offset-less or missing stamps name no instant and fail closed;
    two distinct entries sharing the latest instant stay ambiguous.
    """
    bound = [entry for entry in entries
             if entry.get("criterion") == criterion and entry.get("artifact") == artifact]
    if not bound:
        return None
    latest = latest_by_instant(bound)
    if latest is None:
        raise ValueError("invalid-binding-timestamp")
    latest_instant = binding_instant(latest.get("ts"))
    if any(binding_instant(entry.get("ts")) == latest_instant and entry != latest
           for entry in bound):
        raise ValueError("conflicting-bindings")
    return latest


def bound_capture_request(entry: dict) -> dict:
    """Read the provider snapshot with the same precedence as G6."""
    request = entry.get("request")
    if isinstance(request, dict):
        return request
    capture = entry.get("capture")
    if isinstance(capture, dict) and isinstance(capture.get("request"), dict):
        return capture["request"]
    return {}


def _capture_metadata(entry: dict) -> tuple[object, object, object, object]:
    """(capture dict, type, state, primary artifact path) from one entry."""
    capture = entry.get("capture")
    if not isinstance(capture, dict):
        return None, None, None, None
    return (capture, capture.get("type"), capture.get("state"),
            capture.get("artifact_path"))


def _artifact_diagnostic(fact: EvidenceArtifactFact) -> ReferenceDiagnostic:
    if fact.reason == containment.REASON_NOT_REGULAR_FILE:
        return ReferenceDiagnostic("artifact_missing", "missing")
    if fact.reason == REASON_UNREADABLE:
        return ReferenceDiagnostic("artifact_unreadable", fact.detail)
    return ReferenceDiagnostic("escape", fact.reason or fact.detail)


def _validate_reference(
    reference: EvidenceReference,
    entries: list[dict],
    valid_criteria: set[str],
    facts: dict[str, EvidenceArtifactFact] | None,
) -> ReferenceBinding:
    """Verify one reference against frozen facts and manifest entries."""
    canonical, leaf = normalise_evidence_reference(reference.token)
    if leaf is None:
        # Repair-local leaf-only references and absolute paths used to bypass
        # the evidence/ normalization entirely. They now fail with one named
        # migration code instead of resolving against the manifest leaf.
        return ReferenceBinding(
            reference, canonical,
            diagnostics=(ReferenceDiagnostic(
                "reference_prefix",
                f"expected evidence/<artifact>, got {reference.token}"),))

    if facts is None:
        return ReferenceBinding(
            reference, canonical,
            diagnostics=(ReferenceDiagnostic(
                "artifact_facts_unavailable",
                "the snapshot did not capture referenced artifact facts"),))
    fact = facts.get(canonical)
    if fact is None:
        return ReferenceBinding(
            reference, canonical,
            diagnostics=(ReferenceDiagnostic(
                "artifact_facts_unavailable",
                f"no captured fact for {canonical}"),))
    if not fact.ok:
        return ReferenceBinding(
            reference, canonical, sha256=fact.sha256, size=fact.size,
            diagnostics=(_artifact_diagnostic(fact),))

    bound = [
        entry for entry in entries
        if entry.get("criterion") == reference.criterion
        and isinstance(entry.get("artifact"), str)
        and entry["artifact"] == leaf
    ]
    if not bound:
        unknown = [
            entry for entry in entries
            if isinstance(entry.get("criterion"), str)
            and entry["criterion"] not in valid_criteria
            and isinstance(entry.get("artifact"), str)
            and entry["artifact"] == leaf
        ]
        if unknown:
            criterion = unknown[0].get("criterion")
            return ReferenceBinding(
                reference, canonical, sha256=fact.sha256, size=fact.size,
                diagnostics=(ReferenceDiagnostic(
                    "unknown_criterion",
                    f"manifest binds unknown criterion {criterion}"),))
        return ReferenceBinding(
            reference, canonical, sha256=fact.sha256, size=fact.size,
            diagnostics=(ReferenceDiagnostic(
                "no_binding",
                f"no manifest entry binds {reference.criterion} -> {leaf}"),))
    try:
        entry = select_bound_entry(bound, reference.criterion, leaf)
    except ValueError as conflict:
        return ReferenceBinding(
            reference, canonical, sha256=fact.sha256, size=fact.size,
            diagnostics=(ReferenceDiagnostic("binding_conflict", str(conflict)),))
    assert entry is not None
    if entry.get("criterion") not in valid_criteria:
        return ReferenceBinding(
            reference, canonical, entry=entry,
            sha256=fact.sha256, size=fact.size,
            diagnostics=(ReferenceDiagnostic(
                "unknown_criterion",
                f"manifest binds unknown criterion {entry.get('criterion')}"),))

    request = bound_capture_request(entry)
    _, capture_type, capture_state, artifact_path = _capture_metadata(entry)
    binding = ReferenceBinding(
        reference, canonical, entry=entry, sha256=fact.sha256, size=fact.size,
        viewport=request.get("viewport"),
        capture_type=capture_type if isinstance(capture_type, str) else None,
        capture_state=capture_state,
        capture_artifact_path=artifact_path,
    )

    def failure(diagnostic: ReferenceDiagnostic) -> ReferenceBinding:
        return dataclasses.replace(binding, diagnostics=(diagnostic,))

    capture_diagnostic = _capture_fact_diagnostic(request)
    if capture_diagnostic is not None:
        return failure(capture_diagnostic)

    if reference.proof in PROOF_CAPTURE_TYPES:
        expected = PROOF_CAPTURE_TYPES[reference.proof]
        if capture_type != expected:
            return failure(ReferenceDiagnostic(
                "proof_type",
                f"expected capture.type {expected!r}, got {capture_type!r}"))

    declared = entry.get("sha256")
    if declared is None:
        if reference.require_hash:
            return failure(ReferenceDiagnostic(
                "artifact_hash_unavailable",
                "the bound manifest entry declares no sha256"))
    elif not isinstance(declared, str) or not _CANONICAL_DIGEST.fullmatch(declared):
        return failure(ReferenceDiagnostic(
            "artifact_hash_malformed",
            "declared sha256 is not 64 lowercase hex characters"))
    elif fact.sha256 != declared:
        return failure(ReferenceDiagnostic(
            "artifact_hash_mismatch",
            f"declared {declared}, captured bytes {fact.sha256}"))
    return binding


def validate_references(
    references,
    entries: list[dict],
    valid_criteria,
    artifact_facts: tuple[EvidenceArtifactFact, ...] | None,
) -> tuple[ReferenceBinding, ...]:
    """Verify references against frozen artifact facts; never touches disk.

    ``artifact_facts`` is the explicit capture result: ``None`` means the
    snapshot did not collect facts (every reference is unavailable), an empty
    tuple means collection ran and saw no references. A reference whose
    canonical token has no fact is likewise unavailable - this function never
    falls back to ``containment.read_artifact``. ``valid_criteria`` is the
    current G1 criterion set; membership is checked against the manifest and
    the ledger binding.
    """
    criteria = {str(item) for item in valid_criteria}
    facts: dict[str, EvidenceArtifactFact] | None
    if artifact_facts is None:
        facts = None
    else:
        facts = {fact.reference: fact for fact in artifact_facts}
    return tuple(
        _validate_reference(reference, entries, criteria, facts)
        for reference in references)


def _reference_label(reference: EvidenceReference) -> str:
    return (reference.token if reference.role == "observed"
            else f"{reference.role} {reference.token}")


def reference_finding(
    binding: ReferenceBinding, diagnostic: ReferenceDiagnostic,
    *, expected_l6: int | None = None,
) -> Finding:
    """Project one binding diagnostic into the historical G6 rule surface.

    Rule IDs and wording for the pre-T-159 codes stay exactly as they were;
    the new codes name the frozen-fact, prefix, proof-type, and hash gaps.
    """
    reference = binding.reference
    criterion = reference.criterion
    label = _reference_label(reference)
    token = reference.token
    code = diagnostic.code
    detail = diagnostic.detail
    criterion_range = (
        f"criterion in L6.1..L6.{expected_l6}" if expected_l6 is not None
        else "a declared L6 criterion")
    if code == "artifact_missing":
        return finding(
            "G6.artifact_missing",
            f"G6 evidence: {criterion} {label} artifact missing: {token}",
            owner=f"evidence/{binding.canonical[len(EVIDENCE_PREFIX):]}",
            expected="artifact file on disk",
            actual="missing",
            repair=f"Capture or restore {token}",
        )
    if code == "escape":
        return finding(
            "G6.escape",
            f"G6 evidence: {criterion} {label} escapes evidence/ subtree: {token}",
            owner=f"point-back.md#{criterion}",
            expected="path inside evidence/",
            actual=f"{token} ({detail})" if detail else token,
            repair="Point the reference at an artifact under evidence/",
        )
    if code == "artifact_unreadable":
        return finding(
            "G6.artifact_unreadable",
            f"G6 evidence: {criterion} {label} could not be read: {token}",
            owner=f"evidence/{binding.canonical[len(EVIDENCE_PREFIX):]}",
            expected="readable artifact bytes",
            actual=detail or "read error",
            repair="Restore a readable artifact and recapture",
        )
    if code == "artifact_facts_unavailable":
        return finding(
            "G6.artifact_facts_unavailable",
            f"G6 evidence: {criterion} cannot verify {label}: no captured "
            "artifact facts in this snapshot",
            owner="validate_run.py",
            expected="artifact bytes frozen during the explicit capture",
            actual=detail or "artifact facts not captured",
            repair="Recapture the run snapshot with evidence collection so "
                   "the reference can be verified; a supplied snapshot is "
                   "never re-read",
        )
    if code == "reference_prefix":
        return finding(
            "G6.reference_prefix",
            f"G6 evidence: {criterion} reference is not evidence-relative: "
            f"{token}",
            owner=f"point-back.md#{criterion}",
            expected="evidence/<artifact>",
            actual=detail or token,
            repair="Write the reference as evidence/<artifact>; manifest "
                   "leaves and absolute paths are not binding tokens",
        )
    if code == "unknown_criterion":
        return finding(
            "G6.unknown_criterion",
            f"G6 evidence: {detail}",
            owner="evidence/manifest.jsonl",
            expected=criterion_range,
            actual=str(criterion),
            repair="Bind the artifact to a declared L6 criterion",
        )
    if code == "no_binding":
        return finding(
            "G6.no_binding",
            f"G6 evidence: {criterion} no manifest entry binding {token}",
            owner="evidence/manifest.jsonl",
            expected=f"manifest entry for {criterion} -> "
                     f"{binding.canonical[len(EVIDENCE_PREFIX):]}",
            actual="no binding",
            repair="Append a manifest line binding criterion and artifact",
        )
    if code == "binding_conflict":
        return finding(
            "G6.binding_conflict",
            "G6 evidence: binding timestamps are malformed or the latest "
            "entries conflict",
            owner="evidence/manifest.jsonl",
            expected="one unambiguous latest binding with an offset-aware "
                     "ISO-8601 ts",
            actual=detail or "conflict",
            repair="Give every binding an offset-aware ISO-8601 ts and "
                   "resolve conflicting bindings before re-evaluation",
        )
    if code == "capture_schema":
        return finding(
            "G6.capture_schema",
            f"G6 evidence: {criterion} capture missing schemaVersion=1 "
            f"({detail}); recapture with capture contract v1",
            owner="evidence/manifest.jsonl",
            expected="schemaVersion=1 with viewport on the bound entry",
            actual=detail,
            repair="Recapture the artifact with execute_capture_plan schemaVersion=1",
        )
    if code == "capture_viewport":
        return finding(
            "G6.capture_viewport",
            f"G6 evidence: {criterion} capture missing viewport snapshot; "
            "recapture with capture contract v1",
            owner="evidence/manifest.jsonl",
            expected="viewport width/height/devicePixelRatio/colorScheme",
            actual="missing",
            repair="Recapture and embed the provider request snapshot",
        )
    if code == "capture_viewport_shape":
        return finding(
            "G6.capture_viewport_shape",
            f"G6 evidence: {criterion} capture viewport snapshot malformed: "
            f"{detail}; recapture with capture contract v1",
            owner="evidence/manifest.jsonl",
            expected="viewport width/height/devicePixelRatio/colorScheme",
            actual=detail,
            repair="Recapture and embed the provider request snapshot",
        )
    if code == "capture_freeze":
        return finding(
            "G6.capture_freeze",
            f"G6 evidence: {criterion} capture freeze snapshot "
            f"{'missing' if detail == 'missing' else 'malformed'}: "
            f"{detail}; recapture with capture contract v1",
            owner="evidence/manifest.jsonl",
            expected="freeze enabled/waitFonts/networkIdle booleans",
            actual=detail,
            repair="Recapture and embed the provider request snapshot",
        )
    if code == "capture_design_shape":
        return finding(
            "G6.capture_design_shape",
            f"G6 evidence: {criterion} capture design binding malformed: "
            f"{detail}; recapture with capture contract v1",
            owner="evidence/manifest.jsonl",
            expected="design object with declared axes as literal lists",
            actual=detail,
            repair="Recapture and embed the provider request snapshot",
        )
    if code == "capture_contract":
        return finding(
            "G6.capture_contract",
            f"G6 evidence: {criterion} capture contract failure: {detail}",
            owner="evidence/manifest.jsonl",
            expected="a valid capture contract v1 snapshot",
            actual=detail,
            repair="Recapture through the provider contract",
        )
    if code == "proof_type":
        return finding(
            "G6.proof_type",
            f"G6 evidence: {criterion} {label} does not match the declared "
            f"proof type: {detail}",
            owner="evidence/manifest.jsonl",
            expected=f"capture.type matching declared {reference.proof}",
            actual=detail,
            repair="Recapture with the declared capture type or correct the "
                   "criterion's Required evidence seed",
        )
    if code == "artifact_hash_unavailable":
        return finding(
            "G6.artifact_hash_unavailable",
            f"G6 evidence: {criterion} {label} has no declared sha256 for a "
            "required repair pair",
            owner="evidence/manifest.jsonl",
            expected="a declared 64-character lowercase sha256 on the bound entry",
            actual="no declared sha256",
            repair="Recapture through the manifest writer, which records the "
                   "captured bytes' digest",
        )
    if code == "artifact_hash_malformed":
        return finding(
            "G6.artifact_hash_malformed",
            f"G6 evidence: {criterion} {label} declares a malformed sha256",
            owner="evidence/manifest.jsonl",
            expected="64 lowercase hexadecimal characters",
            actual=detail,
            repair="Record the real digest of the captured bytes",
        )
    if code == "artifact_hash_mismatch":
        return finding(
            "G6.artifact_hash_mismatch",
            f"G6 evidence: {criterion} {label} declared sha256 does not match "
            f"the captured bytes ({detail})",
            owner="evidence/manifest.jsonl",
            expected="declared sha256 equal to the captured file's digest",
            actual=detail,
            repair="Recapture or restore the artifact; a declared digest must "
                   "match the bytes",
        )
    raise AssertionError(f"unknown reference diagnostic: {code}")


def check_evidence(
        pointback_text: str,
        expected_l6: int,
        evidence_dir: Path | None,
        run_root: Path | None,
        *,
        observed_rows: list[tuple[str, str]] | None = None,
        entries: list[dict] | None = None,
        artifact_facts: tuple[EvidenceArtifactFact, ...] | None = None) -> list[Finding]:
    """G6 conditional evidence-binding gate (explicit I/O seam).

    Triggers only when a ledger ``observed`` references an ``evidence/``
    artifact. For each such row, the artifact must exist and a manifest entry
    must bind it to the matching L6.<n> (multi-entry: latest by ts wins).
    Weak/conditional: rows with free-text observed are not checked; pass rows
    are not required to reference evidence.

    ``artifact_facts`` is optional: when omitted this I/O seam probes the
    evidence directory and collects the facts for its own observed references
    once, then delegates to the pure ``validate_references``. A caller holding
    a snapshot passes its frozen tuple (including an empty one) so the
    projection performs no directory check and never re-reads disk.
    """
    if artifact_facts is None:
        if evidence_dir is None or not evidence_dir.is_dir():
            return []
    root = (run_root if run_root is not None
            else (evidence_dir.parent if evidence_dir is not None else None))
    entries = entries if entries is not None else manifest_entries(evidence_dir)
    valid_criteria = {f"L6.{n}" for n in range(1, expected_l6 + 1)}
    rows = observed_rows if observed_rows is not None else ledger_observed(pointback_text)
    references = [
        EvidenceReference(criterion, observed, role="observed")
        for criterion, observed in rows
        # Case-insensitive prefix. The write boundary treats paths
        # case-insensitively on case-insensitive filesystems (Windows), so
        # ``EVIDENCE/<x>`` lands in the evidence/ subtree on disk; the read
        # side must match the same way or uppercase rows skip G6 entirely.
        if observed.casefold().startswith(EVIDENCE_PREFIX)
    ]
    if not references:
        return []
    facts = artifact_facts
    if facts is None:
        facts = collect_evidence_artifacts(
            [reference.token for reference in references], run_root=root)
    errs: list[Finding] = []
    for binding in validate_references(references, entries, valid_criteria, facts):
        if binding.diagnostics:
            errs.append(reference_finding(
                binding, binding.diagnostics[0], expected_l6=expected_l6))
    return errs


def main(argv: list[str]) -> int:
    """Single-gate CLI (left-shifted validation, spec 2026-09-22 D3)."""
    from design_playbook.scripts.g1_spec import _l6_items

    parser = argparse.ArgumentParser(
        prog="g6_evidence.py",
        description="G6 evidence-binding gate: every point-back ledger "
                    "`observed: evidence/…` row has the artifact on disk and "
                    "a manifest.jsonl line binding it to the same L6.<n>; a "
                    "declared sha256 must match the captured bytes. Repair "
                    "pairs, proof-type obligations, and complete-acceptance "
                    "derivation belong to validate_run.py.",
    )
    parser.add_argument(
        "point_back",
        help="path to the run's point-back.md "
             "(`.scratch/<run>/point-back.md`)",
    )
    parser.add_argument(
        "--spec",
        default=None,
        help="path to spec.md for the expected L6 count "
             "(default: sibling of point-back.md)",
    )
    parser.add_argument(
        "--evidence-dir",
        default=None,
        help="path to the run's evidence/ directory "
             "(default: sibling of point-back.md)",
    )
    args = parser.parse_args(argv[1:])
    point_back = Path(args.point_back)
    if not point_back.is_file():
        print(
            f"G6 INVALID: {point_back} is not a file — pass the run's "
            f"point-back.md (`.scratch/<run>/point-back.md`)",
            file=sys.stderr,
        )
        return 2
    spec = Path(args.spec) if args.spec else point_back.parent / "spec.md"
    if not spec.is_file():
        print(
            f"G6 INVALID: {spec} not found — G6 needs the spec to size "
            f"L6.<n>; pass --spec <path to spec.md>",
            file=sys.stderr,
        )
        return 2
    evidence_dir = (
        Path(args.evidence_dir)
        if args.evidence_dir
        else point_back.parent / "evidence"
    )
    findings = check_evidence(
        point_back.read_text(encoding="utf-8"),
        len(_l6_items(spec.read_text(encoding="utf-8"))),
        evidence_dir if evidence_dir.is_dir() else None,
        evidence_dir.parent,
    )
    if not findings:
        print("G6 OK: evidence bindings satisfy the gate")
        return 0
    print("G6 INVALID:")
    for item in findings:
        print(f"  FAIL  {item.message}")
    return 1


if __name__ == "__main__":
    for _candidate in Path(__file__).resolve().parents:
        if (_candidate / "design_playbook.py").is_file():
            sys.path.insert(0, str(_candidate))
            break
    from design_playbook.scripts.stdio_encoding import configure_piped_utf8

    configure_piped_utf8()
    sys.exit(main(sys.argv))