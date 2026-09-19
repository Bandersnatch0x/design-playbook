#!/usr/bin/env python3
"""Context budget for design-playbook skills (report-only).

Walks ``skills/*/SKILL.md`` and ``skills/*/references/*.md`` under the
package root and reports the context weight of the skill surface: the
always-loaded SKILL.md face per skill, its on-demand references, and the
worst-case full-pipeline total. Purely informational — no thresholds, no
gates, no writes, no network.

Token counts are character-level estimates, never tokenizer-exact:
``ascii_chars / 4 + non_ascii_chars`` (CJK prose runs near one token per
character; every output carries ``estimate: true``).

Usage:
  python scripts/context_budget.py            # text view (package root)
  python scripts/context_budget.py --json     # machine view
  python scripts/context_budget.py --root <package-root> --top 5
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent

_ESTIMATE_NOTE = (
    "token counts are character-level estimates: ascii/4 + non-ascii chars; "
    "not tokenizer-exact"
)


def estimate_tokens(text: str) -> int:
    """Character-level estimate (see module docstring)."""
    non_ascii = sum(1 for ch in text if ord(ch) > 127)
    return (len(text) - non_ascii) // 4 + non_ascii


def _measure_file(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    chars = len(text)
    return {
        "path": path.name,
        "chars": chars,
        "tokens_est": estimate_tokens(text),
    }


def measure_skills(package_root: Path) -> dict:
    """Measure the whole skill surface under *package_root*. Read-only."""
    skills_dir = package_root / "skills"
    skills: list[dict] = []
    for skill_dir in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.is_file():
            continue
        skill = {
            "skill": skill_dir.name,
            "skill_md": _measure_file(skill_file),
            "references": [
                _measure_file(p) for p in sorted((skill_dir / "references").glob("*.md"))
            ],
        }
        skill["references_tokens_est"] = sum(
            ref["tokens_est"] for ref in skill["references"]
        )
        skill["skill_tokens_est"] = skill["skill_md"]["tokens_est"]
        skill["total_tokens_est"] = (
            skill["skill_tokens_est"] + skill["references_tokens_est"]
        )
        skills.append(skill)

    all_files = [
        {"skill": s["skill"], **ref}
        for s in skills
        for ref in s["references"]
    ] + [{"skill": s["skill"], **s["skill_md"]} for s in skills]
    heaviest = sorted(all_files, key=lambda f: f["tokens_est"], reverse=True)

    return {
        "estimate": True,
        "estimate_note": _ESTIMATE_NOTE,
        "skills": skills,
        "total": {
            "skill_md_tokens_est": sum(s["skill_tokens_est"] for s in skills),
            "references_tokens_est": sum(s["references_tokens_est"] for s in skills),
            "worst_case_pipeline_tokens_est": sum(s["total_tokens_est"] for s in skills),
        },
        "heaviest_files": heaviest[:10],
    }


def _text_view(report: dict) -> str:
    lines = [
        "context budget (estimate: %s)" % report["estimate"],
        report["estimate_note"],
        "",
        f"{'skill':<18} {'skill.md':>10} {'refs':>10} {'total':>10}",
    ]
    for s in report["skills"]:
        lines.append(
            f"{s['skill']:<18} {s['skill_tokens_est']:>10} "
            f"{s['references_tokens_est']:>10} {s['total_tokens_est']:>10}"
        )
    t = report["total"]
    lines += [
        "",
        f"{'TOTAL':<18} {t['skill_md_tokens_est']:>10} "
        f"{t['references_tokens_est']:>10} "
        f"{t['worst_case_pipeline_tokens_est']:>10}",
        "",
        "heaviest files (tokens_est):",
    ]
    for f in report["heaviest_files"]:
        lines.append(f"  {f['tokens_est']:>8}  {f['skill']}/{f['path']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="context_budget",
        description="Report the context weight of the skill surface (report-only).",
    )
    parser.add_argument(
        "--root",
        default=str(_PACKAGE_ROOT),
        help="package root holding skills/ (default: this package)",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--top", type=int, default=10, metavar="N",
                        help="heaviest-file list length (default 10)")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    report = measure_skills(root)
    report["heaviest_files"] = report["heaviest_files"][: max(args.top, 0)]

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(_text_view(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
