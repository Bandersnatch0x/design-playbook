#!/usr/bin/env python3
"""Derive Design I/O run status / resume hints from existing artifacts.

CLI seam over the projection library (``status_projection.py``), which owns
the typed next-action model and the stage / vNext / verdict inspectors; this
module renders them (text / JSON) and holds the ``scripts/run_status.py``
path contract used by subprocess callers. Does **not** create a second
run-state SSOT. Reads only files agents already write under a run root
(default: discover newest ``.scratch/*/``). Fill surfaces may live outside
the run root: when ``plan.md`` registers them with ``fill:`` field lines,
the fill stage is also judged on those declared paths (issue #44; the stage
registry itself is unchanged).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Package-local scripts directory (works for installed plugin and monorepo
# copy).
_SCRIPTS_DIR = Path(__file__).resolve().parent

# One import seam (ADR-0022): package root on sys.path once, then absolute
# design_playbook.* imports below. No per-runtime sys.path adapters.
_PKG_ROOT = _SCRIPTS_DIR.parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))
from design_playbook.mcp.preview.integrity import inspect_preview  # noqa: E402
from design_playbook.scripts.audit_preferences import parse_audit_marker  # noqa: E402
from design_playbook.scripts.escalation_signals import effective_tier  # noqa: E402
from design_playbook.scripts.run_facts import capture_run_facts  # noqa: E402
from design_playbook.scripts.status_projection import (  # noqa: E402
    _audit_disposition,
    discover_runs,
    inspect_run,
    inspect_vnext,
    next_action,
    verdict_of,
)

# Repo/package root for default --scratch discovery only.
ROOT = _SCRIPTS_DIR.parent
if (ROOT / "packages" / "design-playbook").is_dir():
    pass  # monorepo layout: package under packages/design-playbook
elif ROOT.name == "design-playbook":
    pass  # package root when run from packages/design-playbook/scripts
else:
    ROOT = Path.cwd()


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
    audit_marker = parse_audit_marker(facts.pointback_text)
    audit_disposition = _audit_disposition(
        facts.pointback_text, marker=audit_marker
    )
    audited_projection = (
        False if audit_disposition in {"unaudited", "ambiguous"}
        else audit_marker.audited
    )
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
        # Fail closed: malformed/ambiguous markers project False, while
        # marker-less legacy reports alone retain None.
        "audited": audited_projection,
        "audit_marker_state": audit_disposition,
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
    # Ambiguous markers also project audited=False; check the disposition
    # first or the skeleton line masks the marker damage (the elif used to be
    # unreachable for exactly this reason).
    if audit_disposition == "ambiguous":
        print("audit: invalid marker (duplicate or malformed audited line)")
    elif payload["audited"] is False:
        print("audit: not audited (skeleton point-back)")
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
