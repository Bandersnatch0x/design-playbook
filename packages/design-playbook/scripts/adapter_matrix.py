"""Adapter capability matrix — one row per agent (ADR-0042).

Dispatch keys off the row: its ``native`` flag says the host consumes the
package directly, its ``renderer`` names a dedicated renderer (Tier 1/2),
and a Tier-3 row renders through the shared AGENTS.md floor. The row cannot
be built with a tier its renderer cannot honor, so a Tier-2 declaration
cannot silently produce Tier-3 output. The
per-surface capability flags this file once carried (rules / commands /
mcp_project / hooks / skills / rules_target) had no production consumer —
no renderer or gate ever read them — and were retired 2026-09-20 (T-040;
ADR-0042 amendment): the tier encodes the capability class, each renderer
documents its own output surface, and the published counts are derived
from this matrix by the validate.py gate.

Each row also carries a lifecycle ``status`` (T-149 / S7): the tier says how
much surface a platform gets, the status says whether the platform is still
there to receive it.  ``dead`` rows emit no adapter (see ``AgentRow.generates``).

Decision authority: docs/adr/0042-multi-platform-adapter-generator.md.
This module owns the current adapter inventory.
"""
from __future__ import annotations

from dataclasses import dataclass


#: The tier is the capability class; ``status`` is the lifecycle class, and a
#: row cannot carry a value outside it.  ``dead`` is the one status with a
#: generator consequence: a product that no longer exists gets no adapter, so
#: the matrix cannot advertise breadth nobody can run (T-149 / S7,
#: ADR-0045 2026-11-06 amendment).
STATUSES: tuple[str, ...] = ("active", "deprecated", "rebranded", "dead")


@dataclass(frozen=True)
class AgentRow:
    """One row in the adapter capability matrix."""

    agent: str
    tier: int
    # True when the host platform consumes the package directly (no generated
    # adapter output).  The generator skips native rows entirely.
    native: bool = False
    #: The dedicated renderer this row uses; ``None`` means the shared
    #: AGENTS.md floor.  Renderer availability is a matrix fact, so a Tier-2
    #: declaration cannot silently render Tier-3 output: the row cannot be
    #: built without naming its renderer.
    renderer: str | None = None
    #: Lifecycle state of the product behind the row, from ``STATUSES``.
    status: str = "active"
    #: Where the product went, when it did not simply stay put: the successor
    #: platform of a ``rebranded`` row (required there), and an optional
    #: migration target for a ``deprecated`` or ``dead`` one.
    successor: str | None = None

    def __post_init__(self) -> None:
        if self.tier not in (1, 2, 3):
            raise ValueError(f"{self.agent}: tier must be 1, 2, or 3, got {self.tier!r}")
        if not self.agent:
            raise ValueError("agent must be non-empty")
        if self.status not in STATUSES:
            raise ValueError(
                f"{self.agent}: status must be one of {STATUSES}, got {self.status!r}"
            )
        if self.status == "rebranded" and not self.successor:
            raise ValueError(
                f"{self.agent}: a rebranded row must name its successor"
            )
        if self.status == "active" and self.successor:
            raise ValueError(
                f"{self.agent}: an active row has no successor ({self.successor!r})"
            )
        if self.tier in (1, 2) and not self.native and not self.renderer:
            raise ValueError(
                f"{self.agent}: tier {self.tier} requires a dedicated renderer"
            )
        if self.tier == 3 and self.renderer:
            raise ValueError(
                f"{self.agent}: tier 3 renders through the shared AGENTS.md floor"
            )

    @property
    def generates(self) -> bool:
        """False for a ``dead`` row: the product is gone, so nothing is emitted.

        ``native`` and ``generates`` are different reasons for the same
        outcome (no adapter output): a native host consumes the package
        directly, a dead product has no host left.  The generator keeps them
        apart so the two never share an error message.
        """
        return self.status != "dead"


# Tier 1 — full fidelity (skills + commands + MCP + hooks where supported).
# These agents have dedicated, committed snapshots verified by validate.py.
_TIER1: tuple[AgentRow, ...] = (
    AgentRow(agent="claude-code", tier=1, native=True),
    AgentRow(agent="codex", tier=1, renderer="codex"),
)

# Tier 2 — skills + MCP (commands degrade to documented prompt equivalents).
# ``windsurf`` is rebranded: the product was folded into Devin Local, so the
# row names where it went while still rendering for the surface that
# keeps the old name.  Nothing is added or removed here — a lifecycle
# annotation, not a breadth change (ADR-0045 2026-11-06 amendment).
_TIER2: tuple[AgentRow, ...] = (
    AgentRow(agent="cursor", tier=2, renderer="cursor"),
    AgentRow(agent="gemini-cli", tier=2, renderer="gemini-cli"),
    AgentRow(agent="opencode", tier=2, renderer="opencode"),
    AgentRow(
        agent="windsurf", tier=2, renderer="windsurf",
        status="rebranded", successor="devin",
    ),
    AgentRow(agent="github-copilot", tier=2, renderer="github-copilot"),
    AgentRow(agent="zed", tier=2, renderer="zed"),
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

# Lifecycle overrides for the Tier-3 floor, keyed by agent id.  Roo Code shut
# down (2026-05): keeping it on the floor would ship an adapter to a host that
# no longer exists, which is the false breadth S7 removes.
_LIFECYCLE: dict[str, dict[str, str]] = {
    "roo-code": {"status": "dead"},
}

_TIER3: tuple[AgentRow, ...] = tuple(
    AgentRow(agent=name, tier=3, **_LIFECYCLE.get(name, {}))
    for name in _TIER3_AGENTS
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
