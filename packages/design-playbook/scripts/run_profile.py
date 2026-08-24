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

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field

RUN_PROFILE_MARKER = re.compile(r"<!--\s*run-profile(?::\s*v(\d+))?\s*-->")
FENCED_BLOCK = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.S)
TIERS = frozenset({"P1", "P2", "P3"})
SUPPORTED_RUN_PROFILE_VERSIONS = frozenset({1})
REQUEST_INTENTS = frozenset(
    {"answer", "review", "diagnose", "plan", "prototype", "build", "fix"}
)
REQUEST_CONSEQUENCES = frozenset({"none", "local", "feature", "structural"})
NO_RUN_INTENTS = frozenset({"answer", "review", "diagnose", "plan"})
NO_RUN_REASON = ("non-durable request does not require Design I/O artifacts",)
TIER_REASONS = {
    "P1": ("local fix has no full-tier trigger or decided-field addition",),
    "P2": ("request does not meet a P1 or P3 condition",),
    "P3": ("structural consequence, decided-field revision, or multi-domain work",),
}


@dataclass(frozen=True)
class RequestFacts:
    """Normalized facts used to choose whether a Design I/O run starts."""

    intent: str
    durable_design_artifacts: bool
    consequence: str
    existing_product: bool
    has_references: bool
    spec_present: bool
    baseline_ready: bool
    reference_contract_ready: bool
    adds_decided_fields: bool
    revises_decided_fields: bool
    declaration_domains: int


@dataclass(frozen=True)
class RouteDecision:
    """Initial Design I/O disposition and its run requirements."""

    mode: str
    tier: str | None
    requires_baseline: bool
    requires_reference_contract: bool
    requires_spec: bool
    criteria: tuple[str, ...]
    reasons: tuple[str, ...]


def _validate_request_facts(facts: RequestFacts) -> None:
    if not isinstance(facts.intent, str) or facts.intent not in REQUEST_INTENTS:
        raise ValueError(f"unknown request intent: {facts.intent!r}")
    if not isinstance(facts.consequence, str) or facts.consequence not in REQUEST_CONSEQUENCES:
        raise ValueError(f"unknown request consequence: {facts.consequence!r}")
    if isinstance(facts.declaration_domains, bool) or not isinstance(
        facts.declaration_domains, int
    ) or facts.declaration_domains < 0:
        raise ValueError("declaration_domains must be a non-negative integer")
    for name in (
        "durable_design_artifacts",
        "existing_product",
        "has_references",
        "spec_present",
        "baseline_ready",
        "reference_contract_ready",
        "adds_decided_fields",
        "revises_decided_fields",
    ):
        if not isinstance(getattr(facts, name), bool):
            raise ValueError(f"{name} must be boolean")
    if facts.intent == "build" and facts.consequence == "none":
        raise ValueError("contradictory request facts: build consequence cannot be none")
    if (
        facts.intent in NO_RUN_INTENTS
        and facts.consequence == "structural"
        and not facts.durable_design_artifacts
    ):
        raise ValueError(
            "contradictory request facts: non-durable structural work requires "
            "durable Design I/O artifacts"
        )


def _p3_criteria(facts: RequestFacts) -> tuple[str, ...]:
    criteria: list[str] = []
    if facts.consequence == "structural":
        criteria.append("consequence: structural")
    if facts.revises_decided_fields:
        criteria.append("decided-fields: revise")
    if facts.declaration_domains >= 2:
        criteria.append(f"declaration-domains: {facts.declaration_domains}")
    return tuple(criteria)


def _lower_tier_criteria(facts: RequestFacts, tier: str) -> tuple[str, ...]:
    criteria = [f"intent: {facts.intent}", f"consequence: {facts.consequence}"]
    if tier == "P1":
        criteria.append("decided-fields: unchanged")
        return tuple(criteria)
    if facts.adds_decided_fields:
        criteria.append("decided-fields: add")
    if facts.durable_design_artifacts:
        criteria.append("durable-artifacts: requested")
    return tuple(criteria)


def route_request(facts: RequestFacts) -> RouteDecision:
    """Route normalized facts through the single Design I/O entry seam."""
    _validate_request_facts(facts)
    if facts.intent in NO_RUN_INTENTS and not facts.durable_design_artifacts:
        return RouteDecision(
            mode="no-run",
            tier=None,
            requires_baseline=False,
            requires_reference_contract=False,
            requires_spec=False,
            criteria=(),
            reasons=NO_RUN_REASON,
        )

    requires_baseline = facts.existing_product and not facts.baseline_ready
    requires_reference_contract = facts.has_references and not facts.reference_contract_ready
    requires_spec = not facts.spec_present
    p3_criteria = _p3_criteria(facts)
    p3 = bool(p3_criteria)
    p1 = (
        facts.intent == "fix"
        and facts.consequence == "local"
        and not facts.adds_decided_fields
        and not p3
    )
    if p3:
        tier = "P3"
    elif p1:
        tier = "P1"
    else:
        tier = "P2"
    return RouteDecision(
        mode="design-run",
        tier=tier,
        requires_baseline=requires_baseline,
        requires_reference_contract=requires_reference_contract,
        requires_spec=requires_spec,
        criteria=(
            p3_criteria if tier == "P3" else _lower_tier_criteria(facts, tier)
        ),
        reasons=TIER_REASONS[tier],
    )


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
    if profile.version not in SUPPORTED_RUN_PROFILE_VERSIONS:
        errors.append(
            f"run-profile version v{profile.version} is unsupported; only v1 is accepted"
        )
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


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Design I/O run-profile utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)
    route = subparsers.add_parser("route", help="route normalized request facts")
    route.add_argument("--intent", required=True, choices=sorted(REQUEST_INTENTS))
    route.add_argument(
        "--consequence", required=True, choices=sorted(REQUEST_CONSEQUENCES)
    )
    route.add_argument("--durable-design-artifacts", action="store_true")
    route.add_argument("--existing-product", action="store_true")
    route.add_argument("--has-references", action="store_true")
    route.add_argument("--spec-present", action="store_true")
    route.add_argument("--baseline-ready", action="store_true")
    route.add_argument("--reference-contract-ready", action="store_true")
    route.add_argument("--adds-decided-fields", action="store_true")
    route.add_argument("--revises-decided-fields", action="store_true")
    route.add_argument("--declaration-domains", type=int, default=0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.command == "route":
        try:
            decision = route_request(
                RequestFacts(
                    intent=args.intent,
                    durable_design_artifacts=args.durable_design_artifacts,
                    consequence=args.consequence,
                    existing_product=args.existing_product,
                    has_references=args.has_references,
                    spec_present=args.spec_present,
                    baseline_ready=args.baseline_ready,
                    reference_contract_ready=args.reference_contract_ready,
                    adds_decided_fields=args.adds_decided_fields,
                    revises_decided_fields=args.revises_decided_fields,
                    declaration_domains=args.declaration_domains,
                )
            )
        except ValueError as exc:
            print(f"run_profile.py: error: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(asdict(decision), indent=2, sort_keys=True))
        return 0
    return 2  # argparse (required=True subparsers) never reaches here


if __name__ == "__main__":
    raise SystemExit(main())
