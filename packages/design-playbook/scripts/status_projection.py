#!/usr/bin/env python3
"""Run-status projection library: derive status facts from run artifacts.

Owns the typed next-action model (Closed Snapshot v1), the stage / vNext /
verdict inspectors, and the forward-action resolver. ``run_status.py`` is the
CLI seam over this library: it renders these projections (text / JSON) and
keeps the ``scripts/run_status.py`` path contract used by subprocess callers.

Does **not** create a second run-state SSOT. Reads only files agents already
write under a run root (via RunFacts); Fill surfaces may live outside the run
root — when ``plan.md`` registers them with ``fill:`` field lines, the fill
stage is also judged on those declared paths (issue #44; the stage registry
itself is unchanged, ADR-0021).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# One import seam (ADR-0022): package root on sys.path once, then absolute
# design_playbook.* imports below. No per-runtime sys.path adapters.
_PKG_ROOT = Path(__file__).resolve().parents[1]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

# Preview integrity lives with the bundled Preview runtime.
from design_playbook.mcp.preview.integrity import PreviewSnapshot, inspect_preview  # noqa: E402

# Stage registry and shared artifact names live in the packaged scripts dir
# (ADR-0021): STAGES mirrors skills/design-playbook/SKILL.md Steps; the
# artifact-name constants are shared with validate_run.py. Verdict syntax
# facts are parsed once in verdict_syntax (ADR-0025); run status projects
# its status decision from the shared canonical value.
from design_playbook.scripts.stages import STAGES, STAGES_BY_KEY  # noqa: E402
from design_playbook.scripts.run_facts import RunFacts, capture_run_facts  # noqa: E402
from design_playbook.scripts.shaping_log import queue_state  # noqa: E402

# Audit-preferences forgery boundary (ADR-0033 D12, issue #67): a skeleton
# point-back (audited: false) projects "not audited" — the marker facts
# come from the single audit_preferences module; status narration never
# invites the user to confirm a verdict the audit never earned.
from design_playbook.scripts.audit_preferences import (  # noqa: E402
    AuditMarker,
    parse_audit_marker,
)

# vNext S4 re-entry narration (loop-prototype 7.1): repair rounds, route
# hit counts, dd supersedes / stale reviews, derived escalation signals,
# and the close_reason terminal narration, all read from artifacts the
# gates already consume (additive; plain runs report empty faces).
from design_playbook.scripts.dd_entries import dd_refs_in_pointback  # noqa: E402
from design_playbook.scripts.escalation_signals import (  # noqa: E402
    EscalationSignal,
    collect_signals,
    recorded_regrades,
    route_hits,
)
from design_playbook.scripts.repair_rounds import (  # noqa: E402
    parse_close_reason,
    parse_round_facts,
)


class NextActionKind(str, Enum):
    """Closed Snapshot v1 kinds for owner-emitted next actions.

    Only kinds an existing owner branch actually emits are members;
    ``agent-command`` and ``source-review`` stay absent until an owner
    emits them.
    """

    STOP = "stop"
    CONTINUE = "continue"
    HUMAN_DECISION = "human-decision"


class NextActionActor(str, Enum):
    """Closed Snapshot v1 actor for one owner-emitted next action."""

    RUN_OPERATOR = "run-operator"
    AGENT = "agent"


@dataclass(frozen=True)
class NextActionOwner:
    """Actor and optional semantic role responsible for an action."""

    actor: NextActionActor
    role: str | None


@dataclass(frozen=True)
class NextAction:
    """Structured owner result; narration is never parsed to construct it."""

    action_id: str
    kind: NextActionKind
    label: str
    owner: NextActionOwner
    copyable_agent_command: str | None


@dataclass(frozen=True)
class NextActionProjection:
    """One canonical action and only owner-sanctioned alternatives."""

    primary: NextAction
    alternatives: tuple[NextAction, ...]


def _next_action(
    action_id: str,
    kind: NextActionKind,
    actor: NextActionActor,
    label: str,
) -> NextAction:
    """Build one owner-emitted action.

    ``copyable_agent_command`` stays ``None`` until an existing owner
    emits one exact command; converting narration is forbidden
    (Snapshot v1 section 7.5).
    """
    return NextAction(
        action_id=action_id,
        kind=kind,
        label=label,
        owner=NextActionOwner(actor=actor, role=None),
        copyable_agent_command=None,
    )


def _action_projection(action: NextAction) -> NextActionProjection:
    """Wrap one canonical action; no owner sanctions alternatives yet."""
    return NextActionProjection(primary=action, alternatives=())


@dataclass(frozen=True)
class VnextNarration:
    """Additive vNext narration facts (run-profile block + shaping session)."""

    tier: str | None
    confirmed_by: str | None
    skipped: tuple[tuple[str, str], ...]
    upgrades: tuple[str, ...]
    shaping: str | None
    six_block: bool = False
    invalidated: bool = False
    repair: "RepairNarration | None" = None


@dataclass(frozen=True)
class RepairNarration:
    """S4 re-entry facts derived from the point-back / plan / DD report.

    W-event presentation (loop-prototype 7.1): route hit counts stand for
    W1-W7 (R4 / R5 / R2-line / R2-structural / R1 x2 / R3), dd supersedes
    and stale reviews for W7-W8, upgrade events for W10, and the
    close_reason narration carries the terminal state (pass |
    escalated-stop | aborted — a narration state, never a verdict value).
    E5 (G12 contract diff) needs the project contract and stays gate-side.
    """

    rounds: int = 0
    routes: tuple[tuple[str, int], ...] = ()
    dd_supersedes: int = 0
    stale_reviews: int = 0
    close_reason: str | None = None
    signals: tuple[EscalationSignal, ...] = ()

    @property
    def wait_user(self) -> bool:
        """An escalated stop waits on the user disposition (three-way)."""
        return self.close_reason == "escalated-stop"

    @property
    def empty(self) -> bool:
        return not (self.rounds or self.routes or self.signals
                    or self.close_reason or self.dd_supersedes
                    or self.stale_reviews)


def _repair_narration(
        pointback_text: str,
        upgrades: tuple[str, ...],
        decision_entries: tuple,
) -> RepairNarration:
    """Derive the S4 re-entry faces from artifacts in the run root."""
    rounds = parse_round_facts(pointback_text).max_rounds
    routes = tuple(sorted(route_hits(pointback_text).items()))
    dd_supersedes = len(dd_refs_in_pointback(pointback_text))
    stale_reviews = sum(1 for entry in decision_entries if entry.stale_review)
    dd_explore = any(entry.tier == "explore" for entry in decision_entries)
    signals = list(collect_signals(pointback_text, dd_explore=dd_explore))
    signals.extend(recorded_regrades(upgrades))
    return RepairNarration(
        rounds=rounds,
        routes=routes,
        dd_supersedes=dd_supersedes,
        stale_reviews=stale_reviews,
        close_reason=parse_close_reason(pointback_text),
        signals=tuple(signals),
    )


def inspect_vnext(
        run_root: Path,
        run_facts: RunFacts | None = None,
) -> VnextNarration:
    """Project vNext facts from one immutable run snapshot."""
    facts = run_facts or capture_run_facts(run_root=run_root)
    tier = None
    confirmed_by = None
    skipped: tuple[tuple[str, str], ...] = ()
    upgrades: tuple[str, ...] = ()
    profile = facts.run_profile
    if profile is not None:
        tier = profile.tier or None
        confirmed_by = profile.confirmed_by or None
        skipped = profile.skipped
        upgrades = profile.upgrades
    shaping: str | None = None
    if facts.shaping_error is not None:
        shaping = "unreadable"
    elif facts.shaping_events is not None:
        shaping = queue_state(list(facts.shaping_events))
    pb_text = facts.pointback_text
    six_block = "## Coverage statement" in pb_text
    invalidated = "\ninvalidated:" in pb_text or pb_text.startswith(
        "invalidated:")
    repair = None
    if pb_text:
        repair = _repair_narration(
            pb_text, upgrades, facts.decision_entries
        )
    return VnextNarration(
        tier=tier, confirmed_by=confirmed_by, skipped=skipped,
        upgrades=upgrades, shaping=shaping,
        six_block=six_block, invalidated=invalidated,
        repair=repair,
    )


@dataclass(frozen=True)
class StageState:
    key: str
    skill: str
    present: bool
    evidence: list[str]


# Plan fill declarations are captured by RunFacts; status only projects them.


def inspect_run(
    run_root: Path, preview_snapshot: PreviewSnapshot | None = None,
    run_facts: RunFacts | None = None,
) -> list[StageState]:
    facts = run_facts or capture_run_facts(run_root=run_root)
    snapshot = preview_snapshot or facts.preview or inspect_preview(run_root / "preview")
    plan_fills = list(facts.plan_fill_artifacts)
    states: list[StageState] = []
    for stage in STAGES:
        if stage.key == "preview":
            found = [f"preview/{source}" for source in snapshot.occurrence_sources]
        elif stage.key == "fill":
            found = [marker for marker in stage.markers if marker in facts.existing_paths]
            found += [declared for declared in plan_fills]
        else:
            found = [marker for marker in stage.markers if marker in facts.existing_paths]
        states.append(StageState(
            key=stage.key,
            skill=stage.skill,
            present=bool(found),
            evidence=found,
        ))
    return states


def discover_runs(scratch: Path) -> list[Path]:
    if not scratch.is_dir():
        return []
    runs = [p for p in scratch.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))]
    runs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return runs


def _audit_disposition(
    pointback_text: str, *, marker: AuditMarker | None = None
) -> str:
    """Classify marker facts without treating ambiguity as legacy absence.

    ``marker`` lets a caller that already parsed the text (render) reuse the
    facts instead of parsing the same point-back twice.
    """
    facts = marker if marker is not None else parse_audit_marker(pointback_text)
    if not facts.present:
        return "legacy"
    if facts.audited is True:
        return "audited"
    if facts.audited is False:
        return "unaudited"
    return "ambiguous"


def verdict_of(run_root: Path, run_facts: RunFacts | None = None) -> str | None:
    facts = run_facts or capture_run_facts(run_root=run_root)
    if not facts.pointback_text:
        return None
    # Skeleton and malformed marker reports cannot project an earned verdict.
    if _audit_disposition(facts.pointback_text) in {"unaudited", "ambiguous"}:
        return None
    # ADR-0025 sanctioned correction: a canonical Verdict is exposed only
    # when exactly one valid Verdict exists. Missing, malformed, ambiguous,
    # or repeated Verdict text yields no canonical value, so run status can
    # never report ``Run complete (Pass)`` from anything other than one
    # uniquely valid Pass. The previous permissive line/regex scan accepted
    # Verdict text the G3 gate rejects; both consumers now share one parse.
    verdict = facts.verdict
    if verdict.canonical == "pass":
        return "Pass"
    if verdict.canonical == "recirculate":
        return "Recirculate"
    return None


def _baseline_next_action(facts: RunFacts) -> str | None:
    """Return a blocking resume hint when the DesignBaseline gate is incomplete.

    Reads only ``design-baseline/state.json`` (schema ``design-baseline/v1``),
    which is the sole stage marker (ADR-0012). Mirrors the public statuses
    produced by ``prepare`` / ``confirm`` / ``verify``:
    ``ready`` (bound), ``waived`` (explicit reason), ``needs_confirmation``,
    or ``ambiguous``. This is **status narration only** — it does not re-hash
    sources or re-verify the binding. ``verify()`` at Fill time is the
    forge-resistant gate.
    """
    if facts.baseline_state_error is not None:
        return "Design-baseline state.json is unreadable — re-run design-baseline prepare before Fill."
    state = facts.baseline_state
    if state is None:
        return ("Design-baseline state.json vanished mid-read — "
                "re-run design-baseline prepare before Fill.")
    if not isinstance(state, dict):
        return "Design-baseline state.json is not an object — re-run design-baseline prepare before Fill."

    status = state.get("status")
    decision = state.get("decision") if isinstance(state.get("decision"), dict) else {}

    if status == "needs_confirmation":
        return ("Design-baseline draft needs confirmation — "
                "accept/waive via design-baseline confirm before Fill.")
    if status == "ambiguous":
        return ("Design-baseline candidates are ambiguous — "
                "resolve DESIGN.md vs .stitch/DESIGN.md before Fill.")
    if status == "waived":
        waiver_reason = decision.get("reason")
        if not (isinstance(waiver_reason, str) and waiver_reason.strip()):
            return ("Design-baseline waiver is missing a non-empty reason — "
                    "record an explicit waiver reason before Fill.")
        return None
    if status == "ready":
        return None
    return ("Design-baseline status is not ready/waived — "
            "complete prepare/confirm (or re-run prepare) before Fill.")


def _preview_next_action(snapshot: PreviewSnapshot) -> NextAction:
    """Typed action for the Preview branch; narration renders its label.

    Preview presence and confirm validity come from the one integrity
    snapshot; this never re-derives G5 facts. Human-decision kinds are
    the HITL branches (confirm/revise belongs to the run operator);
    re-running a preview round is an agent continuation.
    """
    confirm = snapshot.canonical_current_confirm
    if confirm is None:
        invalid = next(
            (
                fact
                for fact in snapshot.facts
                if fact.code == "invalid_confirm_record" and fact.path is not None
            ),
            None,
        )
        if invalid is not None:
            return _next_action(
                "action.recover-preview-confirm",
                NextActionKind.CONTINUE,
                NextActionActor.AGENT,
                f"Preview confirm unreadable ({invalid.path.name}); "
                "re-run preview*.",
            )
        return _next_action(
            "action.finish-preview-hitl",
            NextActionKind.HUMAN_DECISION,
            NextActionActor.RUN_OPERATOR,
            "Preview artifacts exist without a confirm for the latest "
            "round — finish preview* HITL (G5) before fill.",
        )
    payload = confirm.data
    if isinstance(payload, dict) and payload.get("aborted") is True:
        return _next_action(
            "action.rerun-preview-after-abort",
            NextActionKind.CONTINUE,
            NextActionActor.AGENT,
            f"Preview ABORTED in {confirm.path.name} — must not proceed to "
            f"fill; re-run preview* from the current round.",
        )
    # Status narrates the transaction outcome only. Prototype facts remain
    # G5's fail-closed concern; run_status does not become a second gate.
    if confirm.valid:
        return _next_action(
            "action.resume-after-preview",
            NextActionKind.CONTINUE,
            NextActionActor.AGENT,
            "Preview confirmed and floor passed — resume at fill.",
        )
    if isinstance(payload, dict) and payload.get("confirmed") is True:
        reason = payload.get("floor_failure") or "floor_pass is not true"
        return _next_action(
            "action.rerun-preview-after-floor-failure",
            NextActionKind.HUMAN_DECISION,
            NextActionActor.RUN_OPERATOR,
            f"Preview confirmed in {confirm.path.name} but feedback floor "
            f"failed ({reason}) — must not proceed to fill; re-run "
            f"preview* HITL.",
        )
    return _next_action(
        "action.complete-preview-decision",
        NextActionKind.HUMAN_DECISION,
        NextActionActor.RUN_OPERATOR,
        "Preview open without decision — complete preview* confirm/revise.",
    )


def next_action(
    states: list[StageState],
    run_root: Path,
    preview_snapshot: PreviewSnapshot | None = None,
    run_facts: RunFacts | None = None,
) -> str:
    """Legacy narration seam: render the typed projection's primary label.

    The typed resolver (:func:`project_next_action`) owns every forward
    branch; this function never re-derives owner branches, and no
    consumer may parse the narration back into domain facts or commands.
    """
    return project_next_action(
        states, run_root, preview_snapshot, run_facts,
    ).primary.label


def project_next_action(
    states: list[StageState],
    run_root: Path,
    preview_snapshot: PreviewSnapshot | None = None,
    run_facts: RunFacts | None = None,
) -> NextActionProjection:
    """Project the canonical structured action from owner facts.

    Single forward branch source for every existing owner branch of the
    legacy narration, in owner precedence order: the design-baseline
    gate, the accept ladder (audit disposition, then the escalated-stop
    waiting state ahead of any verdict-derived hint, then the verdict),
    the empty run, the stage-resume loop, and the generic latest-stage
    fallback. Narration renders ``primary.label``; it never re-derives
    branches, and no consumer may parse the narration back into domain
    facts or commands.
    """
    facts = run_facts or capture_run_facts(run_root=run_root)
    snapshot = preview_snapshot or facts.preview or inspect_preview(run_root / "preview")
    present = {state.key for state in states if state.present}
    if "baseline" in present:
        blocked = _baseline_next_action(facts)
        if blocked is not None:
            # The design-baseline gate is a human confirm/waive owner
            # (ADR-0012): every blocked sub-state resolves to the same
            # typed operator action, with the owner's blocker as label.
            return _action_projection(_next_action(
                "action.resolve-design-baseline",
                NextActionKind.HUMAN_DECISION,
                NextActionActor.RUN_OPERATOR,
                blocked,
            ))
    if "accept" in present:
        audit_disposition = _audit_disposition(facts.pointback_text)
        if audit_disposition == "unaudited":
            return _action_projection(_next_action(
                "action.audit-unaudited-point-back",
                NextActionKind.CONTINUE,
                NextActionActor.AGENT,
                "point-back.md is the unaudited skeleton "
                "(audited: false) — not audited; run the ui-evaluator "
                "audit to earn a real verdict.",
            ))
        if audit_disposition == "ambiguous":
            return _action_projection(_next_action(
                "action.repair-audit-marker",
                NextActionKind.CONTINUE,
                NextActionActor.AGENT,
                "point-back.md has duplicate or malformed audited markers "
                "— fix the marker and run ui-evaluator before trusting "
                "its verdict.",
            ))
        verdict = verdict_of(run_root, facts)
        # vNext S4: an escalated stop is a waiting state — repairing again
        # is exactly wrong; the three-way user disposition comes before any
        # verdict-derived hint.
        if parse_close_reason(facts.pointback_text) == "escalated-stop":
            return _action_projection(_next_action(
                "action.disposition-escalated-stop",
                NextActionKind.HUMAN_DECISION,
                NextActionActor.RUN_OPERATOR,
                "Escalated stop — the same blocking finding survived two "
                "repair rounds without new evidence; user disposition "
                "required (revise the owning declaration / accept the "
                "risk and record / keep suspended).",
            ))
        # verdict_of returns "Pass" only from one uniquely valid Pass
        # (ADR-0025); exact equality avoids any string-prefix inference
        # that could complete a run from malformed or repeated Verdict
        # text.
        if verdict == "Pass":
            return _action_projection(_next_action(
                "action.stop-after-pass",
                NextActionKind.STOP,
                NextActionActor.RUN_OPERATOR,
                "Run complete (Pass). Ship or start a new run.",
            ))
        if verdict == "Recirculate":
            return _action_projection(_next_action(
                "action.repair-after-recirculate",
                NextActionKind.CONTINUE,
                NextActionActor.AGENT,
                "Verdict is Recirculate — repair from point-back "
                "findings, then re-run ui-evaluator.",
            ))
        return _action_projection(_next_action(
            "action.confirm-verdict",
            NextActionKind.CONTINUE,
            NextActionActor.AGENT,
            "point-back.md present — confirm ## Verdict, then stop or "
            "recirculate.",
        ))
    if not present:
        return _action_projection(_next_action(
            "action.start-run",
            NextActionKind.CONTINUE,
            NextActionActor.RUN_OPERATOR,
            "No run artifacts — start with "
            "/design-playbook:design-io <ask> (design-baseline?, "
            "reference-intake?, or ux-spec).",
        ))
    for state in reversed(states):
        if not state.present or state.key == "accept":
            continue
        if state.key == "preview":
            return _action_projection(_preview_next_action(snapshot))
        stage = STAGES_BY_KEY.get(state.key)
        if stage is not None and stage.resume_action is not None:
            return _action_projection(_next_action(
                f"action.resume-after-{state.key}",
                NextActionKind.CONTINUE,
                NextActionActor.AGENT,
                stage.resume_action,
            ))
    last = [state for state in states if state.present][-1]
    return _action_projection(_next_action(
        "action.continue-orchestrator",
        NextActionKind.CONTINUE,
        NextActionActor.AGENT,
        f"Latest artifact stage: {last.key} ({last.skill}). "
        "Continue the orchestrator sequence from there.",
    ))
