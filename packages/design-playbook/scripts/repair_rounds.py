"""Repair-round machine counting (vNext S4, loop-prototype 2.2 / 5.1).

The orchestrator's two-cycle stop policy — "the same blocking finding
through two repair -> re-evaluate rounds without new evidence stops the
recirculation and reports" — was agent-enforced. S4 machines the countable
face; the verdict value domain stays ``Pass | Recirculate`` (#32-Q4=A), so
the stop is narrated, never a third verdict value:

- ``rounds: N`` on a finding — repair rounds that finding has survived
  (0 = fresh, 2 = two repairs re-evaluated, still open);
- ``round: N`` inside an ``invalidated:`` entry — which repair round
  invalidated that evidence (loop-prototype 2.2: "closure/invalidated
  round annotations" are the machine-checkable face);
- ``close_reason: pass | escalated-stop | aborted`` in the Verdict section
  — the terminal narration. ``escalated-stop`` means the run stopped at
  the two-round budget and waits on the user disposition (revise the
  owning declaration / accept the risk and record / keep suspended).

Machine policy (``G4.round_*`` rule ids, wired after G2-G4):

- an unclosed blocking finding at ``rounds >= 2`` must declare
  ``close_reason: escalated-stop`` (the stop is mandatory, not optional);
- an escalated-stop narration must rest on such a finding (no orphan
  stops) and never co-exists with a Pass verdict (after the user
  disposition the run closes through the normal closure -> Pass chain and
  the close_reason becomes ``pass``);
- round values are non-negative integers (findings) / positive integers
  (invalidated entries).

Reports without round annotations and without a close_reason line do not
trigger the gate (legacy reports keep passing; the machine face is
additive). The one-round repair -> closure -> Pass chain is untouched.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from design_playbook.scripts._diagnostics import Finding, finding
from design_playbook.scripts.g2_g4_pointback import (
    CLOSURE_LINE,
    _findings,
    _normalise_issue,
)
from design_playbook.scripts.verdict_syntax import VerdictFacts, parse_verdict

# The two-cycle stop budget (loop-prototype 5.1 / orchestrator SKILL.md).
TWO_ROUND_STOP = 2

# Terminal narration values (#32-Q4=A: narration state, not a verdict value).
CLOSE_REASONS = frozenset({"pass", "escalated-stop", "aborted"})

_VERDICT_HEADING = re.compile(r"^#+\s*Verdict\s*$", re.I | re.M)
_NEXT_HEADING = re.compile(r"^#+\s+", re.M)
_CLOSE_REASON_LINE = re.compile(r"^close_reason:\s*(\S+)", re.I | re.M)
_INVALIDATED_BLOCK = re.compile(r"^invalidated:\s*$", re.M)
_INVALIDATED_ROUND = re.compile(r"^\s+round:\s*(\S+)\s*$", re.M)


@dataclass(frozen=True)
class RoundFacts:
    """One immutable view of the round annotations in a point-back report."""

    # (issue, rounds) for every finding carrying a rounds annotation.
    rounds_by_issue: tuple[tuple[str, int], ...]
    # round values annotated on invalidated: entries.
    invalidated_rounds: tuple[int, ...]
    close_reason: str | None
    max_rounds: int


def _verdict_body(text: str) -> str:
    heading = _VERDICT_HEADING.search(text)
    if heading is None:
        return ""
    rest = text[heading.end():]
    nxt = _NEXT_HEADING.search(rest)
    return rest[:nxt.start()] if nxt else rest


def parse_close_reason(text: str) -> str | None:
    """The close_reason narration value, or None when not declared."""
    match = _CLOSE_REASON_LINE.search(_verdict_body(text))
    return match.group(1).casefold() if match else None


def _invalidated_text(text: str) -> str:
    marker = _INVALIDATED_BLOCK.search(text)
    if marker is None:
        return ""
    rest = text[marker.end():]
    nxt = _NEXT_HEADING.search(rest)
    return rest[:nxt.start()] if nxt else rest


def is_blocking(parsed: dict[str, list[str]]) -> bool:
    """Blocking disposition: legacy severity spelling or the new axis."""
    severity = parsed["severity"][0] if parsed["severity"] else ""
    legacy_blocking = bool(re.search(r"(?<!non-)\bblocking\b", severity, re.I))
    disposition = (
        parsed["disposition"][0].strip().casefold()
        if parsed["disposition"] else ""
    )
    return legacy_blocking or disposition == "blocking"


def parse_round_facts(text: str) -> RoundFacts:
    """Collect round annotations without applying policy."""
    rounds_by_issue: list[tuple[str, int]] = []
    max_rounds = 0
    for parsed in _findings(text):
        values = parsed.get("rounds", [])
        if not values:
            continue
        issue = parsed["issue"][0] if parsed["issue"] else ""
        try:
            count = int(values[0].strip())
        except ValueError:
            count = -1
        rounds_by_issue.append((issue, count))
        if count > max_rounds:
            max_rounds = count
    invalidated: list[int] = []
    for value in _INVALIDATED_ROUND.findall(_invalidated_text(text)):
        try:
            invalidated.append(int(value))
        except ValueError:
            invalidated.append(-1)
    if invalidated and max(invalidated) > max_rounds:
        max_rounds = max(invalidated)
    return RoundFacts(
        rounds_by_issue=tuple(rounds_by_issue),
        invalidated_rounds=tuple(invalidated),
        close_reason=parse_close_reason(text),
        max_rounds=max_rounds,
    )


def has_round_face(facts: RoundFacts) -> bool:
    """True when the report carries any S4 round annotation."""
    return bool(facts.rounds_by_issue) or facts.close_reason is not None


def check_rounds(
        text: str,
        verdict_facts: VerdictFacts | None = None) -> list[Finding]:
    """Return G4 round findings (empty = pass or gate not triggered)."""
    facts = parse_round_facts(text)
    if not has_round_face(facts):
        return []

    errs: list[Finding] = []

    # close_reason enum (only when the line exists).
    if facts.close_reason is not None and facts.close_reason not in CLOSE_REASONS:
        errs.append(finding(
            "G4.close_reason_invalid",
            f"G4 rounds: close_reason {facts.close_reason!r} not in "
            "pass|escalated-stop|aborted",
            owner="point-back.md#Verdict",
            expected="pass|escalated-stop|aborted",
            actual=facts.close_reason,
            repair="Narrate the terminal reason with a value from the enum "
                   "(narration state, never a third verdict value)",
        ))

    # Round values: findings non-negative integers, invalidated positive.
    for issue, count in facts.rounds_by_issue:
        if count < 0:
            errs.append(finding(
                "G4.rounds_invalid",
                "G4 rounds: finding rounds annotation is not a non-negative "
                f"integer (issue {issue!r})",
                owner="point-back.md#findings",
                expected="rounds: <non-negative integer>",
                actual="not an integer",
                repair="Annotate the count of repair rounds the finding "
                       "has survived",
            ))
    if any(value < 1 for value in facts.invalidated_rounds):
        errs.append(finding(
            "G4.rounds_invalid",
            "G4 rounds: invalidated entry round annotation is not a "
            "positive integer",
            owner="point-back.md#invalidated",
            expected="round: <positive integer>",
            actual="not a positive integer",
            repair="Annotate which repair round invalidated the evidence "
                   "set entry",
        ))

    # Two-round stop: an unclosed blocking finding at rounds >= 2 must be
    # narrated as escalated-stop (the stop then waits on the user).
    closure_targets = {
        _normalise_issue(target) for target in CLOSURE_LINE.findall(text)
    }
    stopping: list[str] = []
    for parsed in _findings(text):
        values = parsed.get("rounds", [])
        if not values or not is_blocking(parsed):
            continue
        try:
            count = int(values[0].strip())
        except ValueError:
            continue
        if count < TWO_ROUND_STOP:
            continue
        issue = parsed["issue"][0] if parsed["issue"] else ""
        if _normalise_issue(issue) in closure_targets:
            continue  # closed on a later round: the normal chain, no stop
        stopping.append(issue)
    if stopping and facts.close_reason != "escalated-stop":
        first = stopping[0]
        errs.append(finding(
            "G4.round_stop_missing",
            f"G4 rounds: blocking finding {first!r} survived two repair "
            "rounds without closing — stop the recirculation and narrate "
            "close_reason: escalated-stop (verdict stays Recirculate)",
            owner="point-back.md#Verdict",
            expected="close_reason: escalated-stop + user disposition",
            actual="stop not narrated",
            repair="Stop repairing; request the user disposition (revise "
                   "the owning declaration / accept the risk and record / "
                   "keep suspended)",
        ))
    if not stopping and facts.close_reason == "escalated-stop":
        errs.append(finding(
            "G4.round_stop_orphan",
            "G4 rounds: close_reason escalated-stop without an unclosed "
            "blocking finding at two rounds",
            owner="point-back.md#Verdict",
            expected="a blocking finding with rounds >= 2 and no closure",
            actual="no stopping finding",
            repair="Drop the escalated-stop narration or record the "
                   "finding's round count",
        ))

    # A two-round stop never co-exists with Pass: after the user
    # disposition the run closes through closure -> Pass with close_reason
    # pass (accept-risk closures ride the normal G4 closure line).
    verdict = verdict_facts or parse_verdict(text)
    if verdict.canonical == "pass" and facts.close_reason == "escalated-stop":
        errs.append(finding(
            "G4.round_stop_pass_conflict",
            "G4 rounds: Pass verdict with close_reason escalated-stop (the "
            "stop is a waiting state; a closed run narrates pass)",
            owner="point-back.md#Verdict",
            expected="close_reason: pass on a closed run",
            actual="close_reason: escalated-stop",
            repair="After the user disposition, close via the closure -> "
                   "Pass chain and set close_reason: pass",
        ))
    return errs
