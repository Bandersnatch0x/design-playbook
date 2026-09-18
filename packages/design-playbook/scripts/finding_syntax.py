"""Single Point-back finding syntax-facts parser (ADR-0025 / ADR-0039).

This is the third syntax-facts module beside ``verdict_syntax`` (Verdict
section) and ``mcp/evidence/ledger_syntax`` (evidence ledger rows). It owns
the finding-paragraph sub-grammar of point-back text and applies no gate,
status, routing, or projection policy:

* the field-line grammar — the four required fields plus every additive
  annotation (track / confidence / disposition / evidence / assumes / rule /
  dd / dimension / face / basis / route / rounds / id / status);
* finding-paragraph segmentation — a blank-line separated block counts as a
  finding only when at least one required field is present, so an
  annotation-only block outside a finding never becomes one;
* the severity axis value domain (``S3 | S2 | S1 | S0``) and the removed
  legacy spellings, kept only so consumers can explain a rejection;
* the closure-trail line grammar and the issue-normalisation used to match a
  closure against the finding it closes.

Consumers (G2-G4, G12, repair rounds, escalation signals, interaction
dimensions, dd entries, learning candidates, and the Run Snapshot point-back
projection) all read these facts through this interface; before it existed
they imported the gate module's private names.
"""
from __future__ import annotations

import re

FINDING_FIELDS = ("issue", "source", "fix", "severity")
EXTRA_FINDING_FIELDS = (
    "track", "confidence", "disposition", "evidence", "assumes", "rule", "dd",
    # vNext S3 interaction-track annotations (review-prototype 1.2): the
    # dimension refinement plus its objective/subjective face and judgment
    # source. Validated by interaction_dimensions.py; parsed here so every
    # consumer sees the same field set.
    "dimension", "face", "basis",
    # vNext S4 recirculation annotations (loop-prototype 2.2 / 7.1): the
    # second-hop repair route (R1 | R2-line | R2-structural | R3 | R4 | R5,
    # multiple values legal for multi-layer findings) and the machine round
    # counter for blocking findings (rounds survived through repair +
    # re-evaluate). Validated by repair_rounds.py / escalation_signals.py /
    # g12_tier_boundary.py; parsed here so every consumer sees one field set.
    "route", "rounds",
    # Operator evidence hardening: stable finding identity and re-review
    # status. Additive; absence stays legal. G4 may close by id or issue.
    "id", "status",
)
FIELD_LINE = re.compile(
    r"^(issue|source|fix|severity|track|confidence|disposition|evidence|"
    r"assumes|rule|dd|dimension|face|basis|route|rounds|id|status):[ \t]*(.*)$",
    re.I | re.M)
CLOSURE_LINE = re.compile(
    r"^\s*[-*]\s*closes:[ \t]*(.*?)[ \t]*->[^\n]*\b0 blocking\b",
    re.I | re.M,
)

# Severity axis (review-prototype Q1). vNext S5 removed the legacy aliases
# (vnext-prototype Q5=B, two-stage migration complete): only S3|S2|S1|S0 are
# legal; the old spellings are structural errors.
SEVERITY_NEW = frozenset({"S3", "S2", "S1", "S0"})
SEVERITY_LEGACY = frozenset({"high (blocking)", "high", "med", "low"})
VALID_TRACKS = frozenset({"product", "interaction", "cross-cutting"})
VALID_CONFIDENCE = frozenset({"high", "medium", "low"})
VALID_DISPOSITIONS = frozenset({"blocking", "advisory", "info"})
VALID_FINDING_STATUSES = frozenset({"open", "resolved", "new", "regression"})


def severity_axis(value: str) -> str | None:
    """Map a severity value onto the axis; None when invalid.

    The exact axis spelling is required — the legacy aliases were removed
    in vNext S5 (they used to fold onto S3/S2/S1/S1 during the alias
    period).
    """
    stripped = value.strip()
    if stripped in SEVERITY_NEW:
        return stripped
    return None


def parse_findings(text: str) -> list[dict[str, list[str]]]:
    """Parse finding paragraphs without using a required field as delimiter.

    Additional-field-only blocks (e.g. a bare ``track:`` line outside a
    finding) do not count as findings — at least one of the four required
    fields must be present. Every field key is present in each result, so
    consumers index without ``get`` and see repeated lines in source order.
    """
    findings = []
    for block in re.split(r"\n\s*\n", text):
        matches = FIELD_LINE.findall(block)
        if not matches:
            continue
        fields = {field: [] for field in FINDING_FIELDS + EXTRA_FINDING_FIELDS}
        for name, value in matches:
            fields[name.lower()].append(value.strip())
        if not any(fields[field] for field in FINDING_FIELDS):
            continue
        findings.append(fields)
    return findings


def normalise_issue(value: str) -> str:
    """Case- and whitespace-insensitive issue identity for closure matching."""
    return " ".join(value.casefold().split())


def closure_targets(text: str) -> list[str]:
    """Normalised issue targets of every ``0 blocking`` closure trail line."""
    return [normalise_issue(target) for target in CLOSURE_LINE.findall(text)]


def finding_identities(parsed: dict[str, list[str]]) -> tuple[str, ...]:
    """Normalised identities a current ``closes:`` line may match.

    Issue text is always an identity when present. A non-empty ``id:`` is an
    additional identity. Empty ``id:`` values are ignored here; G2 reports
    them separately.
    """
    identities: list[str] = []
    issue_values = parsed.get("issue") or []
    if issue_values and issue_values[0].strip():
        identities.append(normalise_issue(issue_values[0]))
    id_values = parsed.get("id") or []
    if id_values and id_values[0].strip():
        ident = normalise_issue(id_values[0])
        if ident not in identities:
            identities.append(ident)
    return tuple(identities)


def finding_current_close_count(
    parsed: dict[str, list[str]], closed_targets: list[str] | tuple[str, ...]
) -> int:
    """How many current CLOSURE_LINE targets match this finding.

    Walks ``closed_targets`` in source order and **does not** uniquify first.
    Two ``closes: F-1`` lines, or one ``closes: F-1`` plus one ``closes:`` of
    the issue text, count as two matches. Pass requires exactly one.
    """
    identities = finding_identities(parsed)
    if not identities:
        return 0
    identity_set = set(identities)
    return sum(1 for target in closed_targets if target in identity_set)


def finding_is_currently_closed(
    parsed: dict[str, list[str]],
    closed_targets: list[str] | tuple[str, ...],
) -> bool:
    """True when exactly one current CLOSURE_LINE matches this finding."""
    return finding_current_close_count(parsed, closed_targets) == 1
