"""Adapter capability matrix — one row per agent with per-surface flags.

Renderers in generate_adapter.py key off flags (not agent names), so
promoting an agent from Tier 3 to Tier 2 means adding a renderer that
handles the capability flags it advertises, not patching name checks.

Authority: docs/specs/2026-08-28-multi-platform-adapter.md §1 and
           docs/adr/0042-multi-platform-adapter-generator.md.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentRow:
    """One row in the adapter capability matrix."""

    agent: str
    tier: int
    rules: bool
    commands: bool
    mcp_project: bool
    hooks: bool
    skills: bool
    rules_target: str

    def __post_init__(self) -> None:
        if self.tier not in (1, 2, 3):
            raise ValueError(f"{self.agent}: tier must be 1, 2, or 3, got {self.tier!r}")
        if not self.agent:
            raise ValueError("agent must be non-empty")
        if not self.rules_target:
            raise ValueError(f"{self.agent}: rules_target must be non-empty")


# Tier 1 — full fidelity (skills + commands + MCP + hooks where supported).
# These agents have dedicated, committed snapshots verified by validate.py.
_TIER1: tuple[AgentRow, ...] = (
    AgentRow(
        agent="claude-code",
        tier=1,
        rules=True,
        commands=True,
        mcp_project=True,
        hooks=True,
        skills=True,
        rules_target="native plugin (skills/)",
    ),
    AgentRow(
        agent="codex",
        tier=1,
        rules=True,
        commands=True,
        mcp_project=True,
        hooks=False,
        skills=True,
        rules_target=".codex-plugin/ + codex/AGENTS.md",
    ),
)

# Tier 2 — skills + MCP (commands degrade to documented prompt equivalents).
_TIER2: tuple[AgentRow, ...] = (
    AgentRow(
        agent="cursor",
        tier=2,
        rules=True,
        commands=False,
        mcp_project=True,
        hooks=False,
        skills=False,
        rules_target=".cursor/rules/<name>.mdc",
    ),
    AgentRow(
        agent="gemini-cli",
        tier=2,
        rules=True,
        commands=True,
        mcp_project=True,
        hooks=False,
        skills=False,
        rules_target="GEMINI.md + .gemini/commands/",
    ),
    AgentRow(
        agent="opencode",
        tier=2,
        rules=True,
        commands=False,
        mcp_project=True,
        hooks=False,
        skills=False,
        rules_target="AGENTS.md (opencode)",
    ),
    AgentRow(
        agent="windsurf",
        tier=2,
        rules=True,
        commands=True,
        mcp_project=False,
        hooks=True,
        skills=False,
        rules_target=".windsurf/rules/<name>.md",
    ),
    AgentRow(
        agent="github-copilot",
        tier=2,
        rules=True,
        commands=False,
        mcp_project=True,
        hooks=False,
        skills=False,
        rules_target=".github/copilot-instructions.md",
    ),
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
    AgentRow(
        agent=name,
        tier=3,
        rules=True,
        commands=False,
        mcp_project=False,
        hooks=False,
        skills=False,
        rules_target="AGENTS.md",
    )
    for name in _TIER3_AGENTS
)

MATRIX: tuple[AgentRow, ...] = _TIER1 + _TIER2 + _TIER3

# Agents for which the generator produces committed snapshots verified by
# the validate.py drift gate.
TIER1_SNAPSHOT_AGENTS: tuple[str, ...] = tuple(
    row.agent for row in MATRIX if row.tier == 1 and row.agent != "claude-code"
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
        if row.tier == 1 and not row.rules:
            errors.append(f"{row.agent}: Tier-1 agent must have rules=True")
        if row.tier == 3 and (row.commands or row.mcp_project or row.hooks or row.skills):
            errors.append(
                f"{row.agent}: Tier-3 agent must have commands/mcp_project/hooks/skills=False"
            )
    return errors
