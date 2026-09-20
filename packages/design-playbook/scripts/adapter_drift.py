#!/usr/bin/env python3
"""Snapshot drift comparison for tier-1 adapter agents (ADR-0042).

One compare algorithm, two thin consumers (T-038, spec 2026-09-20):

- root ``scripts/validate.py`` — the BLOCKING gate over committed snapshots
- root ``scripts/doctor.py``   — a read-only report of the same facts

Drift means: the committed snapshot bytes differ from what the current
generator would render for that path (byte compare after LF normalization,
so a CRLF checkout of a clean snapshot is not drift). The blocking-vs-report
semantic split between the two consumers stays with the consumers; this
module owns only the comparison and its refresh repair text.

Snapshot agents come from ``adapter_matrix.TIER1_SNAPSHOT_AGENTS``, so a
second tier-1 snapshot agent is covered by both gates without editing either.
The compare runs in-process over ``render_entries`` (no subprocess, hence no
timeout indirection); every failure surfaces as an ``error`` row instead of
an exception so neither consumer can crash on a bad snapshot file.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from adapter_matrix import TIER1_SNAPSHOT_AGENTS  # noqa: E402
from generate_adapter import render_entries  # noqa: E402

_REFRESH_CMD = (
    "python packages/design-playbook/scripts/generate_adapter.py {agent}"
)


def compare_snapshots(pkg_root: Path) -> list[dict]:
    """Compare committed snapshot files with a fresh render, read-only.

    Returns one row per snapshot file plus one aggregate row per agent:
    ``{"agent", "path", "status", "version", "message", "repair"}`` with
    ``status`` in ``clean`` / ``missing`` / ``drifted`` / ``error``
    (``error`` = the render itself failed; ``version`` is set on the
    aggregate row when the render succeeded). Consumers keep their own
    ok/fail wording and blocking semantics.
    """
    rows: list[dict] = []
    for agent in TIER1_SNAPSHOT_AGENTS:
        try:
            version, _out_dir, entries = render_entries(agent, pkg_root)
        except (ValueError, OSError, NotImplementedError) as exc:
            rows.append({
                "agent": agent, "path": None, "status": "error",
                "version": None,
                "message": f"adapter snapshot render failed ({agent}): {exc}",
                "repair": _REFRESH_CMD.format(agent=agent),
            })
            continue
        agent_ok = True
        for rel, content in entries:
            committed = pkg_root / rel
            if not committed.is_file():
                agent_ok = False
                rows.append({
                    "agent": agent, "path": rel, "status": "missing",
                    "version": version,
                    "message": f"adapter snapshot missing: {rel}",
                    "repair": _REFRESH_CMD.format(agent=agent),
                })
                continue
            expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
            try:
                committed_bytes = committed.read_bytes()
            except OSError as exc:
                agent_ok = False
                rows.append({
                    "agent": agent, "path": rel, "status": "error",
                    "version": version,
                    "message": f"adapter snapshot unreadable: {rel}: {exc}",
                    "repair": _REFRESH_CMD.format(agent=agent),
                })
                continue
            actual = hashlib.sha256(
                committed_bytes.replace(b"\r\n", b"\n")
            ).hexdigest()
            if actual == expected:
                rows.append({
                    "agent": agent, "path": rel, "status": "clean",
                    "version": version,
                    "message": f"adapter snapshot matches generator ({agent}/{rel})",
                    "repair": "",
                })
            else:
                agent_ok = False
                rows.append({
                    "agent": agent, "path": rel, "status": "drifted",
                    "version": version,
                    "message": f"adapter snapshot drift ({agent}/{rel})",
                    "repair": _REFRESH_CMD.format(agent=agent),
                })
        rows.append({
            "agent": agent, "path": None,
            "status": "clean" if agent_ok else "drifted",
            "version": version,
            "message": (
                f"adapter generator v{version} {agent} snapshot clean"
                if agent_ok
                else f"adapter generator {agent} snapshot stale"
            ),
            "repair": "" if agent_ok else _REFRESH_CMD.format(agent=agent),
        })
    return rows
