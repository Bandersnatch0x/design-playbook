"""Adapter capability matrix — one row per agent (ADR-0042).

Dispatch keys off the agent id, its tier, and the ``native`` flag
(``_SPECIALIZED_RENDERERS`` + the shared AGENTS.md floor fallback in
generate_adapter.py), so adding an agent = adding a matrix row. The
per-surface capability flags this file once carried (rules / commands /
mcp_project / hooks / skills / rules_target) had no production consumer —
no renderer or gate ever read them — and were retired 2026-09-20 (T-040;
ADR-0042 amendment): the tier encodes the capability class, each renderer
documents its own output surface, and the published counts are derived
from this matrix by the validate.py gate.

Decision authority: docs/adr/0042-multi-platform-adapter-generator.md.
This module owns the current adapter inventory.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentRow:
    """One row in the adapter capability matrix."""

    agent: str
    tier: int
    # True when the host platform consumes the package directly (no generated
    # adapter output).  The generator skips native rows entirely.
    native: bool = False

    def __post_init__(self) -> None:
        if self.tier not in (1, 2, 3):
            raise ValueError(f"{self.agent}: tier must be 1, 2, or 3, got {self.tier!r}")
        if not self.agent:
            raise ValueError("agent must be non-empty")


# Tier 1 — full fidelity (skills + commands + MCP + hooks where supported).
# These agents have dedicated, committed snapshots verified by validate.py.
_TIER1: tuple[AgentRow, ...] = (
    AgentRow(agent="claude-code", tier=1, native=True),
    AgentRow(agent="codex", tier=1),
)

# Tier 2 — skills + MCP (commands degrade to documented prompt equivalents).
_TIER2: tuple[AgentRow, ...] = (
    AgentRow(agent="cursor", tier=2),
    AgentRow(agent="gemini-cli", tier=2),
    AgentRow(agent="opencode", tier=2),
    AgentRow(agent="windsurf", tier=2),
    AgentRow(agent="github-copilot", tier=2),
    AgentRow(agent="zed", tier=2),
)

# Tier 3 — rules floor (generated AGENTS.md + inline MCP guide).
# One renderer covers all; rows can be promoted by adding a dedicated renderer.
_TIER3_AGENTS: tuple[str, ...] = (
    "qoder",
    "kiro-ide",
    "kiro-cli",
    "amp",
    "auggie",
    "codebuddy",
    "forge",
    "ibm-bob",
    "jules",
    "kilo-code",
    "pi",
    "qwen-code",
    "roo-code",
    "shai",
    "tabnine",
    "mistral-vibe",
    "kimi-code",
    "iflow",
    "junie",
    "antigravity",
    "trae",
    "generic",
)

_TIER3: tuple[AgentRow, ...] = tuple(
    AgentRow(agent=name, tier=3) for name in _TIER3_AGENTS
)

MATRIX: tuple[AgentRow, ...] = _TIER1 + _TIER2 + _TIER3

# Agents for which the generator produces committed snapshots verified by
# the validate.py drift gate.  Native rows are consumed directly by the host
# platform and never get generated snapshots.
TIER1_SNAPSHOT_AGENTS: tuple[str, ...] = tuple(
    row.agent for row in MATRIX if row.tier == 1 and not row.native
)


def get_agent(agent: str) -> AgentRow | None:
    """Return the row for *agent*, or None if the agent is not in the matrix."""
    for row in MATRIX:
        if row.agent == agent:
            return row
    return None


def validate_matrix(rows: tuple[AgentRow, ...] = MATRIX) -> list[str]:
    """Return a list of error strings (empty means the matrix is valid)."""
    errors: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if row.agent in seen:
            errors.append(f"duplicate agent: {row.agent!r}")
        seen.add(row.agent)
        try:
            row.__post_init__()
        except ValueError as exc:
            errors.append(str(exc))
        if row.native and row.tier != 1:
            errors.append(f"{row.agent}: native rows must be Tier 1")
    return errors
