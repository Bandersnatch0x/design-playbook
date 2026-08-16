#!/usr/bin/env python3
"""Derive Design I/O run status / resume hints from existing artifacts.

Does **not** create a second run-state SSOT. Reads only files agents already
write under a run root (default: discover newest ``.scratch/*/``). Fill
surfaces may live outside the run root: when ``plan.md`` registers them with
``fill:`` field lines, the fill stage is also judged on those declared paths
(issue #44; the stage registry itself is unchanged).
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

# Package-local scripts directory (works for installed plugin and monorepo
# copy). Preview integrity lives with the bundled Preview runtime.
_SCRIPTS_DIR = Path(__file__).resolve().parent

# One import seam (ADR-0022): package root on sys.path once, then absolute
# design_playbook.* imports below. No per-runtime sys.path adapters.
_PKG_ROOT = _SCRIPTS_DIR.parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))
from design_playbook.mcp.preview.integrity import PreviewSnapshot, inspect_preview  # noqa: E402

# Repo/package root for default --scratch discovery only.
ROOT = _SCRIPTS_DIR.parent
if (ROOT / "packages" / "design-playbook").is_dir():
    pass  # monorepo layout: package under packages/design-playbook
elif ROOT.name == "design-playbook":
    pass  # package root when run from packages/design-playbook/scripts
else:
    ROOT = Path.cwd()

# Stage registry and shared artifact names live in the packaged scripts dir
# (ADR-0021): STAGES mirrors skills/design-playbook/SKILL.md Steps; the
# artifact-name constants are shared with validate_run.py. Verdict syntax
# facts are parsed once in verdict_syntax (ADR-0025); run status projects
# its status decision from the shared canonical value.
from design_playbook.scripts.stages import STAGES, STAGES_BY_KEY  # noqa: E402
from design_playbook.scripts.run_facts import RunFacts, capture_run_facts  # noqa: E402
from design_playbook.scripts.shaping_log import queue_state  # noqa: E402

# vNext S4 re-entry narration (loop-prototype 7.1): repair rounds, route
# hit counts, dd supersedes / stale reviews, derived escalation signals,
# and the close_reason terminal narration, all read from artifacts the
# gates already consume (additive; plain runs report empty faces).
from design_playbook.scripts.dd_entries import dd_refs_in_pointback  # noqa: E402
from design_playbook.scripts.escalation_signals import (  # noqa: E402
    EscalationSignal,
    collect_signals,
    effective_tier,
    recorded_regrades,
    route_hits,
)
from design_playbook.scripts.repair_rounds import (  # noqa: E402
    parse_close_reason,
    parse_round_facts,
)


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


def verdict_of(run_root: Path, run_facts: RunFacts | None = None) -> str | None:
    facts = run_facts or capture_run_facts(run_root=run_root)
    if not facts.pointback_text:
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


def _preview_next_action(snapshot: PreviewSnapshot) -> str:
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
            return f"Preview confirm unreadable ({invalid.path.name}); re-run preview*."
        return ("Preview artifacts exist without a confirm for the latest "
                "round — finish preview* HITL (G5) before fill.")
    payload = confirm.data
    if isinstance(payload, dict) and payload.get("aborted") is True:
        return (f"Preview ABORTED in {confirm.path.name} — must not proceed to "
                f"fill; re-run preview* from the current round.")
    # Status narrates the transaction outcome only. Prototype facts remain
    # G5's fail-closed concern; run_status does not become a second gate.
    if confirm.valid:
        return "Preview confirmed and floor passed — resume at fill."
    if isinstance(payload, dict) and payload.get("confirmed") is True:
        reason = payload.get("floor_failure") or "floor_pass is not true"
        return (f"Preview confirmed in {confirm.path.name} but feedback floor "
                f"failed ({reason}) — must not proceed to fill; re-run "
                f"preview* HITL.")
    return "Preview open without decision — complete preview* confirm/revise."


def next_action(
    states: list[StageState],
    run_root: Path,
    preview_snapshot: PreviewSnapshot | None = None,
    run_facts: RunFacts | None = None,
) -> str:
    facts = run_facts or capture_run_facts(run_root=run_root)
    snapshot = preview_snapshot or facts.preview or inspect_preview(run_root / "preview")
    present = {state.key: state for state in states if state.present}
    if "baseline" in present:
        blocked = _baseline_next_action(facts)
        if blocked is not None:
            return blocked
    if "accept" in present:
        verdict = verdict_of(run_root, facts)
        # vNext S4: an escalated stop is a waiting state — repairing again
        # is exactly wrong; narrate the two-round budget and the three-way
        # user disposition before any verdict-derived hint.
        if parse_close_reason(facts.pointback_text) == "escalated-stop":
            return ("Escalated stop — the same blocking finding survived two "
                    "repair rounds without new evidence; user disposition "
                    "required (revise the owning declaration / accept the "
                    "risk and record / keep suspended).")
        # verdict_of returns "Pass" only from one uniquely valid Pass
        # (ADR-0025); exact equality avoids any string-prefix inference that
        # could complete a run from malformed or repeated Verdict text.
        if verdict == "Pass":
            return "Run complete (Pass). Ship or start a new run."
        if verdict == "Recirculate":
            return "Verdict is Recirculate — repair from point-back findings, then re-run ui-evaluator."
        return "point-back.md present — confirm ## Verdict, then stop or recirculate."
    if not present:
        return "No run artifacts — start with /design-playbook:design-io <ask> (design-baseline?, reference-intake?, or ux-spec)."

    for state in reversed(states):
        if not state.present or state.key == "accept":
            continue
        if state.key == "preview":
            return _preview_next_action(snapshot)
        stage = STAGES_BY_KEY.get(state.key)
        if stage is not None and stage.resume_action is not None:
            return stage.resume_action

    last = [state for state in states if state.present][-1]
    return f"Latest artifact stage: {last.key} ({last.skill}). Continue the orchestrator sequence from there."


def render(run_root: Path, *, as_json: bool) -> int:
    if not run_root.is_dir():
        print(f"RUN STATUS ERROR: not a directory: {run_root}", file=sys.stderr)
        return 2
    facts = capture_run_facts(run_root=run_root)
    read_error = next(
        (error for error in facts.read_errors if error.code != "missing"),
        None,
    )
    if read_error is not None:
        print(
            f"RUN STATUS ERROR: cannot read {read_error.path.name}: "
            f"{read_error.message}",
            file=sys.stderr,
        )
        return 2
    snapshot = facts.preview or inspect_preview(run_root / "preview")
    states = inspect_run(run_root, snapshot, facts)
    action = next_action(states, run_root, snapshot, facts)
    vnext = inspect_vnext(run_root, facts)
    payload = {
        "run_root": str(run_root),
        "stages": [
            {
                "key": s.key,
                "skill": s.skill,
                "present": s.present,
                "evidence": s.evidence,
            }
            for s in states
        ],
        "next": action,
        "verdict": verdict_of(run_root, facts),
        "run_profile": {
            "tier": vnext.tier,
            "effective_tier": (
                effective_tier(vnext.tier, vnext.upgrades)
                if vnext.tier is not None else None),
            "confirmed_by": vnext.confirmed_by,
            "skipped": [
                {"step": name, "reason": reason}
                for name, reason in vnext.skipped
            ],
            "upgrades": list(vnext.upgrades),
        } if vnext.tier is not None else None,
        "shaping": vnext.shaping,
        "six_block_report": vnext.six_block,
        "invalidated_evidence": vnext.invalidated,
        "repair": {
            "rounds": vnext.repair.rounds,
            "routes": {route: count for route, count in vnext.repair.routes},
            "dd_supersedes": vnext.repair.dd_supersedes,
            "stale_reviews": vnext.repair.stale_reviews,
            "close_reason": vnext.repair.close_reason,
            "wait_user": vnext.repair.wait_user,
            "signals": [
                {
                    "signal": signal.signal,
                    "required_tier": signal.required_tier,
                    "detail": signal.detail,
                }
                for signal in vnext.repair.signals
            ],
        } if vnext.repair is not None else None,
    }
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"run: {run_root}")
    print("stages:")
    for s in states:
        mark = "x" if s.present else " "
        detail = f" ({', '.join(s.evidence)})" if s.evidence else ""
        print(f"  [{mark}] {s.key:10} {s.skill}{detail}")
    if vnext.tier is not None:
        confirmed = "confirmed by user" if (
            vnext.confirmed_by or "").casefold().startswith("user") else (
            vnext.confirmed_by or "unconfirmed")
        effective = effective_tier(vnext.tier, vnext.upgrades)
        tier_note = (
            vnext.tier if effective == vnext.tier
            else f"{vnext.tier} -> {effective} (upgraded)")
        print(f"run-profile: tier {tier_note} ({confirmed})")
        if vnext.upgrades:
            print(f"  upgrades: {'; '.join(vnext.upgrades)}")
    if vnext.shaping is not None:
        print(f"shaping: session {vnext.shaping}")
    if vnext.six_block:
        note = " with invalidated evidence set" if vnext.invalidated else ""
        print(f"point-back: six-block vNext report{note}")
    repair = vnext.repair
    if repair is not None and not repair.empty:
        faces = [f"{repair.rounds} round(s)"] if repair.rounds else []
        if repair.routes:
            faces.append("routes " + ", ".join(
                f"{route} x{count}" for route, count in repair.routes))
        if repair.dd_supersedes:
            faces.append(f"dd supersedes x{repair.dd_supersedes}")
        if repair.stale_reviews:
            faces.append(f"stale reviews x{repair.stale_reviews}")
        print(f"repair: {'; '.join(faces)}")
        if repair.signals:
            listed = "; ".join(
                f"{signal.signal} -> {signal.required_tier}"
                for signal in repair.signals)
            print(f"escalation signals: {listed}")
        if repair.close_reason:
            waiting = " (waiting user disposition)" if repair.wait_user else ""
            print(f"close_reason: {repair.close_reason}{waiting}")
    if payload["verdict"]:
        print(f"verdict: {payload['verdict']}")
    print(f"next: {action}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Status / resume hints from Design I/O run artifacts",
    )
    parser.add_argument(
        "run_root",
        nargs="?",
        default=None,
        help="path to .scratch/<run>/ (default: newest under .scratch/)",
    )
    parser.add_argument(
        "--scratch",
        default=str(ROOT / ".scratch"),
        help="scratch root used when run_root is omitted",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="list discovered runs under --scratch and exit",
    )
    args = parser.parse_args(argv)

    scratch = Path(args.scratch)
    if args.list:
        runs = discover_runs(scratch)
        if not runs:
            print(f"no runs under {scratch}")
            return 0
        for path in runs:
            print(path)
        return 0

    if args.run_root:
        run_root = Path(args.run_root)
    else:
        runs = discover_runs(scratch)
        if not runs:
            print(f"RUN STATUS ERROR: no runs under {scratch}", file=sys.stderr)
            return 2
        run_root = runs[0]
    return render(run_root, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
