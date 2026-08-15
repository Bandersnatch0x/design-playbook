"""Run-profile block parsing (vNext S1, loop-prototype 1.4 / Q8=A).

``plan.md`` must open with a structured ``run-profile`` block — the block is
mandatory for every run even when the rest of the plan body is skipped:

    <!-- run-profile: v1 -->

    ```yaml
    tier: P2
    criteria:
      - decided-fields: add-only (l6.c1, l6.c2, export.*)
    confirmed_by: user + 2026-08-14T09:30:00Z
    skipped:
      - preview: adapter absent, no E-tier decisions (G5 not triggered)
    upgrades: []
    ```

Fields: ``tier`` P1|P2|P3 (point-fix / standard / full), the grading
checklist (``criteria``), one user confirmation line, the skip list (step +
reason, one line each — silent skips are illegal), and upgrade events.
``run_status.py`` narrates from this module; tests parse fixtures here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

RUN_PROFILE_MARKER = re.compile(r"<!--\s*run-profile(?::\s*v(\d+))?\s*-->")
FENCED_BLOCK = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.S)
TIERS = frozenset({"P1", "P2", "P3"})


@dataclass(frozen=True)
class RunProfile:
    """One parsed run-profile block from plan.md."""

    tier: str
    confirmed_by: str
    version: int = 1
    criteria: tuple[str, ...] = field(default_factory=tuple)
    skipped: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    upgrades: tuple[str, ...] = field(default_factory=tuple)


def _parse_items(block: str, key: str) -> tuple[str, ...]:
    """Collect list items under a ``key:`` line until the next top key."""
    items: list[str] = []
    collecting = False
    for line in block.splitlines():
        if re.match(rf"^{key}:\s*$", line.strip()):
            collecting = True
            continue
        if collecting:
            stripped = line.strip()
            if not stripped:
                continue
            if not stripped.startswith("- "):
                break
            items.append(stripped[2:].strip())
    return tuple(items)


def _parse_skips(block: str) -> tuple[tuple[str, str], ...]:
    skips: list[tuple[str, str]] = []
    for item in _parse_items(block, "skipped"):
        name, _, reason = item.partition(":")
        skips.append((name.strip(), reason.strip()))
    return tuple(skips)


def parse_run_profile(text: str) -> RunProfile | None:
    """Parse the run-profile block; None when plan.md carries no block."""
    marker = RUN_PROFILE_MARKER.search(text)
    if marker is None:
        return None
    version = int(marker.group(1)) if marker.group(1) else 1
    tail = text[marker.end():]
    fence = FENCED_BLOCK.search(tail)
    block = fence.group(1) if fence else ""

    tier = ""
    confirmed_by = ""
    for line in block.splitlines():
        match = re.match(r"^(tier|confirmed_by):\s*(.+)$", line.strip())
        if not match:
            continue
        if match.group(1) == "tier":
            tier = match.group(2).strip()
        else:
            confirmed_by = match.group(2).strip()
    return RunProfile(
        tier=tier,
        confirmed_by=confirmed_by,
        version=version,
        criteria=_parse_items(block, "criteria"),
        skipped=_parse_skips(block),
        upgrades=_parse_items(block, "upgrades"),
    )


def validate_run_profile(profile: RunProfile | None) -> list[str]:
    """Structural checks. Returns failure descriptions (empty = valid)."""
    if profile is None:
        return ["plan.md has no run-profile block (the block is mandatory; "
                "skipping the rest of the plan body is legal, skipping the "
                "profile block is not)"]
    errors: list[str] = []
    if profile.tier not in TIERS:
        errors.append(
            f"run-profile tier {profile.tier!r} not in P1|P2|P3 "
            "(point-fix / standard / full)"
        )
    if not profile.confirmed_by:
        errors.append("run-profile missing confirmed_by (user + timestamp)")
    elif not profile.confirmed_by.casefold().startswith("user"):
        errors.append(
            f"run-profile confirmed_by {profile.confirmed_by!r} must record "
            "the user confirmation (agent proposes, user confirms once)"
        )
    for name, reason in profile.skipped:
        if not name:
            errors.append("run-profile skip entry has no step name")
        if not reason:
            errors.append(
                f"run-profile skip entry {name!r} lacks a one-line reason "
                "(silent skips are illegal)"
            )
    return errors
