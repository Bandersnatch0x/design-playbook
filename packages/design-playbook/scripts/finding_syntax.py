"""Single Point-back finding syntax-facts parser (ADR-0025 / ADR-0039).

This is the third syntax-facts module beside ``verdict_syntax`` (Verdict
section) and ``mcp/evidence/ledger_syntax`` (evidence ledger rows). It owns
the finding-paragraph sub-grammar of point-back text and applies no gate,
status, routing, or projection policy:

* the field-line grammar — the four required fields plus every additive
  annotation (track / confidence / disposition / evidence / assumes / rule /
  dd / dimension / face / basis / route / rounds / id / status / criteria);
* finding-paragraph segmentation — a blank-line separated block counts as a
  finding only when at least one required field is present, so an
  annotation-only block outside a finding never becomes one;
* the severity axis value domain (``S3 | S2 | S1 | S0``) and the removed
  legacy spellings, kept only so consumers can explain a rejection;
* the closure-trail line grammar, the repair annotations indented under a
  closure, and the issue-normalisation used to match a closure against the
  finding it closes.

``criteria:`` is finding syntax, not ledger grammar: the Evidence ledger's
field set is ``criterion | required | observed | result``, so a finding's
declared L6 criteria live on their own additive field and never become a
ledger row. The values stay raw occurrences here - uniqueness, exact ``L6.<n>``
shape, and membership in the G1 set are G4 policy.

Consumers (G2-G4, G12, repair rounds, escalation signals, interaction
dimensions, dd entries, learning candidates, and the Run Snapshot point-back
projection) all read these facts through this interface; before it existed
they imported the gate module's private names.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

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
    # T-159: the declared L6 criteria a finding's repair obligation follows.
    # Additive and raw here; G4 validates exactness and membership.
    "criteria",
)
FIELD_LINE = re.compile(
    r"^(issue|source|fix|severity|track|confidence|disposition|evidence|"
    r"assumes|rule|dd|dimension|face|basis|route|rounds|id|status|criteria):"
    r"[ \t]*(.*)$",
    re.I | re.M)
# The closure-item head: a list bullet, whitespace (the historic expression
# tolerated a line break here), then ``closes:`` and its target. One fragment
# owns the item syntax; the expressions below only differ in what they do with
# the arrow trail.
_CLOSURE_ITEM_HEAD = r"^\s*[-*]\s*closes:[ \t]*(.*?)[ \t]*"
# The historic ``0 blocking`` projection, kept as the exported legacy name
# (ADR-0023). It matches only an item whose trail reports ``0 blocking``.
CLOSURE_LINE = re.compile(
    _CLOSURE_ITEM_HEAD + r"->[^\n]*\b0 blocking\b",
    re.I | re.M,
)
# Every closure item, whatever its trailing count. ``parse_closures`` scans
# this once: an item's bullet line ends the previous item's attachment, and
# an item whose arrow trail reports ``0 blocking`` projects as a closure. An
# item without an arrow tail is a boundary but never a closure.
_CLOSURE_ITEM = re.compile(
    _CLOSURE_ITEM_HEAD + r"(?:->(?P<trail>[^\n]*))?$",
    re.I | re.M,
)
_ZERO_BLOCKING = re.compile(r"\b0 blocking\b", re.I)
# A repair annotation line. Association with a closure is decided by
# ``parse_closures`` from indentation and adjacency, not by this pattern: a
# matching line without a belonging closure is kept as an orphan fact.
REPAIR_ANNOTATION_LINE = re.compile(
    r"^[ \t]*(?:[-*][ \t]+)?repair-evidence:[ \t]*(.*)$", re.I | re.M)
# One occurrence token: ``key=value`` with no whitespace inside. Whitespace
# separates occurrences, so ``a=1,b=2`` does not hide a key inside another
# token. The value may be empty (``before=``) - that is a malformed
# occurrence, not a missing one, and it stays observable rather than being
# dropped. Names are case-folded, values are preserved verbatim.
_REPAIR_FIELD_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
# An indented Markdown heading ends attachment too: the following annotation
# belongs to a different section, not to the eager closure above it.
_HEADING_LINE = re.compile(r"^[ \t]*#{1,6}(?:[ \t]|$)")
# The complete repair annotation grammar. Anything else is an unknown field
# fact; which fields are required is G4 policy.
REPAIR_FIELDS = ("criterion", "before", "after")

# Severity axis (review-prototype Q1). vNext S5 removed the legacy aliases
# (vnext-prototype Q5=B, two-stage migration complete): only S3|S2|S1|S0 are
# legal; the old spellings are structural errors.
SEVERITY_NEW = frozenset({"S3", "S2", "S1", "S0"})
SEVERITY_LEGACY = frozenset({"high (blocking)", "high", "med", "low"})
VALID_TRACKS = frozenset({"product", "interaction", "cross-cutting"})
VALID_CONFIDENCE = frozenset({"high", "medium", "low"})
VALID_DISPOSITIONS = frozenset({"blocking", "advisory", "info"})
VALID_FINDING_STATUSES = frozenset({"open", "resolved", "new", "regression"})


@dataclass(frozen=True)
class ClosureRepairField:
    """One ``key=value`` occurrence inside a repair annotation."""

    name: str
    value: str


@dataclass(frozen=True)
class ClosureRepairAnnotation:
    """One ``repair-evidence:`` line and its complete field occurrences.

    Duplicate keys and unknown keys stay in ``occurrences`` in source order;
    nothing folds to a first/last value. ``unconsumed`` keeps every
    whitespace-separated token outside the ``key=value`` grammar verbatim (a
    bare word, ``=value``), so malformed text remains visible instead of
    being silently dropped. Which fields are required, whether duplicates are
    legal, and whether an empty value or an unconsumed fragment is an error is
    G4 policy rather than syntax.
    """

    line: int
    occurrences: tuple[ClosureRepairField, ...]
    unconsumed: tuple[str, ...] = ()

    def values(self, name: str) -> tuple[str, ...]:
        """Every value written for ``name``, in occurrence order."""
        wanted = name.casefold()
        return tuple(
            field.value for field in self.occurrences if field.name == wanted)

    @property
    def unknown_fields(self) -> tuple[str, ...]:
        """Distinct names outside the annotation grammar, in first-seen order."""
        seen: list[str] = []
        for field in self.occurrences:
            if field.name not in REPAIR_FIELDS and field.name not in seen:
                seen.append(field.name)
        return tuple(seen)


@dataclass(frozen=True)
class ClosureFact:
    """One closure-trail line plus the annotations indented under it."""

    target: str
    identity: str
    line: int
    annotations: tuple[ClosureRepairAnnotation, ...]


@dataclass(frozen=True)
class ClosureFacts:
    """Per-closure facts plus annotations with no belonging closure."""

    closures: tuple[ClosureFact, ...]
    orphan_annotations: tuple[ClosureRepairAnnotation, ...]


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


def _repair_annotation(line_number: int, body: str) -> ClosureRepairAnnotation:
    """Split one annotation body into occurrences and unconsumed fragments."""
    occurrences: list[ClosureRepairField] = []
    unconsumed: list[str] = []
    for token in body.split():
        name, separator, value = token.partition("=")
        if separator and _REPAIR_FIELD_NAME.fullmatch(name):
            occurrences.append(ClosureRepairField(name.casefold(), value))
        else:
            unconsumed.append(token)
    return ClosureRepairAnnotation(
        line=line_number,
        occurrences=tuple(occurrences),
        unconsumed=tuple(unconsumed),
    )


def _indent(line: str) -> int:
    """Column of the first non-whitespace character (tab stops expanded)."""
    expanded = line.expandtabs()
    return len(expanded) - len(expanded.lstrip())


def _item_anchor(text: str, match: re.Match[str]) -> tuple[int, int]:
    """Zero-based bullet line and bullet column of one closure item.

    The historic expression allows the bullet and ``closes:`` to sit on
    different lines, so the item's indentation comes from the marker's column,
    not the keyword's.
    """
    matched = match.group(0)
    bullet = match.start() + len(matched) - len(matched.lstrip())
    line_start = text.rfind("\n", 0, bullet) + 1
    return text.count("\n", 0, bullet), _indent(text[line_start:bullet])


def parse_closures(text: str) -> ClosureFacts:
    """Parse closure trails and the repair annotations indented under them.

    One ``_CLOSURE_ITEM`` scan yields every closure item, whatever its
    trailing count. An item's bullet line is the boundary that ends the
    previous item's attachment; its arrow trail decides whether the item
    projects as a ``ClosureFact`` (the historic ``0 blocking`` rule). A closure
    owns only the ``repair-evidence:`` lines that follow it before a blank
    line, the next item's bullet, a heading, or any line indented no deeper
    than its own list marker. Indented continuation lines that are not
    annotations belong to the item and do not end it. An annotation with no
    belonging closure is kept in ``orphan_annotations``; it is never borrowed
    by another closure.

    A bullet on one line and ``closes:`` on the next keeps its original
    projection. ``ClosureFact.line`` is the 1-based line of the ``closes:``
    token (where the target is written); an annotation's ``line`` is likewise
    1-based.
    """
    lines = text.split("\n")
    items = list(_CLOSURE_ITEM.finditer(text))
    anchors = [_item_anchor(text, item) for item in items]
    closures: list[ClosureFact] = []
    attached: set[int] = set()
    for index, item in enumerate(items):
        trail = item.group("trail")
        if trail is None or _ZERO_BLOCKING.search(trail) is None:
            continue
        target_line = text.count("\n", 0, item.start(1))
        item_indent = anchors[index][1]
        next_item_line = (
            anchors[index + 1][0] if index + 1 < len(anchors) else None)
        annotations: list[ClosureRepairAnnotation] = []
        cursor = target_line + 1
        while cursor < len(lines):
            if next_item_line is not None and cursor >= next_item_line:
                break
            line = lines[cursor]
            if not line.strip():
                break
            if _HEADING_LINE.match(line):
                break
            if _indent(line) <= item_indent:
                break
            annotation_match = REPAIR_ANNOTATION_LINE.match(line)
            if annotation_match is not None:
                annotations.append(
                    _repair_annotation(cursor + 1, annotation_match.group(1)))
                attached.add(cursor)
            cursor += 1
        closures.append(ClosureFact(
            target=item.group(1).strip(),
            identity=normalise_issue(item.group(1)),
            line=target_line + 1,
            annotations=tuple(annotations),
        ))
    orphans: list[ClosureRepairAnnotation] = []
    for position, line in enumerate(lines):
        if position in attached:
            continue
        match = REPAIR_ANNOTATION_LINE.match(line)
        if match is not None:
            orphans.append(_repair_annotation(position + 1, match.group(1)))
    return ClosureFacts(tuple(closures), tuple(orphans))


def closure_targets(text: str) -> list[str]:
    """Normalised issue targets of every ``0 blocking`` closure trail line.

    Projection over :func:`parse_closures`; the values and source order are
    unchanged for existing consumers.
    """
    return [closure.identity for closure in parse_closures(text).closures]


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


def closure_target_candidates(
    findings: list[dict[str, list[str]]], target: str
) -> tuple[int, ...]:
    """Indices of findings whose issue or id identity equals ``target``.

    Ambiguity is preserved as data rather than resolved here: two indices can
    mean two findings share one issue, or one finding's ``id`` collides with
    another finding's ``issue``. G4 decides whether a closure with several
    candidates is invalid.
    """
    identity = normalise_issue(target)
    return tuple(
        index for index, parsed in enumerate(findings)
        if identity in finding_identities(parsed)
    )


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
