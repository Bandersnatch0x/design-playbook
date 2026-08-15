"""G10 design-decision gate (vNext S2, design-prototype 4.1 machine face).

Conditional: fires only when the decision report carries DD entry blocks
(appended after the verbatim top block). Owns the machine-checkable face
declared by the protocol — entry completeness, tier/status enums, tier
recording obligations (R one-line rationale / C trade-off record / E user
confirmation), supersedes existence + acyclicity, registry rule-reference
cross-check, preview transaction linkage (decision_id), R3 re-entry
resolution (dd: challenges must end invalidated with an E-tier revision;
``dd:`` on a positive finding is a shape error, issue #44), and the
baseline-drift stale review (three exits: keep / revise / escalate).

Comparison-matrix quality, trade-off sufficiency, and tier-grading
judgement calls (composition change, identity drift beyond declared
deviations) stay protocol-side. P1 runs carry no DD entries by definition
(loop-prototype 1.2): entries on a P1 profile are an upgrade signal.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from design_playbook.scripts._diagnostics import Finding, finding
from design_playbook.scripts.dd_entries import (
    ADAPTER_HANDLE,
    CANDIDATE_SOURCES,
    CONFIRM_KINDS,
    DD_ID,
    DD_HEADING,
    RETIRED_STATUSES,
    SHA256,
    STALE_EXITS,
    DDEntry,
    collect_e_signals,
    is_cross_run_ref,
    local_dd_id,
    parse_dd_entries,
    positive_dd_refs,
)

# rules.md ships inside the package (read-only protocol consumption, the
# same file the product-level G8 gate validates); referenced lazily so the
# gate still runs when the skill payload is not installed.
_REGISTRY_PARTS = ("skills", "design-playbook", "references", "rules.md")
RULE_REF = re.compile(r"^([A-Z][A-Z0-9]*-[0-9]{2})@([0-9]+)$")


def default_registry_text() -> str | None:
    """Read the bundled rule registry; None when not shipped alongside."""
    path = Path(__file__).resolve().parents[1].joinpath(*_REGISTRY_PARTS)
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _blocks(text: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"^## ([A-Z][A-Z0-9]*-[0-9]{2})\b.*$", text, re.M))
    blocks: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks.append((match.group(1), text[match.start():end]))
    return blocks


def _registry_ids(text: str) -> dict[str, int]:
    """Map registry id -> version via the entry headings + version fields."""
    ids: dict[str, int] = {}
    for entry_id, body in _blocks(text):
        version_match = re.search(r"^version:[ \t]*([0-9]+)$", body, re.M)
        ids[entry_id] = int(version_match.group(1)) if version_match else 0
    return ids


def _fmt(owner: str) -> str:
    return f"decision-report.md#{owner}"


def _entry_checks(entries: list[DDEntry]) -> list[Finding]:
    errs: list[Finding] = []
    seen: dict[str, int] = {}
    for index, entry in enumerate(entries, 1):
        label = entry.id or f"entry-{index}"
        if not DD_ID.match(label):
            errs.append(finding(
                "G10.bad_id",
                f"G10 decisions: entry id {label!r} fails ^DD-[0-9]{{4}}$ "
                "(zero-padded, run-unique; cross-run refs add <run>/)",
                owner=_fmt(label),
                expected="DD-#### id",
                actual=label,
                repair="Renumber the entry heading and id field to DD-####",
            ))
        if label in seen:
            errs.append(finding(
                "G10.duplicate_id",
                f"G10 decisions: duplicate entry id {label}",
                owner=_fmt(label),
                expected="run-unique ids",
                actual="duplicate",
                repair="Renumber one of the entries (DD ids never repeat "
                       "inside a run)",
            ))
        seen[label] = index

        # fold defects first (issue #44 follow-up): a named unterminated /
        # comma-less fold error outranks the indirect missing_* findings it
        # causes downstream, so the error face points at the real defect.
        errs += _fold_checks(entry)

        for key in ("id", "tier", "question", "status"):
            if not entry.fields.get(key, "").strip():
                errs.append(finding(
                    "G10.missing_field",
                    f"G10 decisions: {label} missing required field {key}:",
                    owner=_fmt(label),
                    expected=f"non-empty {key}",
                    actual="missing",
                    repair=f"Add {key}: to the {label} entry block",
                ))
        if entry.tier and entry.tier not in {"record", "compare", "explore"}:
            errs.append(finding(
                "G10.invalid_tier",
                f"G10 decisions: {label} tier {entry.tier!r} not in "
                "record|compare|explore",
                owner=_fmt(label),
                expected="record|compare|explore",
                actual=entry.tier,
                repair="Re-grade the decision against the R/C/E trigger "
                       "table (design-prototype 1.1)",
            ))
        if entry.status and entry.status not in {
                "open", "compared", "confirmed-agent", "confirmed-user",
                "superseded", "invalidated"}:
            errs.append(finding(
                "G10.invalid_status",
                f"G10 decisions: {label} status {entry.status!r} not in "
                "open|compared|confirmed-agent|confirmed-user|superseded"
                "|invalidated",
                owner=_fmt(label),
                expected="status enum",
                actual=entry.status,
                repair="Use a status from the closed enum",
            ))
        errs += _candidate_checks(entry)
        errs += _selection_checks(entry)
        errs += _confirmation_checks(entry)
        errs += _baseline_rule_checks(entry)
    return errs


def _fold_checks(entry: DDEntry) -> list[Finding]:
    """Fold defects on ``- {…}`` items (issue #44 follow-up, fail-closed).

    A fold break without a comma merges the next key into the previous
    value (the parse alone would accept it silently); a fold that never
    balances swallows the rest of the block and only indirect missing_*
    errors would fire. Both get a named error up front, with the block line
    of the fold-opening marker; the remaining shape errors still fire.
    """
    errs: list[Finding] = []
    for issue in entry.fold_issues:
        if issue.kind == "unterminated":
            errs.append(finding(
                "G10.fold_unterminated",
                f"G10 decisions: {entry.id} opens a folded flow-map item at "
                f"block line {issue.line} that never closes its brace — the "
                "fold swallowed the rest of the entry block",
                owner=_fmt(entry.id),
                expected="braces balance inside the entry block",
                actual=f"unterminated fold from block line {issue.line}",
                repair="Close the brace, or unfold to the canonical "
                       "single-line item",
            ))
        else:
            errs.append(finding(
                "G10.fold_break_not_comma",
                f"G10 decisions: {entry.id} folds a flow-map item at block "
                f"line {issue.line} without a comma at the break — the next "
                "key merges into the previous value",
                owner=_fmt(entry.id),
                expected="fold breaks end with a comma (or the opening "
                         "brace)",
                actual=f"break after {issue.tail!r}",
                repair="End the folded line with a comma before continuing "
                       "the item on the next line",
            ))
    return errs


def _candidate_checks(entry: DDEntry) -> list[Finding]:
    errs: list[Finding] = []
    label = entry.id
    count = len(entry.candidates)
    if entry.tier in {"compare", "explore"} and not 2 <= count <= 3:
        errs.append(finding(
            "G10.candidate_count",
            f"G10 decisions: {label} tier {entry.tier} needs 2-3 "
            f"candidates (no comparison, no exploration), found {count}",
            owner=_fmt(label),
            expected="2-3 candidates",
            actual=f"{count}",
            repair="Add or drop candidates (R tier takes exactly one; "
                   "C/E compare 2-3)",
        ))
    if entry.tier == "record" and count > 1:
        errs.append(finding(
            "G10.candidate_count",
            f"G10 decisions: {label} record tier lists {count} candidates; "
            "a single reasonable choice is the R-tier trigger",
            owner=_fmt(label),
            expected="0-1 candidates",
            actual=f"{count}",
            repair="Demote to a selection line or re-grade to compare",
        ))
    ids: list[str] = []
    for position, candidate in enumerate(entry.candidates, 1):
        cid = candidate.get("id", "")
        where = f"{label}.candidate-{cid or position}"
        if not cid:
            errs.append(finding(
                "G10.bad_candidate",
                f"G10 decisions: {where} has no id",
                owner=_fmt(where),
                expected="candidate id",
                actual="missing",
                repair="Give every candidate a short id (A/B/C or a slug)",
            ))
        if cid in ids:
            errs.append(finding(
                "G10.bad_candidate",
                f"G10 decisions: {where} duplicates candidate id {cid!r}",
                owner=_fmt(where),
                expected="unique candidate ids",
                actual="duplicate",
                repair="Renumber the candidate ids inside the entry",
            ))
        ids.append(cid)
        source = candidate.get("source", "")
        if source not in CANDIDATE_SOURCES:
            errs.append(finding(
                "G10.bad_candidate",
                f"G10 decisions: {where} source {source!r} not in "
                "agent|provider-adapter|user",
                owner=_fmt(where),
                expected="agent|provider-adapter|user",
                actual=source,
                repair="Record the provenance channel for the candidate",
            ))
        if source == "provider-adapter":
            adapter = candidate.get("adapter", "")
            if not adapter:
                errs.append(finding(
                    "G10.bad_candidate",
                    f"G10 decisions: {where} provider-adapter candidate "
                    "lacks the anonymous adapter handle",
                    owner=_fmt(where),
                    expected="adapter: <anonymous handle>",
                    actual="missing",
                    repair="Record the project-local anonymous handle "
                           "(named products are never recorded)",
                ))
            elif not ADAPTER_HANDLE.match(adapter):
                errs.append(finding(
                    "G10.bad_candidate",
                    f"G10 decisions: {where} adapter handle {adapter!r} is "
                    "not anonymous (lowercase handle shape)",
                    owner=_fmt(where),
                    expected="lowercase anonymous handle",
                    actual=adapter,
                    repair="Use the project's anonymous handle convention",
                ))
        for key in ("summary",):
            if not candidate.get(key, "").strip():
                errs.append(finding(
                    "G10.bad_candidate",
                    f"G10 decisions: {where} has no {key}",
                    owner=_fmt(where),
                    expected=f"one-line {key}",
                    actual="missing",
                    repair=f"Add the {key} line for candidate {cid or position}",
                ))
        for asset in _assets(candidate.get("assets", "")):
            if not re.match(r"^\S+\s+sha256:[0-9a-f]{64}$", asset, re.I):
                errs.append(finding(
                    "G10.bad_candidate",
                    f"G10 decisions: {where} asset {asset!r} is not "
                    "<path> sha256:<digest> shaped",
                    owner=_fmt(where),
                    expected="path + sha256 reference",
                    actual=asset[:80],
                    repair="Reference candidate assets as path + sha256 "
                           "(run-local candidates/ layer)",
                ))
    return errs


def _assets(value: str) -> list[str]:
    value = value.strip()
    if not (value.startswith("[") and value.endswith("]")):
        return []
    return [part.strip() for part in value[1:-1].split(",") if part.strip()]


def _selection_checks(entry: DDEntry) -> list[Finding]:
    errs: list[Finding] = []
    label = entry.id
    candidate_id = entry.selection.get("candidate", "").strip()
    rationale = entry.selection.get("rationale", "").strip()
    if not candidate_id:
        errs.append(finding(
            "G10.missing_selection",
            f"G10 decisions: {label} selection has no candidate",
            owner=_fmt(label),
            expected="selection.candidate",
            actual="missing",
            repair="Record which candidate was chosen",
        ))
    if not rationale:
        errs.append(finding(
            "G10.missing_selection",
            f"G10 decisions: {label} selection has no rationale "
            "(R tier records one line; C/E point back at an axis or "
            "trade-off)",
            owner=_fmt(label),
            expected="selection.rationale",
            actual="missing",
            repair="Record the one-line reason (R) or axis-pointing "
                   "rationale (C/E)",
        ))
    ids = set(entry.candidate_ids())
    if ids and candidate_id and candidate_id not in ids:
        errs.append(finding(
            "G10.unknown_candidate",
            f"G10 decisions: {label} selects {candidate_id!r} which is not "
            "a listed candidate",
            owner=_fmt(label),
            expected=f"one of {sorted(ids)}",
            actual=candidate_id,
            repair="Select a listed candidate or add it to the entry",
        ))

    if entry.tier in {"compare", "explore"}:
        if not entry.comparison_axes:
            errs.append(finding(
                "G10.missing_comparison",
                f"G10 decisions: {label} tier {entry.tier} has no "
                "comparison axes (facts and statements, never scores)",
                owner=_fmt(label),
                expected="comparison.axes rows",
                actual="missing",
                repair="Record the dimension x candidate matrix rows "
                       "(one statement + source per cell)",
            ))
        if not entry.comparison_tradeoffs.strip():
            errs.append(finding(
                "G10.missing_comparison",
                f"G10 decisions: {label} tier {entry.tier} has no trade-off "
                "statement",
                owner=_fmt(label),
                expected="comparison.tradeoffs line",
                actual="missing",
                repair="Record the explicit trade-off statement "
                       "('A trades X for Y')",
            ))
        rejected = {
            item.get("candidate", ""): item.get("reason", "").strip()
            for item in entry.rejected
        }
        for cid in sorted(ids - {candidate_id}):
            reason = rejected.get(cid, "")
            if not reason:
                errs.append(finding(
                    "G10.missing_rejected",
                    f"G10 decisions: {label} rejects candidate {cid} "
                    "without a reason (rejection reasons rank with the "
                    "selection rationale)",
                    owner=_fmt(label),
                    expected=f"rejected reason for {cid}",
                    actual="missing",
                    repair=f"Record why {cid} was rejected",
                ))
    return errs


def _confirmation_checks(entry: DDEntry) -> list[Finding]:
    errs: list[Finding] = []
    label = entry.id
    kind = entry.confirmation.get("kind", "")
    via = entry.confirmation.get("via", "").strip()
    confirmed_at = entry.confirmation.get("confirmed_at", "").strip()
    if entry.tier == "explore":
        if not entry.confirmation or kind != "user":
            errs.append(finding(
                "G10.e_needs_user_confirmation",
                f"G10 decisions: {label} explore tier requires a user "
                "confirmation record (kind: user)",
                owner=_fmt(label),
                expected="confirmation.kind: user",
                actual=kind or "missing",
                repair="Record the user confirmation (preview transaction "
                       "when present, report batch otherwise)",
            ))
        if kind == "user" and not via:
            errs.append(finding(
                "G10.e_needs_user_confirmation",
                f"G10 decisions: {label} user confirmation lacks via "
                "(preview-round-<n> decision_id:<id> or report-batch)",
                owner=_fmt(label),
                expected="confirmation.via channel",
                actual="missing",
                repair="Record the confirmation channel",
            ))
        if kind == "user" and not confirmed_at:
            errs.append(finding(
                "G10.e_needs_user_confirmation",
                f"G10 decisions: {label} user confirmation lacks "
                "confirmed_at",
                owner=_fmt(label),
                expected="confirmation.confirmed_at timestamp",
                actual="missing",
                repair="Record when the user confirmed",
            ))
    elif entry.confirmation and kind and kind not in CONFIRM_KINDS:
        errs.append(finding(
            "G10.bad_confirmation",
            f"G10 decisions: {label} confirmation kind {kind!r} not in "
            "user|agent",
            owner=_fmt(label),
            expected="user|agent",
            actual=kind,
            repair="Use the confirmation kind enum",
        ))
    if entry.tier in {"record", "compare"} and kind == "user":
        errs.append(finding(
            "G10.rc_confirmation_not_agent",
            f"G10 decisions: {label} tier {entry.tier} records a user "
            "confirmation; R/C stay agent-decided (upgrade the tier or "
            "fix the record)",
            owner=_fmt(label),
            expected="kind: agent on R/C tiers",
            actual="user",
            repair="Re-grade to explore or correct the confirmation kind",
        ))
    if entry.status == "confirmed-user" and kind != "user":
        errs.append(finding(
            "G10.bad_confirmation",
            f"G10 decisions: {label} status is confirmed-user but the "
            f"confirmation kind is {kind or 'missing'!r}",
            owner=_fmt(label),
            expected="confirmation.kind: user",
            actual=kind or "missing",
            repair="Record the user confirmation or fix the status",
        ))
    if via and not (
            re.match(r"^preview-round-[0-9]+\s+decision_id:[0-9A-Za-z-]+$", via)
            or re.match(r"^report-batch", via)
            or via == "agent-record"):
        errs.append(finding(
            "G10.bad_confirmation",
            f"G10 decisions: {label} confirmation via {via!r} is not a "
            "declared channel (preview-round-<n> decision_id:<id> | "
            "report-batch | agent-record)",
            owner=_fmt(label),
            expected="declared confirmation channel",
            actual=via[:80],
            repair="Record the confirmation provenance channel",
        ))
    return errs


def _baseline_rule_checks(entry: DDEntry) -> list[Finding]:
    errs: list[Finding] = []
    label = entry.id
    baseline = entry.baseline_ref.strip()
    spec_refs = entry.constraints.get("spec", "").strip()
    if not baseline and not _bracket(spec_refs):
        errs.append(finding(
            "G10.missing_constraints",
            f"G10 decisions: {label} cites no constraints (baseline or "
            "spec reference required on every tier)",
            owner=_fmt(label),
            expected="constraints.baseline or constraints.spec",
            actual="missing",
            repair="Record the bound baseline (path + sha256 or waived:) "
                   "or the spec references",
        ))
    if baseline and not (
            baseline.startswith("waived:")
            or SHA256.search(baseline)
    ):
        errs.append(finding(
            "G10.bad_baseline",
            f"G10 decisions: {label} baseline {baseline!r} is neither "
            "waived:<reason> nor <path> sha256:<digest>",
            owner=_fmt(label),
            expected="waived: reason or path + sha256",
            actual=baseline[:80],
            repair="Pin the baseline binding or record the waiver",
        ))
    return errs


def _bracket(value: str) -> list[str]:
    value = value.strip()
    if not (value.startswith("[") and value.endswith("]")):
        return []
    return [part.strip() for part in value[1:-1].split(",") if part.strip()]


def _rules_checks(
        entries: list[DDEntry],
        registry_text: str | None) -> list[Finding]:
    errs: list[Finding] = []
    registry = None
    if registry_text is None:
        registry_text = default_registry_text()
    if registry_text:
        registry = _registry_ids(registry_text)
    for entry in entries:
        for ref in entry.rules_refs:
            match = RULE_REF.match(ref)
            if match is None:
                errs.append(finding(
                    "G10.bad_rules_ref",
                    f"G10 decisions: {entry.id} rules reference {ref!r} is "
                    "not pinned ID@version",
                    owner=_fmt(entry.id),
                    expected="ID@version pin",
                    actual=ref,
                    repair="Pin rule references as ID@version "
                           "(cross-checked with the G8 registry)",
                ))
                continue
            if registry is None:
                continue
            entry_id, version = match.group(1), int(match.group(2))
            if entry_id not in registry:
                errs.append(finding(
                    "G10.bad_rules_ref",
                    f"G10 decisions: {entry.id} references unknown rule "
                    f"{entry_id}",
                    owner=_fmt(entry.id),
                    expected="registry id",
                    actual=ref,
                    repair="Reference a rule from the first-party registry",
                ))
            elif registry[entry_id] != version:
                errs.append(finding(
                    "G10.bad_rules_ref",
                    f"G10 decisions: {entry.id} pins {ref} but the registry "
                    f"version is {registry[entry_id]}",
                    owner=_fmt(entry.id),
                    expected=f"{entry_id}@{registry[entry_id]}",
                    actual=ref,
                    repair="Re-pin the rule reference to the registry "
                           "version",
                ))
    return errs


def _supersedes_checks(entries: list[DDEntry]) -> list[Finding]:
    errs: list[Finding] = []
    by_id = {entry.id: entry for entry in entries}
    superseded: dict[str, str] = {}
    for entry in entries:
        ref = entry.supersedes_ref
        if not ref:
            continue
        target = local_dd_id(ref)
        if target is None:
            errs.append(finding(
                "G10.supersedes_unknown",
                f"G10 decisions: {entry.id} supersedes {ref!r} which is "
                "not a DD reference",
                owner=_fmt(entry.id),
                expected="DD-#### (same run) or <run>/DD-####",
                actual=ref,
                repair="Point supersedes at the retired entry id",
            ))
            continue
        if is_cross_run_ref(ref):
            continue  # cross-run target resolution is out of scope here
        if target not in by_id:
            errs.append(finding(
                "G10.supersedes_unknown",
                f"G10 decisions: {entry.id} supersedes unknown entry "
                f"{target}",
                owner=_fmt(entry.id),
                expected=f"existing {target}",
                actual="unknown id",
                repair="Reference an entry recorded in this report",
            ))
            continue
        superseded[target] = entry.id
        target_status = by_id[target].status
        if target_status and target_status not in RETIRED_STATUSES:
            errs.append(finding(
                "G10.supersedes_target_active",
                f"G10 decisions: {entry.id} supersedes {target} but "
                f"{target} status is {target_status!r} (revise = new entry "
                "supersedes, old entry retires; history is never "
                "rewritten)",
                owner=_fmt(target),
                expected="status: invalidated|superseded",
                actual=target_status,
                repair=f"Retire {target} (invalidated/superseded) — do not "
                       "rewrite its recorded decision",
            ))
    # cycles
    graph = {
        entry.id: local_dd_id(entry.supersedes_ref)
        for entry in entries if entry.supersedes_ref
        and not is_cross_run_ref(entry.supersedes_ref)
        and local_dd_id(entry.supersedes_ref)
    }
    for start in graph:
        visited: set[str] = set()
        node = graph.get(start)
        while node is not None:
            if node == start:
                errs.append(finding(
                    "G10.supersedes_cycle",
                    f"G10 decisions: supersedes graph has a cycle through "
                    f"{start}",
                    owner=_fmt(start),
                    expected="acyclic supersedes chain",
                    actual="cycle",
                    repair="Break the cycle — revisions append, they never "
                           "loop",
                ))
                break
            if node in visited:
                break
            visited.add(node)
            node = graph.get(node)
    # retired entries need a superseder (no silent retirement)
    for entry in entries:
        if entry.status in RETIRED_STATUSES and entry.id not in superseded:
            errs.append(finding(
                "G10.retired_without_superseder",
                f"G10 decisions: {entry.id} is retired ({entry.status}) "
                "without a superseding entry — retirement only happens by "
                "revision",
                owner=_fmt(entry.id),
                expected="another entry supersedes it",
                actual="no superseder",
                repair="Record the revision entry that supersedes it, or "
                       "restore an active status",
            ))
    return errs


def _reentry_checks(
        entries: list[DDEntry],
        dd_targets: tuple[str, ...]) -> list[Finding]:
    """R3 re-entry: dd: challenges must end invalidated + E-tier revision."""
    errs: list[Finding] = []
    by_id = {entry.id: entry for entry in entries}
    for ref in dd_targets:
        target = local_dd_id(ref)
        if target is None:
            continue
        if is_cross_run_ref(ref):
            continue
        if target not in by_id:
            errs.append(finding(
                "G10.dd_ref_unknown",
                f"G10 decisions: finding dd: reference {ref!r} names no "
                "entry in this report",
                owner="point-back.md#findings",
                expected="existing DD entry",
                actual=ref,
                repair="Reference the challenged entry (same report or "
                       "<run>/DD-#### cross-run)",
            ))
            continue
        entry = by_id[target]
        if entry.status not in RETIRED_STATUSES:
            errs.append(finding(
                "G10.dd_challenge_unresolved",
                f"G10 decisions: dd: challenge on {target} is unresolved — "
                "the challenged entry must be invalidated and revised by "
                "a superseding entry",
                owner=_fmt(target),
                expected="status: invalidated + superseding revision",
                actual=f"status: {entry.status or 'unknown'}",
                repair="Revise via a new entry (supersedes) and retire the "
                       "challenged one",
            ))
    # revision of a challenged entry re-grades to explore + user confirm
    challenged = {
        local_dd_id(ref) for ref in dd_targets
        if local_dd_id(ref) and not is_cross_run_ref(ref)
    }
    for entry in entries:
        ref = entry.supersedes_ref
        target = local_dd_id(ref) if ref else None
        if not target or is_cross_run_ref(ref) or target not in challenged:
            continue
        if entry.tier != "explore":
            errs.append(finding(
                "G10.dd_revision_not_explore",
                f"G10 decisions: {entry.id} supersedes challenged {target} "
                f"as tier {entry.tier!r} — an R3 re-entry hits the "
                "upstream-route/re-entry criterion, so the revision "
                "re-grades to explore with user confirmation",
                owner=_fmt(entry.id),
                expected="tier: explore + user confirmation",
                actual=f"tier: {entry.tier or 'unknown'}",
                repair="Re-grade the revision to explore and record the "
                       "user confirmation",
            ))
    return errs


def _positive_dd_checks(pointback_text: str | None) -> list[Finding]:
    """``dd:`` on a positive (S0) finding is a shape error (issue #44).

    ``dd:`` is the R3 challenge channel; riding it on a positive
    observation reads as a challenge downstream. Fail closed with a
    precise error instead of silently ignoring the line.
    """
    if not pointback_text:
        return []
    errs: list[Finding] = []
    for index, refs in positive_dd_refs(pointback_text):
        errs.append(finding(
            "G10.dd_on_positive_finding",
            f"G10 decisions: positive finding {index} carries "
            f"dd: {', '.join(refs)} — dd: is the R3 challenge channel and "
            "never rides a positive observation",
            owner=f"point-back.md#finding.{index}",
            expected="dd: only on non-positive (S1-S3) findings",
            actual="dd: on severity S0",
            repair="Drop the dd: line and record the observation link as "
                   "prose (e.g. an evidence note line)",
        ))
    return errs


def _preview_link_checks(
        entries: list[DDEntry],
        preview_dir: Path | None) -> list[Finding]:
    """E-tier confirmations riding a transaction must link its decision_id."""
    if preview_dir is None:
        return []
    errs: list[Finding] = []
    for entry in entries:
        link = entry.preview_link
        if link is None:
            continue
        round_n, decision_id = link
        confirm_path = preview_dir / f"confirm-round-{round_n}.json"
        if not confirm_path.is_file():
            errs.append(finding(
                "G10.preview_link_broken",
                f"G10 decisions: {entry.id} confirmation rides "
                f"preview-round-{round_n} but {confirm_path.name} is "
                "missing",
                owner=_fmt(entry.id),
                expected=f"preview/confirm-round-{round_n}.json",
                actual="missing",
                repair="Re-run the preview transaction round or fix the "
                       "confirmation record",
            ))
            continue
        try:
            data = json.loads(confirm_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errs.append(finding(
                "G10.preview_link_broken",
                f"G10 decisions: {entry.id} links {confirm_path.name} "
                f"which is unreadable: {exc}",
                owner=_fmt(entry.id),
                expected="valid confirm-round JSON",
                actual=str(exc),
                repair="Fix the confirm record (G5 owns its integrity)",
            ))
            continue
        if not isinstance(data, dict) or data.get("decision_id") != decision_id:
            actual = (
                data.get("decision_id") if isinstance(data, dict) else None
            )
            errs.append(finding(
                "G10.preview_link_broken",
                f"G10 decisions: {entry.id} links decision_id {decision_id} "
                f"but {confirm_path.name} carries {actual!r} — "
                "confirmation provenance must match the transaction",
                owner=_fmt(entry.id),
                expected=f"decision_id {decision_id}",
                actual=repr(actual),
                repair="Link the entry to the transaction that confirmed "
                       "it (via: preview-round-<n> decision_id:<id>)",
            ))
    return errs


def _stale_checks(
        entries: list[DDEntry],
        baseline_state: dict | None) -> list[Finding]:
    """Baseline-drift stale review: three exits, keep cites the new sha."""
    errs: list[Finding] = []
    current_sha = ""
    if isinstance(baseline_state, dict):
        binding = baseline_state.get("baseline")
        if baseline_state.get("status") == "ready" and isinstance(binding, dict):
            sha = binding.get("sha256")
            if isinstance(sha, str):
                current_sha = sha.lower()
    by_id = {entry.id: entry for entry in entries}
    for entry in entries:
        review = entry.stale_review
        if entry.stale and not review:
            errs.append(finding(
                "G10.stale_no_review",
                f"G10 decisions: {entry.id} is marked stale without the "
                "three-exit review record (keep | revise | escalate)",
                owner=_fmt(entry.id),
                expected="stale_review: {exit, note}",
                actual="missing",
                repair="Re-run the constraint comparison under the new "
                       "baseline and record the exit",
            ))
        if review:
            exit_value = review.get("exit", "")
            note = review.get("note", "").strip()
            if exit_value not in STALE_EXITS:
                errs.append(finding(
                    "G10.stale_bad_exit",
                    f"G10 decisions: {entry.id} stale_review exit "
                    f"{exit_value!r} not in keep|revise|escalate",
                    owner=_fmt(entry.id),
                    expected="keep|revise|escalate",
                    actual=exit_value,
                    repair="Record one of the three review exits",
                ))
            if exit_value == "keep":
                match = SHA256.search(note)
                if match is None:
                    errs.append(finding(
                        "G10.stale_keep_missing_sha",
                        f"G10 decisions: {entry.id} stale review keeps the "
                        "decision without citing the new baseline sha256 "
                        "(the review line re-binds the reference)",
                        owner=_fmt(entry.id),
                        expected="new sha256 in the review note",
                        actual="missing",
                        repair="Record the review line with the re-verified "
                               "sha256 to clear the stale mark",
                    ))
                elif current_sha and match.group(1).lower() != current_sha:
                    errs.append(finding(
                        "G10.stale_keep_missing_sha",
                        f"G10 decisions: {entry.id} stale review cites "
                        f"sha256 {match.group(1)[:12]}… but the bound "
                        f"baseline is {current_sha[:12]}…",
                        owner=_fmt(entry.id),
                        expected=f"current binding {current_sha[:12]}…",
                        actual=match.group(1)[:24] + "…",
                        repair="Cite the re-verified binding sha or re-run "
                               "design-baseline verify",
                    ))
            if exit_value == "revise":
                has_superseder = any(
                    other.supersedes_ref and
                    local_dd_id(other.supersedes_ref) == entry.id
                    for other in entries
                )
                if not has_superseder:
                    errs.append(finding(
                        "G10.stale_revise_no_superseder",
                        f"G10 decisions: {entry.id} stale review chose "
                        "revise but no entry supersedes it",
                        owner=_fmt(entry.id),
                        expected="a superseding revision entry",
                        actual="missing",
                        repair="Record the revision entry (supersedes this "
                               "one) or pick another exit",
                    ))
            if exit_value == "escalate" and not note:
                errs.append(finding(
                    "G10.stale_no_review",
                    f"G10 decisions: {entry.id} stale review escalates "
                    "without a note naming what returned to direction level",
                    owner=_fmt(entry.id),
                    expected="escalation note",
                    actual="missing",
                    repair="Record why the drift returns the question to "
                           "direction level (user decision)",
                ))
        # drift trigger: an entry pinned to a different sha than the bound
        # baseline must carry the stale mark (design-baseline verify owns
        # detection; G10 owns the record face).
        if (
            current_sha
            and entry.baseline_sha
            and entry.baseline_sha != current_sha
            and not entry.stale
        ):
            errs.append(finding(
                "G10.stale_unmarked",
                f"G10 decisions: {entry.id} pins baseline sha256 "
                f"{entry.baseline_sha[:12]}… but the verified binding is "
                f"{current_sha[:12]}… — drift-detected entries must be "
                "marked stale with the three-exit review",
                owner=_fmt(entry.id),
                expected="stale: <reason> + stale_review",
                actual="unmarked drifted entry",
                repair="Mark the entry stale and record the review exit "
                       "(keep/revise/escalate)",
            ))
    return errs


def _signal_checks(
        entries: list[DDEntry],
        signals,
        run_profile_tier: str | None) -> list[Finding]:
    """Machine-judgeable trigger-criteria cross-checks."""
    errs: list[Finding] = []
    if run_profile_tier == "P1" and entries:
        errs.append(finding(
            "G10.p1_decision_entries",
            "G10 decisions: run-profile tier is P1 (point-fix) but the "
            "decision report carries DD entries — any substantive choice "
            "is an upgrade signal (E-class: re-grade the run)",
            owner="decision-report.md",
            expected="no DD entries on P1",
            actual=f"{len(entries)} entries",
            repair="Upgrade the run profile (P2/P3) or remove the decision "
                   "entries from the point-fix scope",
        ))
    has_explore = any(entry.tier == "explore" for entry in entries)
    if not has_explore:
        if signals.t3_questions:
            errs.append(finding(
                "G10.t3_route_needs_explore",
                "G10 decisions: shaping routed T3 visual-direction "
                "question(s) to this decision stage but no explore-tier "
                "entry records them (upstream routes are always "
                "direction-level)",
                owner="decision-report.md",
                expected=">=1 tier: explore entry",
                actual="none",
                repair="Record the routed direction as an E-tier entry "
                       "with user confirmation",
            ))
        if signals.baseline_changed:
            errs.append(finding(
                "G10.baseline_change_needs_explore",
                "G10 decisions: report declares baseline-changes != none "
                "(baseline-conflict criterion) but no explore-tier entry "
                "records the direction decision behind the change",
                owner="decision-report.md",
                expected=">=1 tier: explore entry",
                actual="none",
                repair="Record the baseline change decision as an E-tier "
                       "entry (user confirmed, design-baseline approved)",
            ))
    return errs


def check_g10(
    report_text: str,
    *,
    report_path: Path | None = None,
    preview_dir: Path | None = None,
    registry_text: str | None = None,
    shaping_events: list[dict] | None = None,
    pointback_text: str | None = None,
    baseline_state: dict | None = None,
    run_profile_tier: str | None = None) -> list[Finding]:
    """Return G10 findings for a decision report (empty = pass/not fired)."""
    entries = parse_dd_entries(report_text)
    if not entries:
        return []
    errs: list[Finding] = []
    # headings that look like DD entries but fail the id shape are silently
    # ignorable by the parser — surface them so renames cannot hide entries
    for heading_id in DD_HEADING.findall(report_text):
        if not DD_ID.match(heading_id):
            errs.append(finding(
                "G10.bad_id",
                f"G10 decisions: entry heading {heading_id!r} fails "
                "^DD-[0-9]{{4}}$",
                owner="decision-report.md",
                expected="## DD-#### — <question>",
                actual=heading_id,
                repair="Zero-pad the entry id (DD-0001 style)",
            ))
    errs += _entry_checks(entries)
    errs += _rules_checks(entries, registry_text)
    errs += _supersedes_checks(entries)
    signals = collect_e_signals(
        entries,
        shaping_events=shaping_events,
        pointback_text=pointback_text,
        report_text=report_text,
    )
    errs += _reentry_checks(entries, signals.dd_targets)
    errs += _positive_dd_checks(pointback_text)
    errs += _preview_link_checks(entries, preview_dir)
    errs += _stale_checks(entries, baseline_state)
    errs += _signal_checks(entries, signals, run_profile_tier)
    return errs


def main(argv: list[str]) -> int:
    import sys

    if len(argv) != 2:
        print("Usage: g10_design_decisions.py <decision-report.md>",
              file=sys.stderr)
        return 2
    path = Path(argv[1])
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        print(f"G10 INVALID: cannot read {path}: {exc}", file=sys.stderr)
        return 2
    preview_dir = path.parent / "preview"
    findings = check_g10(
        text,
        report_path=path,
        preview_dir=preview_dir if preview_dir.is_dir() else None,
        pointback_text=_sibling_text(path.parent / "point-back.md"),
    )
    if not findings:
        print("G10 OK: design-decision entries satisfy the gate")
        return 0
    print("G10 INVALID:")
    for item in findings:
        print(f"  FAIL  {item.message}")
    return 1


def _sibling_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


if __name__ == "__main__":
    import sys

    sys.exit(main(sys.argv))
