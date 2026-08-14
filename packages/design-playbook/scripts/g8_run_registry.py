"""G8 run-level registry coverage gate (vNext S3, rules-prototype 8.2).

The product-level G8 self-check (repo ``scripts/validate.py``) landed in
S1. This module is the run-level face: the run's ``craft-guard.md`` audit
rows are evaluated against the same registry entries — both levels share
one canonical parser (``rules_registry.py``, moved next to this module in
S3 so the shipped package owns it).

Tier applicability matrix (loop-prototype 1.2 / 1.6):

- **P2 / P3** — full predicate evaluation: every registry entry that
  executes in the review surface (status ``advisory``, ``executes-in`` not
  ``registry-only``) must have *exactly one* seven-column audit row
  recording its three-state applicability evaluation. A missing row means
  a predicate was silently skipped, which is illegal.
- **P1** — subset evaluation: only touch-related families need rows, so
  completeness is not enforced; the rows that do exist must still be
  well-formed and version-pinned.
- **no tier** (legacy run, no run-profile block) — completeness is not
  enforced either (historical runs are never re-checked); row shapes are
  validated whenever rows parse.

Row-level checks (unknown ids, pinned-version drift, applicability/result
column semantics, blank reasons) come from the shared
``rules_registry.validate_craft_rows`` — the same rule the product-level
fixture check applies.
"""
from __future__ import annotations

import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[1]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.scripts import rules_registry  # noqa: E402
from design_playbook.scripts._diagnostics import Finding, finding  # noqa: E402
from design_playbook.scripts.run_profile import parse_run_profile  # noqa: E402

REGISTRY_PATH = (
    Path(__file__).resolve().parents[1] / "skills" / "design-playbook"
    / "references" / "rules.md"
)
# Tiers whose applicability matrix demands full predicate evaluation.
FULL_EVALUATION_TIERS = frozenset({"P2", "P3"})


def load_registry(path: Path | None = None) -> tuple[list, str]:
    """Parse the registry entries (shared parser, product-level format)."""
    target = path or REGISTRY_PATH
    text = target.read_text(encoding="utf-8")
    return rules_registry.parse_registry(text), text


def _reviewable(entry) -> bool:
    """Entries that execute in the review surface (completeness input)."""
    return (entry.status == "advisory"
            and entry.fields.get("executes-in") != "registry-only")


def check_g8_run(craft_text: str, entries: list, tier: str | None) -> list[Finding]:
    """Run-level G8 checks. Returns findings (empty = pass or not fired)."""
    errs: list[Finding] = []
    rows = rules_registry.parse_craft_rows(craft_text)

    for error in rules_registry.validate_craft_rows(rows, entries):
        errs.append(finding(
            "G8.run_row",
            f"G8 run: {error}",
            owner="craft-guard.md",
            expected="seven-column row valid against the registry",
            actual=error,
            repair="Fix the audit row (or pin the current entry version)",
        ))

    if tier not in FULL_EVALUATION_TIERS:
        return errs  # P1 subset or legacy run: completeness not enforced

    by_id: dict[str, int] = {}
    for row in rows:
        by_id[row.entry_id] = by_id.get(row.entry_id, 0) + 1
    for entry in entries:
        if not _reviewable(entry):
            continue
        count = by_id.get(entry.id, 0)
        if count == 0:
            errs.append(finding(
                "G8.run_missing_row",
                f"G8 run: {tier} demands full predicate evaluation but "
                f"{entry.id} has no audit row (silently skipping a "
                "predicate is illegal)",
                owner="craft-guard.md",
                expected=f"one seven-column row for {entry.id}@"
                         f"{entry.version}",
                actual="no row",
                repair=f"Evaluate {entry.id}'s applicability predicate and "
                       "record the row (applicable / not-applicable with "
                       "a reason / blocked)",
            ))
        elif count > 1:
            errs.append(finding(
                "G8.run_duplicate_row",
                f"G8 run: {entry.id} has {count} audit rows (exactly one "
                "row per applicable advisory entry)",
                owner="craft-guard.md",
                expected="exactly one row",
                actual=f"{count} rows",
                repair=f"Keep one row for {entry.id} (latest evaluation "
                       "wins; append-only)",
            ))
    return errs


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 4) or (len(argv) == 4 and argv[2] != "--plan"):
        print("Usage: g8_run_registry.py <craft-guard.md> [--plan <plan.md>]",
              file=sys.stderr)
        return 2
    craft_path = Path(argv[1])
    plan_path = (
        Path(argv[3]) if len(argv) == 4 else craft_path.parent / "plan.md"
    )
    try:
        craft_text = craft_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        print(f"G8 INVALID: cannot read {craft_path}: {exc}", file=sys.stderr)
        return 2
    try:
        entries, _ = load_registry()
    except (OSError, UnicodeError) as exc:
        print(f"G8 INVALID: cannot read the registry: {exc}", file=sys.stderr)
        return 2
    tier = None
    if plan_path.is_file():
        try:
            profile = parse_run_profile(
                plan_path.read_text(encoding="utf-8"))
            tier = profile.tier if profile is not None else None
        except (OSError, UnicodeError):
            tier = None
    findings = check_g8_run(craft_text, entries, tier)
    if not findings:
        print("G8 OK: craft audit rows satisfy the run-level registry gate")
        return 0
    print("G8 INVALID:")
    for item in findings:
        print(f"  FAIL  {item.message}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
