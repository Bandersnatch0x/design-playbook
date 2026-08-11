"""G6 evidence-binding gate (ADR-0023).

Conditional: if a ledger ``observed`` references an ``evidence/`` artifact,
require the artifact to exist and a manifest entry to bind it to the
matching L6.<n> (multi-entry: latest by ts wins). The soft manifest-ts and
superseded-artifact warnings live in ``g6_warnings.py``. Bound manifest
request snapshots validate through the bundled Evidence runtime's
``validate_capture_snapshot`` (ADR-0018 enforcement site 3).
"""
from __future__ import annotations

import os
from pathlib import Path

from design_playbook.scripts._diagnostics import Finding, finding
from design_playbook.scripts.g6_records import ledger_observed, manifest_entries
from design_playbook.scripts.stages import EVIDENCE_PREFIX
from design_playbook.mcp.evidence.capture_contract import validate_capture_snapshot


def _g6_capture_findings(criterion: str, snapshot: object) -> list[Finding]:
    """Project capture-contract snapshot facts into G6 diagnostics.

    ADR-0018 enforcement site 3: the bound entry's request snapshot is
    validated through validate_capture_snapshot (full shape, fail-closed on
    malformed viewport or missing freeze). Existing rule IDs and wording are
    preserved for the schema/version and viewport-present checks; malformed
    viewport shape and missing/malformed freeze surface as new rule IDs.
    """
    for fact in validate_capture_snapshot(snapshot):
        if fact.code in ("missing_schema_version", "unsupported_schema_version"):
            return [finding(
                "G6.capture_schema",
                f"G6 evidence: {criterion} capture missing schemaVersion=1 "
                f"(got {fact.actual}); recapture with capture contract v1",
                owner="evidence/manifest.jsonl",
                expected="schemaVersion=1 with viewport on the bound entry",
                actual=fact.actual,
                repair="Recapture the artifact with execute_capture_plan schemaVersion=1",
            )]
        if fact.code == "missing_viewport":
            return [finding(
                "G6.capture_viewport",
                f"G6 evidence: {criterion} capture missing viewport snapshot; "
                "recapture with capture contract v1",
                owner="evidence/manifest.jsonl",
                expected="viewport width/height/devicePixelRatio/colorScheme",
                actual="missing",
                repair="Recapture and embed the provider request snapshot",
            )]
        if fact.code == "bad_viewport_shape":
            return [finding(
                "G6.capture_viewport_shape",
                f"G6 evidence: {criterion} capture viewport snapshot malformed: "
                f"{fact.detail}; recapture with capture contract v1",
                owner="evidence/manifest.jsonl",
                expected="viewport width/height/devicePixelRatio/colorScheme",
                actual=fact.detail,
                repair="Recapture and embed the provider request snapshot",
            )]
        if fact.code in ("missing_freeze", "bad_freeze_shape"):
            return [finding(
                "G6.capture_freeze",
                f"G6 evidence: {criterion} capture freeze snapshot "
                f"{'missing' if fact.code == 'missing_freeze' else 'malformed'}: "
                f"{fact.detail}; recapture with capture contract v1",
                owner="evidence/manifest.jsonl",
                expected="freeze enabled/waitFonts/networkIdle booleans",
                actual=fact.detail,
                repair="Recapture and embed the provider request snapshot",
            )]
    return []


def check_evidence(
        pointback_text: str,
        expected_l6: int,
        evidence_dir: Path | None,
        run_root: Path | None) -> list[Finding]:
    """G6 conditional evidence-binding gate.

    Triggers only when a ledger ``observed`` references an ``evidence/``
    artifact. For each such row, the artifact must exist and a manifest entry
    must bind it to the matching L6.<n> (multi-entry: latest by ts wins).
    Weak/conditional: rows with free-text observed are not checked; pass rows
    are not required to reference evidence.
    """
    if evidence_dir is None or not evidence_dir.is_dir():
        return []
    root = run_root if run_root is not None else evidence_dir.parent
    entries = manifest_entries(evidence_dir)
    valid_criterion_ids = {f"L6.{n}" for n in range(1, expected_l6 + 1)}
    evidence_root = (root / "evidence").resolve()

    errs: list[Finding] = []
    for criterion, observed in ledger_observed(pointback_text):
        # LOW-3: case-insensitive prefix. The write boundary treats paths
        # case-insensitively on case-insensitive filesystems (Windows), so
        # ``EVIDENCE/<x>`` lands in the evidence/ subtree on disk; the read
        # side must match the same way or uppercase rows skip G6 entirely.
        # After the casefold match, rewrite the leading segment to the
        # canonical ``evidence/`` so path resolution stays under that subtree
        # on case-*sensitive* filesystems (Linux CI) too — otherwise
        # ``root / "EVIDENCE/…"`` resolves as a sibling of ``evidence/`` and
        # the containment check spuriously reports "escapes" instead of the
        # intended missing/bound diagnostic.
        if not observed.casefold().startswith(EVIDENCE_PREFIX):
            continue  # free-text observation; G6 does not apply
        leaf = observed[len(EVIDENCE_PREFIX):]
        canonical = EVIDENCE_PREFIX + leaf
        # Containment (issue 04 / G6): the observed path must resolve *inside*
        # the evidence/ subtree. Reject any ".." segment, absolute paths, and
        # post-resolve escapes (e.g. ``evidence/../spec.md`` -> run root,
        # which under the new Codex manifest could overwrite spec / source).
        observed_path = Path(canonical)
        if observed_path.is_absolute() or ".." in observed_path.parts:
            errs.append(finding(
                "G6.escape",
                f"G6 evidence: {criterion} observed escapes evidence/ "
                f"subtree: {observed}",
                owner=f"point-back.md#{criterion}",
                expected="observed path inside evidence/",
                actual=observed,
                repair="Point observed at an artifact under evidence/",
            ))
            continue
        try:
            resolved = (root / canonical).resolve()
        except OSError:
            errs.append(finding(
                "G6.escape",
                f"G6 evidence: {criterion} observed escapes evidence/ "
                f"subtree: {observed}",
                owner=f"point-back.md#{criterion}",
                expected="observed path inside evidence/",
                actual=observed,
                repair="Point observed at an artifact under evidence/",
            ))
            continue
        try:
            resolved.relative_to(evidence_root)
        except ValueError:
            errs.append(finding(
                "G6.escape",
                f"G6 evidence: {criterion} observed escapes evidence/ "
                f"subtree: {observed}",
                owner=f"point-back.md#{criterion}",
                expected="observed path inside evidence/",
                actual=observed,
                repair="Point observed at an artifact under evidence/",
            ))
            continue
        # M6: defence in depth — mirror evidence/server.py
        # _resolve_artifact_path. ``Path.resolve`` and ``os.path.realpath``
        # can disagree on symlink chains across platforms, so a symlink under
        # evidence/ that resolves outside must also be rejected on the read
        # side (the write side already rejects it).
        try:
            Path(os.path.realpath(resolved)).relative_to(
                os.path.realpath(evidence_root))
        except ValueError:
            errs.append(finding(
                "G6.escape",
                f"G6 evidence: {criterion} observed escapes evidence/ "
                f"subtree: {observed}",
                owner=f"point-back.md#{criterion}",
                expected="observed path inside evidence/",
                actual=observed,
                repair="Point observed at an artifact under evidence/",
            ))
            continue
        if not resolved.is_file():
            errs.append(finding(
                "G6.artifact_missing",
                f"G6 evidence: {criterion} artifact missing: {observed}",
                owner=f"evidence/{leaf}",
                expected="artifact file on disk",
                actual="missing",
                repair=f"Capture or restore {observed}",
            ))
            continue
        # ledger observed is run-root-relative ("evidence/<name>"); manifest
        # artifact is evidence/-relative ("<name>", no prefix) per ticket 01.
        # Normalise the ledger leaf and compare to the manifest artifact
        # exactly; require the manifest criterion to match the ledger row.
        bound: list[dict] = []
        for entry in entries:
            if entry.get("criterion") != criterion:
                continue
            art = entry.get("artifact")
            if isinstance(art, str) and art == leaf:
                bound.append(entry)
        if not bound:
            # distinguish unknown-criterion (manifest binds a criterion not in
            # spec) from no-binding (manifest criterion != ledger criterion)
            unknown = [
                e for e in entries
                if isinstance(e.get("criterion"), str)
                and e["criterion"] not in valid_criterion_ids
                and isinstance(e.get("artifact"), str)
                and e["artifact"] == leaf
            ]
            if unknown:
                crit = unknown[0].get("criterion")
                errs.append(finding(
                    "G6.unknown_criterion",
                    f"G6 evidence: manifest binds unknown criterion {crit}",
                    owner="evidence/manifest.jsonl",
                    expected=f"criterion in L6.1..L6.{expected_l6}",
                    actual=str(crit),
                    repair="Bind the artifact to a declared L6 criterion",
                ))
            else:
                errs.append(finding(
                    "G6.no_binding",
                    f"G6 evidence: {criterion} no manifest entry binding "
                    f"{observed}",
                    owner="evidence/manifest.jsonl",
                    expected=f"manifest entry for {criterion} -> {leaf}",
                    actual="no binding",
                    repair="Append a manifest line binding criterion and artifact",
                ))
            continue
        latest = max(bound, key=lambda m: m.get("ts", ""))
        if latest.get("criterion") not in valid_criterion_ids:
            errs.append(finding(
                "G6.unknown_criterion",
                f"G6 evidence: manifest binds unknown criterion "
                f"{latest.get('criterion')}",
                owner="evidence/manifest.jsonl",
                expected=f"criterion in L6.1..L6.{expected_l6}",
                actual=str(latest.get("criterion")),
                repair="Bind the artifact to a declared L6 criterion",
            ))
            continue
        # Capture contract v1 (ADR-0018): bound evidence must embed a full
        # provider-echoed request snapshot — schemaVersion=1, complete
        # viewport, and freeze. Unversioned or partial snapshots have no
        # compatibility reader — recapture. Validated through the contract
        # module's read authority (fail-closed on malformed shape).
        capture = latest.get("capture") if isinstance(latest.get("capture"), dict) else {}
        request = latest.get("request")
        if not isinstance(request, dict):
            request = capture.get("request") if isinstance(capture.get("request"), dict) else {}
        capture_findings = _g6_capture_findings(criterion, request)
        if capture_findings:
            errs.extend(capture_findings)
            continue
        # artifact exists + bound + capture contract v1 -> valid; result is
        # the evaluator's call, not G6's.
    return errs
