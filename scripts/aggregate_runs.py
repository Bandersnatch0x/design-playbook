#!/usr/bin/env python3
"""Cross-run aggregate over Design I/O dogfood runs (run aggregate, v0.9).

Deterministic seam over ``.scratch/**/dogfood/*/`` run dirs: per-run rollup
(artifact completeness + G5/G6 gate status via ``validate_run.py``) and
repeat-blocker detection (normalized ``observed`` text frequency).

Repeat blocker = pure statistics, never a judgment: the same normalized
``observed`` text appearing across runs is a systemic-defect signal; no
prose learning, no auto-feedback into the baseline (CONTEXT: ``run
aggregate`` / ``repeat blocker``).

Usage:
  aggregate_runs.py [--root <repo-root>] [--runs <glob-or-dir>...]
                    [--out <json-path>] [--md] [--md-out <path>]
                    [--top N]

Exit 0; prints JSON to stdout unless --out.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "packages" / "design-playbook"
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from design_playbook.mcp.evidence.ledger_syntax import LedgerFacts, parse_ledger  # noqa: E402
from design_playbook.scripts.learning_candidates import (  # noqa: E402
    candidate_view,
    occurrences_from_pointbacks,
)
from design_playbook.scripts.run_facts import RunFacts, capture_run_facts  # noqa: E402
from design_playbook.scripts.validate_run import run as validate_run  # noqa: E402

DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
SPEC_NAMES = ("spec.md", "01-spec.md")


def find_runs(root: Path, override: list[str] | None) -> list[Path]:
    """Default: walk ``root/.scratch/**/dogfood/*/`` dirs with point-back.md.

    ``override`` (--runs) may be dirs or globs (resolved against root);
    when given, the default scan is skipped.
    """
    if override:
        found: list[Path] = []
        for raw in override:
            p = Path(raw)
            if not p.is_absolute():
                p = root / p
            matches = sorted(root.glob(str(p.relative_to(root)))) if p.is_relative_to(root) else [p]
            for m in matches:
                if m.is_file():
                    m = m.parent
                if m.is_dir():
                    found.append(m)
        return [d for d in dict.fromkeys(found) if (d / "point-back.md").is_file()]
    scratch = root / ".scratch"
    if not scratch.is_dir():
        return []
    runs: list[Path] = []
    for d in sorted(scratch.glob("**/dogfood/*")):
        if d.is_dir() and (d / "point-back.md").is_file():
            runs.append(d)
    return runs


def run_meta(run_dir: Path, root: Path) -> dict[str, str | None]:
    name = run_dir.name
    m = DATE_RE.match(name)
    effort = None
    try:
        rel = run_dir.resolve().relative_to((root / ".scratch").resolve())
        effort = rel.parts[0] if rel.parts else None
    except ValueError:
        pass
    return {
        "id": name,
        "date": m.group(1) if m else None,
        "effort": effort,
    }


def artifacts(run_dir: Path, run_facts: RunFacts | None = None) -> dict[str, bool]:
    facts = run_facts or capture_run_facts(run_root=run_dir)
    existing = facts.existing_paths
    spec = any(s in existing for s in SPEC_NAMES)
    return {
        "plan": "plan.md" in existing,
        "point_back": "point-back.md" in existing,
        "evidence_manifest": "evidence/manifest.jsonl" in existing,
        "preview": "preview" in existing,
        "spec": spec,
    }


def ledger_rows(
        point_back_text: str, ledger_facts: LedgerFacts | None = None
) -> list[dict[str, str]]:
    """Parse the evidence-ledger blocks (criterion/required/observed/result)."""
    facts = ledger_facts or parse_ledger(point_back_text)
    rows: list[dict[str, str]] = []
    for fact in facts.rows:
        row: dict[str, str] = {}
        for key in ("criterion", "required", "observed", "result"):
            values = fact.values(key)
            if values:
                row[key] = values[0]
        rows.append(row)
    return rows


def gate_status(run_dir: Path, run_facts: RunFacts | None = None) -> dict[str, str]:
    """Evaluate validate_run policy over the same immutable run snapshot."""
    facts = run_facts or capture_run_facts(
        run_root=run_dir, pointback_fallback_encoding="gb18030"
    )
    spec = facts.spec_path
    if spec is None or "point-back.md" not in facts.existing_paths:
        return {"status": "skipped", "detail": "no spec.md + point-back.md pair"}
    try:
        errors, _warnings = validate_run(
            str(spec),
            str(facts.pointback_path),
            preview_dir=str(facts.preview_dir),
            evidence_dir=str(facts.evidence_dir),
            run_root=str(run_dir),
            run_facts=facts,
        )
    except (OSError, UnicodeError):
        # The historical subprocess exited non-zero for validator I/O errors;
        # its RUN ERROR line was filtered, leaving this fallback projection.
        return {"status": "fail", "detail": "violations"}
    if not errors:
        return {"status": "ok", "detail": "RUN OK"}
    return {"status": "fail", "detail": f"FAIL  {errors[0].message}"[:200]}


def normalize(text: str) -> str:
    # Sync with packages/design-playbook/commands/run-review.md (SSOT) and
    # tests/test_normalize_lockstep.py: casefold + collapse whitespace,
    # then char-for-char equality. Repeat count is distinct runs (OPP-21).
    return " ".join(text.casefold().split())


def aggregate(runs: list[Path], root: Path, top: int,
              task_contexts: dict[str, str] | None = None) -> dict:
    payload: dict = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scratch_root": str((root / ".scratch").resolve()),
        "runs_total": len(runs),
        "runs": [],
        "rollup": {},
        "repeat_blockers": [],
        # vNext S5 additive key (vnext-prototype 1.2): the derived D8
        # learning-candidate view. Reported only, never written back; the
        # legacy keys above are unchanged.
        "learning_candidates": {},
    }
    by_result: dict[str, int] = {}
    blockers: dict[str, dict] = {}
    pointbacks: dict[str, str] = {}
    for run_dir in runs:
        facts = capture_run_facts(
            run_root=run_dir, pointback_fallback_encoding="gb18030"
        )
        meta = run_meta(run_dir, root)
        art = artifacts(run_dir, facts)
        gate = gate_status(run_dir, facts)
        pb_text = facts.pointback_text
        if meta["id"] not in pointbacks:
            pointbacks[meta["id"]] = pb_text
        rows = ledger_rows(pb_text, facts.ledger)
        run_rec = {
            "id": meta["id"],
            "date": meta["date"],
            "effort": meta["effort"],
            "artifacts": art,
            "gate": gate,
            "ledger": [],
        }
        for row in rows:
            criterion = row.get("criterion", "")
            result = (row.get("result") or "unknown").strip().lower()
            observed = row.get("observed", "")
            by_result[result] = by_result.get(result, 0) + 1
            run_rec["ledger"].append({
                "criterion": criterion,
                "result": result,
                "observed": observed,
            })
            if result != "pass":
                norm = normalize(observed)
                if norm:
                    blk = blockers.setdefault(norm, {
                        "text": observed.strip(),
                        "count": 0,
                        "runs": [],
                        "results": {},
                    })
                    if meta["id"] not in blk["runs"]:
                        blk["runs"].append(meta["id"])
                        blk["count"] += 1
                    blk["results"][result] = blk["results"].get(result, 0) + 1
        payload["runs"].append(run_rec)
    payload["rollup"] = {
        "by_result": dict(sorted(by_result.items())),
        "ledger_rows": sum(len(r["ledger"]) for r in payload["runs"]),
    }
    payload["repeat_blockers"] = [
        b for b in sorted(blockers.values(), key=lambda b: (-b["count"], b["text"]))
        if b["count"] >= 2][:top]
    payload["learning_candidates"] = candidate_view(
        occurrences_from_pointbacks(pointbacks, task_contexts=task_contexts))
    return payload


def markdown_view(payload: dict) -> str:
    lines = [
        "# Run aggregate",
        "",
        f"Generated: {payload['generated']} · runs: {payload['runs_total']} · "
        f"ledger rows: {payload['rollup'].get('ledger_rows', 0)}",
        "",
        "## Runs",
        "",
        "| run | date | effort | plan | pb | evidence | preview | spec | gate |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in payload["runs"]:
        a = r["artifacts"]
        gate = r["gate"]["status"]
        lines.append(
            f"| {r['id']} | {r['date'] or '-'} | {r['effort'] or '-'} | "
            f"{'✓' if a['plan'] else '·'} | {'✓' if a['point_back'] else '·'} | "
            f"{'✓' if a['evidence_manifest'] else '·'} | "
            f"{'✓' if a['preview'] else '·'} | {'✓' if a['spec'] else '·'} | "
            f"{gate} |"
        )
    lines += ["", "## Repeat blockers", ""]
    b = payload["repeat_blockers"]
    if not b:
        lines.append("_none_")
    else:
        lines += ["| count | runs | observed |", "| --- | --- | --- |"]
        for blk in b:
            lines.append(
                f"| {blk['count']} | {', '.join(blk['runs'][:5])} | {blk['text'][:80]} |")
    lines += ["", "## Rule candidates (derived, vNext S5)", ""]
    view = payload.get("learning_candidates") or {}
    qualifying = view.get("qualifying", [])
    below = view.get("below_threshold", [])
    if not qualifying and not below:
        lines.append("_none_")
    else:
        if qualifying:
            lines += [
                "| candidate | runs | contexts | signal |",
                "| --- | --- | --- | --- |",
            ]
            for cand in qualifying:
                lines.append(
                    f"| {cand['candidate_id']} | {cand['distinct_runs']} | "
                    f"{cand['distinct_task_contexts']} | "
                    f"{cand['signal_key'][:80]} |")
        else:
            lines.append("_no qualifying candidates_")
        lines.append("")
        lines.append(
            f"below threshold (gap to the queue): {len(below)}"
            + (f" — {', '.join(c['candidate_id'] for c in below[:5])}"
               if below else ""))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows GBK consoles
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--runs", nargs="*", default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--md", action="store_true", help="print markdown view")
    parser.add_argument("--md-out", type=Path, default=None)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument(
        "--candidate-contexts", type=Path, default=None,
        help="JSON file mapping run id -> task context for the derived "
             "learning-candidate view (rules-prototype 5.1: contexts come "
             "from contract / spec / manifest, not from the scan)")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    runs = find_runs(root, args.runs)
    task_contexts = None
    if args.candidate_contexts is not None:
        try:
            task_contexts = json.loads(
                args.candidate_contexts.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            print(f"cannot read --candidate-contexts {args.candidate_contexts}: "
                  f"{exc}", file=sys.stderr)
            return 2
        if not isinstance(task_contexts, dict):
            print("--candidate-contexts must map run id -> task context",
                  file=sys.stderr)
            return 2
    payload = aggregate(runs, root, args.top, task_contexts=task_contexts)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.md or args.md_out:
        view = markdown_view(payload)
        if args.md_out:
            args.md_out.write_text(view, encoding="utf-8")
        if args.md:
            print(view)
            return 0
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out} ({len(runs)} runs)", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
