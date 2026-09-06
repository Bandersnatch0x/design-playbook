"""Read-time capability and readiness projections.

The caller supplies facts already read from package inventory, gate outcomes,
adapter capability data, prerequisites, and trial records. This module only
normalizes those facts into an immutable receipt; it never reads or writes a
capability-state file.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ImplementationState = Literal["absent", "present", "unknown"]
ValidationState = Literal[
    "untested",
    "tested",
    "dogfooded",
    "trial-observed",
    "unknown",
]
AvailabilityState = Literal["local", "distributed", "unsupported", "unknown"]
PublicClaim = Literal[
    "stable",
    "experimental",
    "blocked-by-gate",
    "not-shipped",
]
FallbackKind = Literal["safe-path", "evidence-gap"]

_IMPLEMENTATION_VALUES = frozenset(("absent", "present", "unknown"))
_VALIDATION_VALUES = frozenset(
    ("untested", "tested", "dogfooded", "trial-observed", "unknown")
)
_AVAILABILITY_VALUES = frozenset(("local", "distributed", "unsupported", "unknown"))
_PUBLIC_CLAIM_VALUES = frozenset(
    ("stable", "experimental", "blocked-by-gate", "not-shipped")
)


class CapabilityReceiptError(ValueError):
    """Raised when source facts cannot be represented safely."""


@dataclass(frozen=True)
class CapabilitySourceFacts:
    """Facts joined from existing authorities at read time.

    ``public_claim`` is the claim supplied by the current package/gate/trial
    interpretation. The projection may downgrade it, but never upgrades
    incomplete facts to ``stable``.
    """

    capability: str
    implementation: ImplementationState | None = None
    validation: ValidationState | None = None
    availability: AvailabilityState | None = None
    entrypoint: str | None = None
    prerequisites: tuple[str, ...] = ()
    fallback: str | None = None
    evidence_gap: str | None = None
    public_claim: PublicClaim | None = None
    gate_blocked: bool = False


@dataclass(frozen=True)
class CapabilityStatus:
    """Independent readiness dimensions exposed to an operator."""

    implementation: ImplementationState
    validation: ValidationState
    availability: AvailabilityState
    public_claim: PublicClaim

    def to_dict(self) -> dict[str, str]:
        return {
            "implementation": self.implementation,
            "validation": self.validation,
            "availability": self.availability,
            "publicClaim": self.public_claim,
        }


@dataclass(frozen=True)
class FallbackProjection:
    """A safe continuation or an explicit evidence gap."""

    kind: FallbackKind
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "detail": self.detail}


@dataclass(frozen=True)
class CapabilityReceipt:
    """Immutable, read-time capability receipt."""

    capability: str
    status: CapabilityStatus
    entrypoint: str | None
    prerequisites: tuple[str, ...]
    fallback: FallbackProjection | None
    evidence_gap: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "capability": self.capability,
            "status": self.status.to_dict(),
            "entrypoint": self.entrypoint,
            "prerequisites": list(self.prerequisites),
            "fallback": self.fallback.to_dict() if self.fallback else None,
            "publicClaim": self.status.public_claim,
            "evidenceGap": self.evidence_gap,
        }


def _normalise_dimension(
    name: str,
    value: str | None,
    allowed: frozenset[str],
    unknown: str,
) -> str:
    if value is None:
        return unknown
    if not isinstance(value, str) or value not in allowed:
        raise CapabilityReceiptError(f"{name}-invalid")
    return value


def _normalise_text(name: str, value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise CapabilityReceiptError(f"{name}-invalid")
    return value.strip()


def _normalise_facts(facts: CapabilitySourceFacts) -> tuple[
    str,
    ImplementationState,
    ValidationState,
    AvailabilityState,
    str | None,
    tuple[str, ...],
    str | None,
    str | None,
    PublicClaim | None,
]:
    if not isinstance(facts, CapabilitySourceFacts):
        raise CapabilityReceiptError("source-facts-invalid")
    capability = _normalise_text("capability", facts.capability)
    if capability is None:
        raise CapabilityReceiptError("capability-invalid")
    if not isinstance(facts.prerequisites, tuple):
        raise CapabilityReceiptError("prerequisites-invalid")
    prerequisites: list[str] = []
    for prerequisite in facts.prerequisites:
        normalized = _normalise_text("prerequisite", prerequisite)
        if normalized is None:
            raise CapabilityReceiptError("prerequisite-invalid")
        prerequisites.append(normalized)
    public_claim = facts.public_claim
    if public_claim is not None and (
        not isinstance(public_claim, str)
        or public_claim not in _PUBLIC_CLAIM_VALUES
    ):
        raise CapabilityReceiptError("public-claim-invalid")
    if not isinstance(facts.gate_blocked, bool):
        raise CapabilityReceiptError("gate-blocked-invalid")
    return (
        capability,
        _normalise_dimension(
            "implementation", facts.implementation, _IMPLEMENTATION_VALUES, "unknown"
        ),
        _normalise_dimension(
            "validation", facts.validation, _VALIDATION_VALUES, "unknown"
        ),
        _normalise_dimension(
            "availability", facts.availability, _AVAILABILITY_VALUES, "unknown"
        ),
        _normalise_text("entrypoint", facts.entrypoint),
        tuple(prerequisites),
        _normalise_text("fallback", facts.fallback),
        _normalise_text("evidence-gap", facts.evidence_gap),
        public_claim,
    )


def _derive_public_claim(
    *,
    implementation: ImplementationState,
    validation: ValidationState,
    availability: AvailabilityState,
    requested: PublicClaim | None,
    gate_blocked: bool,
    entrypoint: str | None,
    supplied_gap: str | None,
) -> PublicClaim:
    if implementation != "present":
        return "not-shipped"
    if gate_blocked or requested == "blocked-by-gate":
        return "blocked-by-gate"
    if validation in ("unknown", "untested"):
        return "not-shipped"
    if availability in ("unknown", "unsupported"):
        return "not-shipped"
    if requested == "stable" and (
        validation not in ("dogfooded", "trial-observed")
        or entrypoint is None
        or supplied_gap is not None
    ):
        return "experimental"
    if requested is None:
        return "experimental"
    return requested


def build_capability_receipt(
    facts: CapabilitySourceFacts,
) -> CapabilityReceipt:
    """Project existing source facts into one safe, immutable receipt."""
    (
        capability,
        implementation,
        validation,
        availability,
        entrypoint,
        prerequisites,
        fallback_text,
        supplied_gap,
        requested_claim,
    ) = _normalise_facts(facts)
    public_claim = _derive_public_claim(
        implementation=implementation,
        validation=validation,
        availability=availability,
        requested=requested_claim,
        gate_blocked=facts.gate_blocked,
        entrypoint=entrypoint,
        supplied_gap=supplied_gap,
    )

    gaps: list[str] = []
    unknown_dimensions = tuple(
        name
        for name, value in (
            ("implementation", implementation),
            ("validation", validation),
            ("availability", availability),
        )
        if value == "unknown"
    )
    if unknown_dimensions:
        gaps.append("unknown readiness facts: " + ", ".join(unknown_dimensions))
    if entrypoint is None:
        gaps.append("entrypoint is not available")
    if implementation == "absent":
        gaps.append("capability is not implemented")
    if validation in ("untested", "unknown"):
        gaps.append("validation evidence is incomplete")
    if availability == "unsupported":
        gaps.append("surface is unsupported")
    if facts.gate_blocked or requested_claim == "blocked-by-gate":
        gaps.append("capability is blocked by gate")
    if requested_claim == "stable" and public_claim != "stable":
        gaps.append("stable public claim rejected by incomplete readiness evidence")
    if supplied_gap:
        gaps.append(supplied_gap)

    evidence_gap = "; ".join(dict.fromkeys(gaps)) or None
    fallback = None
    if fallback_text:
        fallback = FallbackProjection(kind="safe-path", detail=fallback_text)
    elif evidence_gap:
        fallback = FallbackProjection(kind="evidence-gap", detail=evidence_gap)

    return CapabilityReceipt(
        capability=capability,
        status=CapabilityStatus(
            implementation=implementation,
            validation=validation,
            availability=availability,
            public_claim=public_claim,
        ),
        entrypoint=entrypoint,
        prerequisites=prerequisites,
        fallback=fallback,
        evidence_gap=evidence_gap,
    )


