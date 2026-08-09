#!/usr/bin/env python3
"""Derive Design I/O run status / resume hints from existing artifacts.

Does **not** create a second run-state SSOT. Reads only files agents already
write under a run root (default: discover newest ``.scratch/*/``).
"""
from __future__ import annotations

import argparse
import json
import re
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
# artifact-name constants are shared with validate_run.py.
from design_playbook.scripts.stages import POINT_BACK, STAGES  # noqa: E402


@dataclass(frozen=True)
class StageState:
    key: str
    skill: str
    present: bool
    evidence: list[str]


def _exists(run_root: Path, relative: str) -> bool:
    return (run_root / relative).exists()


def inspect_run(
    run_root: Path, preview_snapshot: PreviewSnapshot | None = None
) -> list[StageState]:
    snapshot = preview_snapshot or inspect_preview(run_root / "preview")
    states: list[StageState] = []
    for key, skill, markers in STAGES:
        if key == "preview":
            found = [f"preview/{source}" for source in snapshot.occurrence_sources]
        else:
            found = [m for m in markers if _exists(run_root, m)]
        states.append(StageState(key=key, skill=skill, present=bool(found), evidence=found))
    return states


def discover_runs(scratch: Path) -> list[Path]:
    if not scratch.is_dir():
        return []
    runs = [p for p in scratch.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))]
    runs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return runs


def verdict_of(run_root: Path) -> str | None:
    path = run_root / POINT_BACK
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.lower().startswith("## verdict"):
            # next non-empty line or same-line content
            rest = line.split(":", 1)
            if len(rest) == 2 and rest[1].strip():
                return rest[1].strip()
            continue
        if "verdict" in line.lower() and ("pass" in line.lower() or "recirculate" in line.lower()):
            if "pass" in line.lower() and "recirculate" not in line.lower():
                return "Pass"
            if "recirculate" in line.lower():
                return "Recirculate"
    if re.search(r"^##\s*Verdict\s*$[\s\S]*?\bPass\b", text, re.I | re.M):
        return "Pass"
    if re.search(r"^##\s*Verdict\s*$[\s\S]*?\bRecirculate\b", text, re.I | re.M):
        return "Recirculate"
    return None


def _baseline_next_action(run_root: Path) -> str | None:
    """Return a blocking resume hint when the DesignBaseline gate is incomplete.

    Reads only ``design-baseline/state.json`` (schema ``design-baseline/v1``),
    which is the sole stage marker (ADR-0012). Mirrors the public statuses
    produced by ``prepare`` / ``confirm`` / ``verify``:
    ``ready`` (bound), ``waived`` (explicit reason), ``needs_confirmation``,
    or ``ambiguous``. This is **status narration only** — it does not re-hash
    sources or re-verify the binding. ``verify()`` at Fill time is the
    forge-resistant gate.
    """
    state_path = run_root / "design-baseline" / "state.json"
    # Stage is only present when state.json exists, so a missing file here is
    # a race/corruption case rather than the orphan-draft path.
    if not state_path.is_file():
        return ("Design-baseline state.json vanished mid-read — "
                "re-run design-baseline prepare before Fill.")
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "Design-baseline state.json is unreadable — re-run design-baseline prepare before Fill."
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


def next_action(
    states: list[StageState],
    run_root: Path,
    preview_snapshot: PreviewSnapshot | None = None,
) -> str:
    snapshot = preview_snapshot or inspect_preview(run_root / "preview")
    present = {state.key: state for state in states if state.present}
    if "baseline" in present:
        blocked = _baseline_next_action(run_root)
        if blocked is not None:
            return blocked
    if "accept" in present:
        verdict = verdict_of(run_root)
        if verdict and verdict.lower().startswith("pass"):
            return "Run complete (Pass). Ship or start a new run."
        if verdict and "recirculate" in verdict.lower():
            return "Verdict is Recirculate — repair from point-back findings, then re-run ui-evaluator."
        return "point-back.md present — confirm ## Verdict, then stop or recirculate."
    if "evidence" in present and "accept" not in present:
        return "Resume at ui-evaluator (accept) with evidence ledger bound."
    if "craft" in present and "accept" not in present:
        return "Resume at observe* (if adapter present) or ui-evaluator."
    if "fill" in present and "craft" not in present:
        return "Resume at craft-guard, then observe*/ui-evaluator."
    if "preview" in present and "fill" not in present:
        confirm = snapshot.canonical_current_confirm
        if confirm is None:
            invalid = next(
                (
                    fact
                    for fact in snapshot.facts
                    if fact.code == "invalid_confirm_record"
                    and fact.path is not None
                ),
                None,
            )
            if invalid is not None:
                return (
                    f"Preview confirm unreadable ({invalid.path.name}); "
                    "re-run preview*."
                )
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
    if "decision" in present and "preview" not in present and "fill" not in present:
        return "Resume at preview* (if adapter present) or fill."
    if "plan" in present and "decision" not in present:
        return "Resume at ui-picker (decision-report)."
    if "spec" in present and "decision" not in present and "plan" not in present:
        return "Resume at plan? (optional) or ui-picker."
    if "reference" in present and "spec" not in present:
        return "Resume at ux-spec (reference contract present)."
    if "baseline" in present and "reference" not in present and "spec" not in present:
        return "Design baseline bound — resume at reference-intake? (if needed) or ux-spec."
    if not present:
        return "No run artifacts — start with /design-playbook:design-io <ask> (design-baseline?, reference-intake?, or ux-spec)."
    # partial unknown
    last = [s for s in states if s.present][-1]
    return f"Latest artifact stage: {last.key} ({last.skill}). Continue the orchestrator sequence from there."


def render(run_root: Path, *, as_json: bool) -> int:
    if not run_root.is_dir():
        print(f"RUN STATUS ERROR: not a directory: {run_root}", file=sys.stderr)
        return 2
    snapshot = inspect_preview(run_root / "preview")
    states = inspect_run(run_root, snapshot)
    action = next_action(states, run_root, snapshot)
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
        "verdict": verdict_of(run_root),
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
