"""Read-only change-scope projection for the existing run-status entry point."""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from design_playbook.mcp.evidence.containment import (
    REASON_NOT_REGULAR_FILE,
    read_under,
)
from design_playbook.mcp.evidence.capture_contract import validate_capture_snapshot
from design_playbook.mcp.evidence.path_syntax import probe_sidecar_rel
from design_playbook.mcp.run_console.repair_packet import derive_repair_packet
from design_playbook.mcp.run_console.snapshot_builder import build_snapshot, SnapshotBuildError
from design_playbook.mcp.run_console.source_registry import select_source_registry
from design_playbook.scripts.g1_spec import (
    SpecificationProjectionError,
    project_proof_requirements,
    project_scope_links,
)
from design_playbook.scripts.g6_evidence import (
    bound_capture_request, check_evidence, select_bound_entry,
)
from design_playbook.scripts.g11_coverage import check_sampling_matrix, project_sampling
from design_playbook.scripts.pointback_projection import (
    PointBackProjectionError, VerdictDisposition, project_pointback,
)
from design_playbook.scripts.run_facts import capture_run_facts

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROOF_CAPTURE_TYPES = {
    "screenshot": "screenshot",
    "a11y_tree": "a11y tree",
    "interaction_trace": "interaction trace",
}


class FrontendReviewError(ValueError):
    """Path-free input/read failure; no caller prose is echoed."""


def _validate_scope(scope: str, root: Path) -> None:
    kind, _, value = scope.partition(":")
    if kind in {"path", "page", "component"} and re.fullmatch(r"[\w.-]{1,100}", value):
        return
    if kind == "file" and re.fullmatch(r'[^\\:<>"|?*\x00-\x1f\x7f]{1,240}', value):
        parts = value.split("/")
        if all(part not in {"", ".", ".."} for part in parts):
            try:
                (root / value).resolve().relative_to(root.resolve())
                return
            except (OSError, ValueError):
                pass
    raise FrontendReviewError("invalid-scope")


def _read_source(root: Path, name: str) -> tuple[str, str | None]:
    resolved = read_under(root, name)
    if not resolved.ok:
        if resolved.reason == REASON_NOT_REGULAR_FILE:
            return "", None
        raise FrontendReviewError("source-outside-selected-run")
    try:
        raw = resolved.path.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeError):
        raise FrontendReviewError("source-unreadable") from None
    return text, "sha256:" + hashlib.sha256(raw).hexdigest()


def _git_clues(root: Path | None, base: str | None, head: str | None,
               worktree: bool) -> dict:
    if root is None and base is None and head is None and not worktree:
        return {"availability": "unknown", "reason": "not-requested", "files": []}
    if root is None or not base or (bool(head) == worktree):
        raise FrontendReviewError("git-input-incomplete")

    def read(*args: str) -> str:
        try:
            result = subprocess.run(
                ["git", "--no-optional-locks", "-C", str(root), *args],
                capture_output=True, timeout=15, check=True,
                env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
            )
            return result.stdout.decode("utf-8")
        except (OSError, UnicodeError, subprocess.SubprocessError):
            raise FrontendReviewError("git-input-unavailable") from None

    if Path(read("rev-parse", "--show-toplevel").strip()).resolve() != root.resolve():
        raise FrontendReviewError("git-root-must-be-explicit")
    base_hash = read("rev-parse", "--verify", "--end-of-options", base + "^{commit}").strip()
    head_hash = (read("rev-parse", "--verify", "--end-of-options", head + "^{commit}").strip()
                 if head else None)
    revisions = [base_hash] + ([head_hash] if head_hash else [])
    paths = read("diff", "--no-ext-diff", "--no-textconv", "--no-renames",
                 "--name-only", "-z", *revisions, "--").split("\0")
    if worktree:
        paths += read("ls-files", "--others", "--exclude-standard", "-z").split("\0")
    files = sorted(set(filter(None, paths)))
    for filename in files:
        _validate_scope("file:" + filename, root)
    return {"availability": "known", "base": base_hash, "head": head_hash,
            "worktree": worktree, "files": files}


def _authority(root: Path, filename: str, secret: bytes):
    registry = select_source_registry(root, PACKAGE_ROOT, secret)
    # Check registered run targets before invoking owners, including symlinked
    # children. The read-only projection never traverses outside those targets.
    targets = {target for source in registry.sources if source.root_scope == "run-root"
               for target in source.capture_targets}
    candidates = [root / target for target in targets]
    visited = set()
    while candidates:
        candidate = candidates.pop()
        try:
            resolved = candidate.resolve()
            resolved.relative_to(root.resolve())
        except (OSError, ValueError):
            raise FrontendReviewError("source-outside-selected-run") from None
        if resolved in visited:
            continue
        visited.add(resolved)
        if candidate.is_dir():
            try:
                candidates.extend(candidate.iterdir())
            except OSError:
                raise FrontendReviewError("source-unreadable") from None
    facts = capture_run_facts(
        spec_path=root / filename, pointback_path=root / "point-back.md",
        evidence_dir=root / "evidence",
    )
    try:
        snapshot = build_snapshot(
            selected_root=root, package_root=PACKAGE_ROOT, session_secret=secret,
            now=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        ).document
    except SnapshotBuildError:
        raise FrontendReviewError("owner-projection-unavailable") from None
    return facts, snapshot


def _binding(root: Path, criterion: str, token: str, entries: list[dict],
             expected_count: int, required: dict) -> dict:
    errors = check_evidence("", expected_count, root / "evidence", root,
                            observed_rows=[(criterion, token)], entries=entries)
    reasons = [error.rule_id for error in errors]
    leaf = token[len("evidence/"):]
    try:
        entry = select_bound_entry(entries, criterion, leaf)
    except ValueError:
        return {"integrity": "inconsistent", "reasons": ["conflicting-bindings"]}
    if entry is None:
        return {"integrity": "missing", "reasons": reasons or ["required-proof-missing"]}
    resolved = read_under(root, token)
    if not resolved.ok:
        return {"integrity": "missing", "reasons": reasons or ["artifact-unavailable"]}
    request = bound_capture_request(entry)
    reasons += ["capture." + fact.code for fact in validate_capture_snapshot(request)]
    capture = entry.get("capture")
    if isinstance(capture, dict):
        expected_type = PROOF_CAPTURE_TYPES.get(required["proof"])
        if expected_type is not None and capture.get("type") != expected_type:
            reasons.append("proof-type-mismatch")
        if required["state"] is not None and capture.get("state") != required["state"]:
            reasons.append("state-mismatch")
        artifact_path = capture.get("artifact_path")
        primary_artifacts = (artifact_path,)
        if capture.get("type") == "screenshot" and isinstance(artifact_path, str):
            primary_artifacts += (probe_sidecar_rel(artifact_path),)
        if token not in primary_artifacts:
            reasons.append("capture-artifact-mismatch")
    else:
        reasons.append("capture-metadata-unavailable")
    viewport = request.get("viewport")
    if required["viewport"] and (not isinstance(viewport, dict) or any(
            viewport.get(key) != value for key, value in required["viewport"].items())):
        reasons.append("viewport-mismatch")
    try:
        actual = hashlib.sha256(resolved.path.read_bytes()).hexdigest()
    except OSError:
        return {"integrity": "missing", "reasons": reasons + ["artifact-unreadable"]}
    expected = entry.get("sha256")
    if expected != actual:
        reasons.append("artifact-hash-mismatch" if expected else "artifact-hash-unavailable")
    integrity = "stale" if "artifact-hash-mismatch" in reasons else "invalid" if reasons else "complete"
    return {"integrity": integrity, "reasons": sorted(set(reasons)),
            "source": f"evidence/manifest.jsonl#{criterion}", "content_hash": "sha256:" + actual}


def _evidence_gaps(root: Path, requirements, filename: str, digest: str | None,
                   facts) -> list[dict]:
    ids = tuple(item.criterion for item in requirements)
    try:
        pointback = project_pointback(facts.pointback_text, ids)
        evaluations = {item.criterion_id: item for item in pointback.criteria}
        audited = pointback.verdict != VerdictDisposition.UNAUDITED
    except PointBackProjectionError:
        evaluations = {}
        audited = False
    entries = list(facts.manifest_entries)
    manifest_bad = any(error.artifact == "manifest" for error in facts.read_errors)
    gaps = []
    for requirement in requirements:
        required = {
            "proof": requirement.proof, "state": requirement.state,
            "viewport": (dict(zip(("width", "height"), requirement.viewport))
                         if requirement.viewport else None),
        }
        evaluation = evaluations.get(requirement.criterion)
        tokens = ([evaluation.artifact_token] if evaluation and evaluation.artifact_token else
                  sorted({"evidence/" + entry["artifact"] for entry in entries
                          if entry.get("criterion") == requirement.criterion
                          and isinstance(entry.get("artifact"), str)}))
        bindings = [_binding(root, requirement.criterion, token, entries, len(ids), required)
                    for token in tokens]
        complete = any(item["integrity"] == "complete" for item in bindings)
        availability = requirement.availability
        binding = "complete" if complete else "missing"
        if manifest_bad or any(item["integrity"] == "inconsistent" for item in bindings):
            availability, binding = "inconsistent", "inconsistent"
        elif any(item["integrity"] == "stale" for item in bindings) and not complete:
            availability, binding = "stale", "stale"
        elif bindings and not complete:
            binding = bindings[0]["integrity"]
        reasons = sorted({reason for item in bindings for reason in item["reasons"]})
        if manifest_bad:
            reasons.append("manifest-malformed")
        status = "available" if complete and availability == "known" else "blocked"
        if requirement.availability != "known":
            status = "unknown"
            reasons.append("requirement-unavailable")
        elif not bindings:
            reasons.append("required-proof-missing")
        not_applicable = None
        if audited and evaluation and evaluation.outcome == "notApplicable":
            status = "notApplicable"
            not_applicable = {"source": f"point-back.md#{requirement.criterion}",
                              "source_hash": "sha256:" + hashlib.sha256(
                                  facts.pointback_text.encode("utf-8")).hexdigest(),
                              "text": "withheld; consult source"}
        gaps.append({
            "criterion": requirement.criterion,
            "declaration": f"{filename}#{requirement.criterion}", "source_hash": digest,
            "required": required, "availability": availability, "binding": binding,
            "bindings": bindings, "status": status,
            "evaluator": evaluation.outcome if audited and evaluation else "unaudited",
            "not_applicable_reason": not_applicable, "reasons": sorted(set(reasons)),
        })
    return gaps


def _context_hash(snapshot: dict, root: Path, digest: str | None,
                  gaps: list[dict], scopes: tuple[str, ...], clues: dict, facts) -> str:
    records = [{key: row[key] for key in
                ("sourceRef", "readState", "observedHash", "verifiedHash", "freshness")}
               for row in snapshot["sources"]["items"]
               if row["sourceRef"] != "source.selected-run"]
    value = {"root": str(root.resolve()), "records": records, "spec": digest,
             "gaps": gaps, "scopes": scopes, "clues": clues,
             "parser_inputs": [hashlib.sha256(text.encode("utf-8")).hexdigest() for text in (
                 facts.spec_text, facts.pointback_text, facts.manifest_raw_text)]}
    return "sha256:" + hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()


def _proposal(snapshot: dict, impact: list[dict], gaps: list[dict],
              freshness: str) -> dict:
    packet = derive_repair_packet(snapshot)
    contract = snapshot["intent"]["contract"]
    contract_source = next(row for row in snapshot["sources"]["items"]
                           if row["sourceRef"] == "source.contract-bind")
    inconsistent = (contract_source["readState"] != "missing"
                    and contract["availability"] != "known")
    availability = "stale" if freshness == "stale" else "inconsistent" if inconsistent else "known"
    included: dict[str, set[str]] = {}
    sources: dict[str, set[str]] = {}

    def include(criterion: str, reason: str, *refs: str) -> None:
        included.setdefault(criterion, set()).add(reason)
        sources.setdefault(criterion, set()).update(refs)

    invalidated = packet["invalidatedEvidence"]
    for criterion in invalidated["value"] or []:
        include(criterion, "owner-invalidated", "point-back.md#invalidated-evidence")
    for item in impact:
        for link in item["links"]:
            include(link["criterion"], "declared-scope-association", link["declaration"])
    unresolved = any(item["availability"] != "known" for item in impact)
    for gap in gaps:
        if gap["status"] in {"blocked", "unknown"}:
            include(gap["criterion"], "evidence-gap", gap["declaration"],
                    *(binding["source"] for binding in gap["bindings"] if "source" in binding))
        if unresolved or invalidated["availability"] != "known":
            include(gap["criterion"], "cannot-safely-narrow", gap["declaration"])
    fields = {}
    for name, key in (
        ("invalidated_evidence", "invalidatedEvidence"), ("resume_stage", "resumeStage"),
        ("next_command", "nextCommand"), ("recapture_requirement", "recaptureRequirement"),
        ("owner", "nextOwner"),
    ):
        fact = packet[key]
        value = fact["value"]
        if name == "owner" and isinstance(value, dict):
            value = {key: value[key] for key in ("actor", "role", "kind", "actionId")}
        field_state = availability if availability != "known" else fact["availability"]
        fields[name] = {"availability": field_state, "value": value,
                        "source": fact["sourceId"]}
    if fields["next_command"]["availability"] != "known":
        fields["next_command"]["value"] = None
    reasons = ["declarations-do-not-prove-exhaustive-impact"]
    if unresolved:
        reasons.append("scope-unresolved")
    if invalidated["availability"] != "known":
        reasons.append("owner-invalidations-unavailable")
    if freshness == "stale":
        reasons.append("source-not-current-refresh-required")
    if inconsistent:
        reasons.append("contract-unavailable")
    return {
        "availability": availability,
        # These declarations link scope to criteria; they never prove that
        # all code dependencies are captured. Keep the owner scope in force.
        "can_narrow": False, "reasons": reasons, "unaffected": [],
        "included": [{"criterion": criterion, "reasons": sorted(reasons),
                      "sources": sorted(sources[criterion])}
                     for criterion, reasons in sorted(included.items())],
        **fields,
    }


def build_frontend_review(
    run_root: Path, scopes: tuple[str, ...], *,
    git_root: Path | None = None, base_revision: str | None = None,
    head_revision: str | None = None, worktree: bool = False,
    expected_source_hash: str | None = None,
) -> dict:
    """Derive explicit links; an empty association never means unaffected."""
    if not run_root.is_dir():
        raise FrontendReviewError("selected-run-invalid")
    if expected_source_hash is not None and not re.fullmatch(r"sha256:[a-f0-9]{64}", expected_source_hash):
        raise FrontendReviewError("invalid-source-hash")
    clues = _git_clues(git_root, base_revision, head_revision, worktree)
    scopes = scopes + tuple("file:" + name for name in clues["files"])
    for scope in scopes:
        _validate_scope(scope, git_root or run_root)
    spec, digest = _read_source(run_root, "spec.md")
    filename = "spec.md"
    if digest is None:
        filename = "01-spec.md"
        spec, digest = _read_source(run_root, filename)
    try:
        links = project_scope_links(spec)
        state = "known"
    except SpecificationProjectionError:
        links = ()
        state = "inconsistent" if digest is not None else "unknown"
    impact = []
    for scope in dict.fromkeys(scopes):
        matches = [link for link in links if link.scope == scope]
        assumed = any(link.assumed for link in matches)
        availability = state if state != "known" else (
            "assumed" if assumed else "known" if matches else "unknown"
        )
        impact.append({
            "scope": scope,
            "availability": availability,
            "confirmation": None if availability == "known" else "review-source-declaration",
            "reason": "declared-path-reference" if matches else "no-declared-association",
            "links": [{
                "criterion": link.criterion,
                "declaration": f"{filename}#L3.{link.path}",
                "reason": "declared-path-reference",
                "source_hash": digest,
            } for link in matches],
        })
    try:
        requirements = project_proof_requirements(spec)
    except SpecificationProjectionError:
        requirements = ()
    secret = secrets.token_bytes(32)
    facts, snapshot = _authority(run_root, filename, secret)
    gaps = _evidence_gaps(run_root, requirements, filename, digest, facts)
    verdict = snapshot["evaluation"]["verdict"]
    sampling = project_sampling(facts.pointback_text, spec)
    for row in sampling:
        if not re.fullmatch(r"[\w.-]{1,100}", row["page"]):
            row["page"] = "withheld"
    sampling_findings = check_sampling_matrix(facts.pointback_text, spec, run_root / "evidence")
    source_hash = _context_hash(snapshot, run_root, digest, gaps, scopes, clues, facts)
    verified_facts, verified_snapshot = _authority(run_root, filename, secret)
    _, verified_digest = _read_source(run_root, filename)
    verified_gaps = _evidence_gaps(
        run_root, requirements, filename, verified_digest, verified_facts)
    verified_clues = _git_clues(git_root, base_revision, head_revision, worktree)
    verified_hash = _context_hash(
        verified_snapshot, run_root, verified_digest, verified_gaps, scopes, verified_clues,
        verified_facts)
    normalized_spec = spec.replace("\r\n", "\n").replace("\r", "\n")
    owners_current = all(
        row["observedHash"] is None or row["freshness"] == "current"
        for owner in (snapshot, verified_snapshot) for row in owner["sources"]["items"])
    fresh = (owners_current and source_hash == verified_hash and facts.spec_text == normalized_spec
             and (expected_source_hash is None or expected_source_hash == source_hash))
    freshness = "current" if fresh else "stale"
    if not fresh:
        for item in impact:
            item["availability"] = "stale"
        for gap in gaps:
            gap["availability"] = "stale"
        verdict = {**verdict, "availability": "stale"}
    return {"impact": impact, "unaffected": [], "change_clues": clues,
            "source_hash": source_hash, "freshness": freshness,
            "evidence_gaps": gaps, "sampling": sampling,
            "sampling_reasons": sorted({finding.rule_id for finding in sampling_findings}),
            "reverification": _proposal(snapshot, impact, gaps, freshness),
            "evaluation": {"availability": verdict["availability"],
                           "value": verdict["result"] or "unaudited"}}


def text_lines(report: dict) -> list[str]:
    lines = ["Frontend review (read-only; not an acceptance verdict)"]
    for item in report["impact"]:
        criteria = ", ".join(link["criterion"] for link in item["links"]) or "unknown"
        lines.append(f"{item['scope']}: {item['availability']} -> {criteria}")
        for link in item["links"]:
            lines.append(f"  {link['criterion']} <- {link['declaration']}; "
                         f"{link['reason']}; {link['source_hash']}")
        if item["confirmation"]:
            lines.append(f"  confirmation: {item['confirmation']}")
    lines.append("No association does not establish that a criterion is unaffected.")
    lines.append(f"Sources: {report['freshness']} {report['source_hash']}")
    evaluation = report["evaluation"]
    lines.append(f"Evaluation ({evaluation['availability']}): {evaluation['value']}")
    for gap in report["evidence_gaps"]:
        required = gap["required"]
        lines.append(f"{gap['criterion']}: {gap['status']}; binding={gap['binding']}; "
                     f"source={gap['availability']}; evaluator={gap['evaluator']}; "
                     f"proof={required['proof']}; state={required['state']}; "
                     f"viewport={required['viewport']}; reasons={','.join(gap['reasons']) or 'none'}")
        for binding in gap["bindings"]:
            if "source" in binding:
                lines.append(f"  Evidence: {binding['source']}; {binding['content_hash']}; "
                             f"{binding['integrity']}")
        if gap["not_applicable_reason"]:
            reason = gap["not_applicable_reason"]
            lines.append(f"  N/A reason: {reason['source']}; {reason['source_hash']}")
    for row in report["sampling"]:
        lines.append(f"Sampling {row['page']}/{row['state']}: {row['status']}")
    if report["sampling_reasons"]:
        lines.append("Sampling diagnostics: " + ", ".join(report["sampling_reasons"]))
    proposal = report["reverification"]
    lines.append("Reverification candidates: " + (
        ", ".join(row["criterion"] for row in proposal["included"]) or "unknown"))
    for row in proposal["included"]:
        lines.append(f"  {row['criterion']}: {', '.join(row['reasons'])}; "
                     f"sources={', '.join(row['sources'])}")
    lines.append("Cannot safely narrow the original owner scope.")
    for key in ("owner", "invalidated_evidence", "resume_stage",
                "recapture_requirement", "next_command"):
        fact = proposal[key]
        lines.append(f"{key} ({fact['availability']}): {fact['value']}")
    return lines
