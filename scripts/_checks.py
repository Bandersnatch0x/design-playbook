"""Shared static-gate policy for the design-playbook plugin surface.

Single source for facts that validate.py (structure gate), doctor.py
(read-only diagnostic) and release.py (publish gate) must agree on.
Release-checklist mirror rule: one rule must not fork into two
thresholds — change the map here, never at both call sites.
"""
from __future__ import annotations

# Version line → exact shipped command set (ADR-0015 stable main / OPP-01).
# main is the public install surface, so unreleased capability must never
# ship under a released version: a new command requires a version entry
# that admits it, and a version entry requires its inventory on disk.
COMMAND_INVENTORY: dict[tuple[int, int], frozenset[str]] = {
    (0, 9): frozenset({"design-io", "ux-spec", "ui-review"}),
    (0, 10): frozenset({"design-io", "ux-spec", "ui-review", "run-review"}),
}


def version_key(version: str) -> tuple[int, int] | None:
    """(major, minor) for a semver-ish string, or None when unparseable."""
    try:
        major, minor = (int(x) for x in version.split(".", 2)[:2])
    except (ValueError, TypeError):
        return None
    return (major, minor)


def expected_commands(version: str) -> frozenset[str] | None:
    """Exact command set the version line admits, or None if undeclared."""
    key = version_key(version)
    if key is None:
        return None
    return COMMAND_INVENTORY.get(key)
