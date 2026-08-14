#!/usr/bin/env python3
"""Derive Design I/O run status / resume hints from existing artifacts.

Does **not** create a second run-state SSOT. Reads only files agents already
write under a run root (default: discover newest ``.scratch/*/``).
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
from design_playbook.scripts.run_profile import parse_run_profile  # noqa: E402
from design_playbook.scripts.shaping_log import (  # noqa: E402
    ShapingLogError,
    load_shaping_facts,
    queue_state,
)


@dataclass(frozen=True)
class VnextNarration:
    """Additive vNext narration facts (run-profile block + shaping session)."""

    tier: str | None
    confirmed_by: str | None
    skipped: tuple[tuple[str, str], ...]
    upgrades: tuple[str, ...]
    shaping: str | None


def inspect_vnext(run_root: Path) -> VnextNarration:
    """Read run-profile (plan.md) and shaping session state (additive)."""
    tier = None
    confirmed_by = None
    skipped: tuple[tuple[str, str], ...] = ()
    upgrades: tuple[str, ...] = ()
    plan_path = run_root / "plan.md"
    if plan_path.is_file():
        try:
            profile = parse_run_profile(
                plan_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError):
            profile = None
        if profile is not None:
            tier = profile.tier or None
            confirmed_by = profile.confirmed_by or None
            skipped = profile.skipped
            upgrades = profile.upgrades
    shaping: str | None = None
    try:
        session = load_shaping_facts(run_root)
    except (ShapingLogError, OSError, UnicodeError):
        shaping = "unreadable"
    else:
        if session is not None:
            shaping = queue_state(list(session.events))
    return VnextNarration(
        tier=tier, confirmed_by=confirmed_by, skipped=skipped,
        upgrades=upgrades, shaping=shaping,
    )


@dataclass(frozen=True)
class StageState:
    key: str
    skill: str
    present: bool
    evidence: list[str]


def inspect_run(
    run_root: Path, preview_snapshot: PreviewSnapshot | None = None,
    run_facts: RunFacts | None = None,
) -> list[StageState]:
    facts = run_facts or capture_run_facts(run_root=run_root)
    snapshot = preview_snapshot or facts.preview or inspect_preview(run_root / "preview")
    states: list[StageState] = []
    for stage in STAGES:
        if stage.key == "preview":
            found = [f"preview/{source}" for source in snapshot.occurrence_sources]
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
    pointback_error = next(
        (
            error
            for error in facts.read_errors
            if error.artifact == "point_back" and error.code != "missing"
        ),
        None,
    )
    if pointback_error is not None:
        print(
            f"RUN STATUS ERROR: cannot read point-back.md: {pointback_error.message}",
            file=sys.stderr,
        )
        return 2
    snapshot = facts.preview or inspect_preview(run_root / "preview")
    states = inspect_run(run_root, snapshot, facts)
    action = next_action(states, run_root, snapshot, facts)
    vnext = inspect_vnext(run_root)
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
            "confirmed_by": vnext.confirmed_by,
            "skipped": [
                {"step": name, "reason": reason}
                for name, reason in vnext.skipped
            ],
            "upgrades": list(vnext.upgrades),
        } if vnext.tier is not None else None,
        "shaping": vnext.shaping,
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
        print(f"run-profile: tier {vnext.tier} ({confirmed})")
        if vnext.upgrades:
            print(f"  upgrades: {'; '.join(vnext.upgrades)}")
    if vnext.shaping is not None:
        print(f"shaping: session {vnext.shaping}")
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
