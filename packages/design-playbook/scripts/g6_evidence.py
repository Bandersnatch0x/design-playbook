"""G6 evidence-binding gate (ADR-0023).

Conditional: if a ledger ``observed`` references an ``evidence/`` artifact,
require the artifact to exist and a manifest entry to bind it to the
matching L6.<n> (multi-entry: latest by ts wins). Includes the soft
manifest-ts and superseded-artifact warnings. Bound manifest request
snapshots validate through the bundled Evidence runtime's
``validate_capture_snapshot`` (ADR-0018 enforcement site 3).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from design_playbook.scripts._diagnostics import Finding, finding
from design_playbook.scripts.stages import EVIDENCE_PREFIX
from design_playbook.mcp.evidence.capture_contract import validate_capture_snapshot


def _ledger_observed(text: str) -> list[tuple[str, str]]:
    """Return (criterion, observed) pairs for each evidence row.

    The G6 evidence path is the leading token of the observed line; trailing
    commentary after whitespace, a (full/half-width) paren, or a
    (full/half-width) comma / colon is tolerated so authors can annotate
    ``evidence/`` rows without a false-positive G6 fail (issue 03). Free-text
    observed is unaffected — G6 only checks evidence/ rows, and a leading
    token starting with ``evidence/`` never appears in free text.

    Keep the tolerated separators in sync with skills/ui-evaluator/SKILL.md
    (which teaches authors what punctuation may follow the artifact path).
    """
    pairs: list[tuple[str, str]] = []
    for block in re.split(r"\n\s*\n", text):
        crit = re.search(r"^criterion:\s*(\S+)", block, re.I | re.M)
        obs = re.search(r"^observed:\s*(.+)$", block, re.I | re.M)
        if crit and obs:
            raw = obs.group(1).strip()
            lead = re.match(r"[^\s（(,，:：]+", raw)
            observed = lead.group(0) if lead else raw
            pairs.append((crit.group(1).strip(), observed))
    return pairs


def _manifest_entries(evidence_dir: Path) -> list[dict]:
    """Read .scratch/<run>/evidence/manifest.jsonl; one dict per non-empty line."""
    path = evidence_dir / "manifest.jsonl"
    if not path.is_file():
        return []
    entries: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            entries.append(data)
    return entries


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
    entries = _manifest_entries(evidence_dir)
    valid_criterion_ids = {f"L6.{n}" for n in range(1, expected_l6 + 1)}
    evidence_root = (root / "evidence").resolve()

    errs: list[Finding] = []
    for criterion, observed in _ledger_observed(pointback_text):
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


def check_manifest_ts_warnings(evidence_dir: Path | None) -> list[Finding]:
    """Soft signal: all manifest rows share one ``ts`` (likely batch bind).

    Not a hard gate — root fix is orchestrator per-capture append (SKILL step 8).
    Printed as WARN; does not fail the run. Fires only when ≥2 entries exist and
    every non-empty ``ts`` value is identical (including when some rows omit ts
    only if at least two share the same non-empty value and no other ts exists).
    """
    if evidence_dir is None or not evidence_dir.is_dir():
        return []
    entries = _manifest_entries(evidence_dir)
    if len(entries) < 2:
        return []
    ts_vals = [
        e.get("ts") for e in entries
        if isinstance(e.get("ts"), str) and e.get("ts").strip()
    ]
    if len(ts_vals) < 2:
        return []
    if len(set(ts_vals)) == 1:
        return [finding(
            "G6.batch_ts",
            "G6 evidence: all manifest entries share one ts "
            f"({ts_vals[0]}); prefer per-capture append "
            "(batch bind weakens multi-entry latest-by-ts)",
            owner="evidence/manifest.jsonl",
            expected="distinct per-capture timestamps",
            actual=ts_vals[0],
            repair="Append manifest entries at capture time, not in batch",
            severity="warning",
        )]
    return []


def check_superseded_ledger_warnings(
        pointback_text: str,
        evidence_dir: Path | None) -> list[Finding]:
    """Warn when a ledger cites an artifact that is not the latest binding."""
    if evidence_dir is None or not evidence_dir.is_dir():
        return []
    entries = _manifest_entries(evidence_dir)
    if not entries:
        return []
    # Latest artifact per criterion by ts.
    latest_by_crit: dict[str, str] = {}
    for crit in {e.get("criterion") for e in entries if isinstance(e.get("criterion"), str)}:
        candidates = [
            e for e in entries
            if e.get("criterion") == crit and isinstance(e.get("artifact"), str)
        ]
        if not candidates:
            continue
        latest = max(candidates, key=lambda m: m.get("ts", ""))
        latest_by_crit[crit] = latest["artifact"]

    warns: list[Finding] = []
    for criterion, observed in _ledger_observed(pointback_text):
        if not observed.casefold().startswith(EVIDENCE_PREFIX):
            continue
        leaf = observed[len(EVIDENCE_PREFIX):]
        current = latest_by_crit.get(criterion)
        if current and leaf != current:
            warns.append(finding(
                "G6.superseded_artifact",
                f"G6 evidence: {criterion} ledger cites {observed} but latest "
                f"manifest binding is evidence/{current}",
                owner=f"point-back.md#{criterion}",
                expected=f"evidence/{current}",
                actual=observed,
                repair="Update the ledger to the current artifact or recapture",
                severity="warning",
            ))
    return warns


def _ledger_has_evidence_binding(pointback_text: str) -> bool:
    for _criterion, observed in _ledger_observed(pointback_text):
        # Match check_evidence: case-insensitive evidence/ prefix (LOW-3).
        if observed.casefold().startswith(EVIDENCE_PREFIX):
            return True
    return False
