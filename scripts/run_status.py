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

ROOT = Path(__file__).resolve().parent.parent

# Ordered pipeline stages used only for status/resume narration.
#
# Mirror of SKILL.md Steps (spec / plan / decision / preview / fill / craft /
# evidence / accept); the SKILL.md Steps section points back here. When you
# add/remove a step or change an artifact filename in SKILL.md, sync this
# table. A lockstep test or a SKILL-embedded machine-readable table is deferred
# until ADR-0010 P1 turns STAGES into a navigation data source.
STAGES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("spec", "ux-spec", ("spec.md",)),
    ("plan", "plan", ("plan.md",)),
    ("decision", "ui-picker", ("decision-report.md",)),
    ("preview", "preview*", ("preview/log.md", "preview/confirm-round-1.json")),
    ("fill", "fill", ("filled-ui.html", "filled-ui.md")),
    ("craft", "craft-guard", ("craft-guard.md",)),
    ("evidence", "observe*", ("evidence/manifest.jsonl",)),
    ("accept", "ui-evaluator", ("point-back.md",)),
)


@dataclass(frozen=True)
class StageState:
    key: str
    skill: str
    present: bool
    evidence: list[str]


def _exists(run_root: Path, relative: str) -> bool:
    return (run_root / relative).exists()


def inspect_run(run_root: Path) -> list[StageState]:
    states: list[StageState] = []
    for key, skill, markers in STAGES:
        found = [m for m in markers if _exists(run_root, m)]
        states.append(StageState(key=key, skill=skill, present=bool(found), evidence=found))
    return states


def discover_runs(scratch: Path) -> list[Path]:
    if not scratch.is_dir():
        return []
    runs = [p for p in scratch.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))]
    runs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return runs


def latest_confirm(run_root: Path) -> Path | None:
    preview = run_root / "preview"
    if not preview.is_dir():
        return None
    confirms = sorted(preview.glob("confirm-round-*.json"))
    return confirms[-1] if confirms else None


def verdict_of(run_root: Path) -> str | None:
    path = run_root / "point-back.md"
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


def next_action(states: list[StageState], run_root: Path) -> str:
    present = {s.key: s for s in states if s.present}
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
        confirm = latest_confirm(run_root)
        if confirm is None:
            return "Preview artifacts exist without confirm — finish preview* HITL (G5) before fill."
        try:
            payload = json.loads(confirm.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return f"Preview confirm unreadable ({confirm.name}); re-run preview*."
        if payload.get("confirmed") is True or payload.get("aborted") is True:
            return "Preview decided — resume at fill."
        return "Preview open without decision — complete preview* confirm/revise."
    if "decision" in present and "preview" not in present and "fill" not in present:
        return "Resume at preview* (if adapter present) or fill."
    if "plan" in present and "decision" not in present:
        return "Resume at ui-picker (decision-report)."
    if "spec" in present and "decision" not in present and "plan" not in present:
        return "Resume at plan? (optional) or ui-picker."
    if not present:
        return "No run artifacts — start with /design-playbook:design-io <ask> (ux-spec)."
    # partial unknown
    last = [s for s in states if s.present][-1]
    return f"Latest artifact stage: {last.key} ({last.skill}). Continue the orchestrator sequence from there."


def render(run_root: Path, *, as_json: bool) -> int:
    if not run_root.is_dir():
        print(f"RUN STATUS ERROR: not a directory: {run_root}", file=sys.stderr)
        return 2
    states = inspect_run(run_root)
    action = next_action(states, run_root)
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
