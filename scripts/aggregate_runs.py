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
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

VALIDATE_RUN = Path(__file__).resolve().parents[1] / "packages" / "design-playbook" / "scripts" / "validate_run.py"

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


def artifacts(run_dir: Path) -> dict[str, bool]:
    spec = any((run_dir / s).is_file() for s in SPEC_NAMES)
    return {
        "plan": (run_dir / "plan.md").is_file(),
        "point_back": (run_dir / "point-back.md").is_file(),
        "evidence_manifest": (run_dir / "evidence" / "manifest.jsonl").is_file(),
        "preview": (run_dir / "preview").is_dir(),
        "spec": spec,
    }


def ledger_rows(point_back_text: str) -> list[dict[str, str]]:
    """Parse the evidence-ledger blocks (criterion/required/observed/result)."""
    rows: list[dict[str, str]] = []
    lines = point_back_text.splitlines()
    current: dict[str, str] | None = None
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("criterion:") or stripped.startswith("criterion :"):
            if current:
                rows.append(current)
            current = {"criterion": stripped.split(":", 1)[1].strip()}
            continue
        if current is None:
            continue
        for key in ("required", "observed", "result"):
            low = stripped.lower()
            if low.startswith(key + ":") or low.startswith(key + " :"):
                current[key] = stripped.split(":", 1)[1].strip()
                break
        if stripped.startswith("#") or stripped.startswith("##"):
            if current:
                rows.append(current)
                current = None
    if current:
        rows.append(current)
    return rows


def _spec_path(run_dir: Path) -> Path | None:
    for s in SPEC_NAMES:
        p = run_dir / s
        if p.is_file():
            return p
    return None


def _read_text_lossy(path: Path) -> str:
    """Read with UTF-8, falling back to GB18030 for legacy dogfood runs.

    Early dogfood point-back files were authored with GBK-family encodings;
    forcing UTF-8 mangles CJK observed text and defeats repeat-blocker
    normalization. GB18030 is a superset of GBK/GB2312 and always decodes.
    """
    raw = path.read_bytes()
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def gate_status(run_dir: Path) -> dict[str, str]:
    """Run validate_run over the run's spec+point-back; exit 0 = ok."""
    spec = _spec_path(run_dir)
    pb = run_dir / "point-back.md"
    if spec is None or not pb.is_file():
        return {"status": "skipped", "detail": "no spec.md + point-back.md pair"}
    cmd = [sys.executable, str(VALIDATE_RUN), str(spec), str(pb)]
    if (run_dir / "preview").is_dir():
        cmd += ["--preview-dir", str(run_dir / "preview")]
    if (run_dir / "evidence").is_dir():
        cmd += ["--evidence-dir", str(run_dir / "evidence")]
    cmd += ["--run-root", str(run_dir)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "error", "detail": str(exc)}
    if proc.returncode == 0:
        return {"status": "ok", "detail": "RUN OK"}
    first_err = ""
    for line in (proc.stdout + proc.stderr).splitlines():
        line = line.strip()
        if line and "RUN" not in line:
            first_err = line[:200]
            break
    return {"status": "fail", "detail": first_err or "violations"}


def normalize(text: str) -> str:
    return " ".join(text.casefold().split())


def aggregate(runs: list[Path], root: Path, top: int) -> dict:
    payload: dict = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scratch_root": str((root / ".scratch").resolve()),
        "runs_total": len(runs),
        "runs": [],
        "rollup": {},
        "repeat_blockers": [],
    }
    by_result: dict[str, int] = {}
    blockers: dict[str, dict] = {}
    for run_dir in runs:
        meta = run_meta(run_dir, root)
        art = artifacts(run_dir)
        gate = gate_status(run_dir)
        pb_text = _read_text_lossy(run_dir / "point-back.md")
        rows = ledger_rows(pb_text)
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
                        blk["runs"].append(str(meta["id"]))
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
    args = parser.parse_args(argv)
    root = args.root.resolve()
    runs = find_runs(root, args.runs)
    payload = aggregate(runs, root, args.top)
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
