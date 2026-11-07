"""First-party UX rule registry parsing and G8 self-checks.

One canonical module shared by both G8 levels (vNext S3): the product-level
self-check (repo ``scripts/validate.py``) and the run-level coverage gate
(``g8_run_registry.py``) consume the same entry parsing and row validation.
Owns exactly the machine-checkable face declared in
``skills/design-playbook/references/rules.md``:

- entry parsing: ``## <ID> — <title>`` heading + one fenced field block
- enum / format / reference checks (rules-prototype §8.2, decision Q6=A)
- seven-column craft audit row parsing for the migrated fixtures

Validation errors are :class:`RegistryError` values: ``str`` subclasses
carrying the historical message plus the structured face (``rule`` /
``expected`` / ``actual`` / ``repair``, review advisory R4) that the
run-level G8 gate lifts into its findings.

Protocol-face fields (statement wording, signal quality, fix quality) are
intentionally not judged here.
"""
from __future__ import annotations

import importlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

try:  # package import seam (design_playbook.* context)
    from design_playbook.scripts import rules_governance
except ImportError:  # standalone product-level import (scripts/validate.py
    import rules_governance  # puts only this scripts/ dir on sys.path)

RULES_PATH_PARTS = (
    "skills", "design-playbook", "references", "rules.md"
)

ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*-[0-9]{2}$")
ENTRY_HEADING = re.compile(r"^## ([A-Z][A-Z0-9]*-[0-9]{2})\b", re.M)
FIELD_LINE = re.compile(r"^([a-z][a-z0-9-]*):[ \t]*(.*)$", re.M)

# V-4 limits. Kept here so the product-level gate and the layout-aware
# measurement read the same numbers; the registry header states the clause.
SPLIT_ENTRY_LIMIT = 30
SPLIT_GROUP_LIMIT = 3

# An index declares its physical parts and the global entry order in one
# fenced block. The info string is the marker; plain rule entries never use it.
INDEX_FENCE = re.compile(r"```registry-index[ \t]*\n(.*?)```", re.S)
INDEX_OPEN = re.compile(r"```registry-index[ \t]*(?:\n|$)")
INDEX_PART_LINE = re.compile(r"^part:[ \t]*(\S.*?)[ \t]*$", re.M)
INDEX_ORDER_LINE = re.compile(r"^order:[ \t]*(.+?)[ \t]*$", re.M)
INDEX_SCHEMA_LINE = re.compile(r"^schemaVersion:[ \t]*(\S.*?)[ \t]*$", re.M)
INDEX_KNOWN_PREFIXES = ("schemaVersion:", "part:", "order:")


class RegistryError(str):
    """One registry validation error (structured, review advisory R4).

    A ``str`` subclass so every historical consumer keeps working verbatim
    (``startswith`` prefix filtering in ``scripts/validate.py``, ``join``,
    substring membership, equality with ``[]``) while the same diagnostics
    grow the structured face the Finding-model gates (G10-G12) already
    use: which rule failed, what was expected, what was seen, and how to
    repair it. Fields are deliberately optional — a site may leave
    ``repair`` empty when the historical message already embeds the fix.
    """
    rule: str
    expected: str
    actual: str
    repair: str

    def __new__(cls, message: str, *, rule: str = "", expected: str = "",
                actual: str = "", repair: str = "") -> "RegistryError":
        self = super().__new__(cls, message)
        self.rule = rule
        self.expected = expected
        self.actual = actual
        self.repair = repair
        return self

    def to_dict(self) -> dict[str, str]:
        return {
            "message": str(self),
            "rule": self.rule,
            "expected": self.expected,
            "actual": self.actual,
            "repair": self.repair,
        }


class RegistryLayoutError(Exception):
    """The registry cannot be loaded from its declared layout (fail closed)."""

CAPABILITY_DOMAINS = frozenset(f"D{i}" for i in range(1, 9))
EXECUTES_IN = frozenset({
    "D4:product", "D4:interaction", "D4:cross-cutting", "registry-only",
})
AUTHORITIES = frozenset({
    "hard-constraint", "project-declaration", "platform-convention",
    "measured-threshold", "usability-heuristic", "advisory-aesthetic",
})
EVIDENCE_METHODS = frozenset({
    "expert-review", "runtime-observation", "static-inspection",
    "machine-measurement",
})
PROVENANCES = frozenset({
    "first-party", "promoted-from-findings", "placeholder",
    "benchmark-input-only",
})
STATUSES = frozenset({"draft", "advisory", "machine-enforced", "deprecated"})
CHECK_TYPES = frozenset({"machine-detector", "protocol-check"})
EVIDENCE_LAYERS = frozenset({
    "source", "rendered", "interaction", "measurement", "decision",
})
# Authority -> (allowed severity levels, required class or "" for any).
# hard-constraint and measured-threshold are facts; taste and convention never
# reach S3. The registry header states the same mapping in prose.
AUTHORITY_SEVERITY = {
    "hard-constraint": (frozenset({"S2", "S3"}), "fact"),
    "measured-threshold": (frozenset({"S1", "S2", "S3"}), "fact"),
    "project-declaration": (frozenset({"S1", "S2", "S3"}), ""),
    "platform-convention": (frozenset({"S1", "S2"}), ""),
    "usability-heuristic": (frozenset({"S1", "S2"}), ""),
    "advisory-aesthetic": (frozenset({"S0", "S1", "S2"}), "judgment"),
}
THRESHOLD_OPS = (">=", "<=", "=")
THRESHOLD_UNITS = (":1", "px", "ms", "s", "%", "count")
THRESHOLD_TERM = re.compile(
    r"^([a-z][a-z0-9-]*)\s*(>=|<=|=)\s*([0-9]+(?:\.[0-9]+)?)(:1|px|ms|s|%|count)$"
)


@dataclass(frozen=True)
class Threshold:
    """One parsed ``<term> <op> <number><unit>`` clause."""

    term: str
    op: str
    value: float
    unit: str


def parse_threshold(value: str) -> tuple[dict[str, Threshold], list[str]]:
    """Parse a ``threshold`` field into terms, plus the problems found.

    Syntax: ``<term> <op> <number><unit>; ...`` with op in ``>= <= =`` and
    unit in ``:1 px ms s % count``. A term appears once.
    """
    terms: dict[str, Threshold] = {}
    problems: list[str] = []
    for clause in value.split(";"):
        clause = clause.strip()
        if not clause:
            continue
        match = THRESHOLD_TERM.match(clause)
        if not match:
            problems.append(f"unparseable clause {clause!r}")
            continue
        term, op, number, unit = match.groups()
        if term in terms:
            problems.append(f"duplicate term {term!r}")
            continue
        terms[term] = Threshold(term, op, float(number), unit)
    if not terms and not problems:
        problems.append("empty threshold")
    return terms, problems


def threshold(entries: list["RuleEntry"], entry_id: str, term: str) -> Threshold:
    """Read one threshold term from the registry: the single source for gates."""
    for entry in entries:
        if entry.id == entry_id:
            terms, problems = parse_threshold(entry.fields.get("threshold", ""))
            if problems:
                raise ValueError(f"{entry_id}: {'; '.join(problems)}")
            if term not in terms:
                raise KeyError(f"{entry_id} has no threshold term {term!r}")
            return terms[term]
    raise KeyError(f"unknown registry id {entry_id!r}")


SEVERITY_PATTERN = re.compile(r"^(S[0-3])(?:\s*/\s*(fact|judgment))?$")
# Owner first hop = recirculate-map artifact names + the bound-baseline path.
OWNER_FIRST_HOPS = frozenset({
    "spec", "domain", "craft", "design", "components", "template",
    "native-craft", "reference", "baseline",
})
OWNER_SECOND_HOPS = frozenset(f"R{i}" for i in range(1, 6))

APPLICABILITY_KEYS = (
    "applicability-applicable",
    "applicability-not-applicable",
    "applicability-blocked",
)
REQUIRED_KEYS = (
    "id",
    "version",
    "capability-domain",
    "executes-in",
    "authority",
    "check-type",
    "evidence-layers",
    "severity-default",
    "owner",
    "provenance",
    "status",
    # Protocol face: its wording is a reviewer's call, but an entry without
    # a statement, a fix, its exceptions, its known false positives or the way
    # it is evidenced cannot be applied or argued with.
    "statement",
    "fix",
    "exceptions",
    "false-positives",
    "evidence-method",
) + APPLICABILITY_KEYS

# The seven-column audit row (craft migration, rules-prototype §6.2):
# | ID@ver | Applicability | Predicate reason / missing proof | Result |
#   | Rendered evidence | Source evidence | Exception check | Positive fix |
SEVEN_COL_ROW = re.compile(
    r"^\| ([A-Z][A-Z0-9]*-[0-9]{2}@[0-9]+) \| (applicable|not-applicable|blocked) "
    r"\| ([^|]*) \| (clear|hit|-) \| ([^|]*) \| ([^|]*) \| ([^|]*) \| ([^|]*) \|$",
    re.M,
)
# Contrast fixtures carry a leading Case column before the same seven columns.
CONTRAST_ROW = re.compile(
    r"^\| ([^|]+) \| ([A-Z][A-Z0-9]*-[0-9]{2}@[0-9]+) \| (applicable|not-applicable|blocked) "
    r"\| ([^|]*) \| (clear|hit|-) \| ([^|]*) \| ([^|]*) \| ([^|]*) \| ([^|]*) \|$",
    re.M,
)
APPLICABILITY_VALUES = frozenset({"applicable", "not-applicable", "blocked"})


@dataclass
class RuleEntry:
    """One parsed registry entry (machine face + raw protocol text)."""

    id: str
    fields: dict[str, str] = field(default_factory=dict)
    #: Part file the entry was read from ("" for a bare ``parse_registry``
    #: call). The split measurement derives the physical layout from it; the
    #: pure parser never fills it.
    source: str = ""

    @property
    def version(self) -> int:
        try:
            return int(self.fields.get("version", "0"))
        except ValueError:
            return 0

    @property
    def provenance(self) -> str:
        return self.fields.get("provenance", "")

    @property
    def status(self) -> str:
        return self.fields.get("status", "")


def _entry_blocks(text: str) -> list[tuple[str, str]]:
    """Split the registry into (id, body) blocks by entry heading."""
    matches = list(ENTRY_HEADING.finditer(text))
    blocks: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks.append((match.group(1), text[match.start():end]))
    return blocks


def _fenced_block(body: str) -> str:
    """Return the first fenced block inside an entry body ("" if absent)."""
    match = re.search(r"```[a-zA-Z]*\n(.*?)```", body, re.S)
    return match.group(1) if match else ""


def parse_registry(text: str) -> list[RuleEntry]:
    """Parse registry entries into RuleEntry objects (no validation).

    Pure text parsing: it never opens a file and never resolves a split
    layout. Use :func:`load_registry` when a path is available and the
    registry may be an index over part files.
    """
    entries: list[RuleEntry] = []
    for entry_id, body in _entry_blocks(text):
        block = _fenced_block(body)
        fields = {
            match.group(1): match.group(2).strip()
            for match in FIELD_LINE.finditer(block)
        }
        entries.append(RuleEntry(id=entry_id, fields=fields))
    return entries


@dataclass(frozen=True)
class RegistryIndex:
    """The physical layout an index file declares."""

    parts: tuple[str, ...]
    order: tuple[str, ...]


def _index_error(message: str, repair: str) -> RegistryLayoutError:
    return RegistryLayoutError(f"{message} (repair: {repair})")


def parse_index(text: str) -> RegistryIndex | None:
    """Parse the ``registry-index`` block; ``None`` for a single-file registry."""
    blocks = INDEX_FENCE.findall(text)
    openings = INDEX_OPEN.findall(text)
    if not openings:
        return None
    if len(openings) != len(blocks):
        raise _index_error(
            f"registry-index fence is not closed ({len(openings)} opening, "
            f"{len(blocks)} closed)",
            "Close the registry-index block with ```",
        )
    if len(blocks) > 1:
        raise _index_error(
            f"index carries {len(blocks)} registry-index blocks; exactly one "
            "is allowed",
            "Keep one registry-index block and list every part in it",
        )
    parts: list[str] = []
    order: tuple[str, ...] = ()
    schema = ""
    for raw_line in blocks[0].splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if not line.startswith(INDEX_KNOWN_PREFIXES):
            raise _index_error(
                f"registry-index line {line!r} is not schemaVersion/part/order",
                "Remove unknown manifest lines",
            )
        if line.startswith("part:"):
            match = INDEX_PART_LINE.match(line)
            if not match:
                raise _index_error(
                    "registry-index part line has no path",
                    "Write 'part: <relative .md path>'",
                )
            parts.append(match.group(1))
        elif line.startswith("order:"):
            if order:
                raise _index_error(
                    "registry-index declares more than one order line",
                    "Keep a single order line with every entry id",
                )
            match = INDEX_ORDER_LINE.match(line)
            if not match:
                raise _index_error(
                    "registry-index order line is empty",
                    "List every entry id on the order line",
                )
            order = tuple(
                token for token in re.split(r"[,\s]+", match.group(1)) if token
            )
        else:
            match = INDEX_SCHEMA_LINE.match(line)
            if not match:
                raise _index_error(
                    "registry-index schemaVersion line is empty",
                    "Write 'schemaVersion: 1'",
                )
            schema = match.group(1)
    if schema != "1":
        raise _index_error(
            f"registry-index schemaVersion is {schema!r}, expected '1'",
            "Write 'schemaVersion: 1'",
        )
    if not parts:
        raise _index_error(
            "registry-index lists no parts",
            "List each part file under the index",
        )
    if not order:
        raise _index_error(
            "registry-index lists no entry order",
            "List every entry id on the order line",
        )
    return RegistryIndex(tuple(parts), order)


def _resolve_part(index_path: Path, relative: str) -> Path:
    """Resolve one part path under the index's directory (no escapes)."""
    part = Path(relative)
    if part.is_absolute():
        raise _index_error(
            f"registry part {relative!r} is absolute",
            "Use a path relative to the index file",
        )
    resolved = (index_path.parent / part).resolve()
    if not resolved.is_relative_to(index_path.parent.resolve()):
        raise _index_error(
            f"registry part {relative!r} escapes the index directory",
            "Keep part paths inside the index directory",
        )
    if not resolved.is_file():
        raise _index_error(
            f"registry part {relative!r} is missing",
            "Create the part file or remove it from the index",
        )
    return resolved


def _read_layout(
    path: Path,
) -> tuple[str, RegistryIndex | None, list[tuple[str, Path]]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise _index_error(
            f"registry {path} is unreadable: {exc}",
            "Ship the registry index alongside its parts",
        ) from exc
    index = parse_index(text)
    if index is None:
        return text, None, []
    parts = [(relative, _resolve_part(path, relative)) for relative in index.parts]
    return text, index, parts


def _ordered_entries(
    index: RegistryIndex,
    parts: list[tuple[str, Path]],
) -> dict[str, RuleEntry]:
    """Parse every part and return entries keyed by id (validated layout)."""
    by_id: dict[str, RuleEntry] = {}
    for relative, part_path in parts:
        try:
            part_text = part_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise _index_error(
                f"registry part {relative!r} is unreadable: {exc}",
                "Ship every part named by the index",
            ) from exc
        part_entries = parse_registry(part_text)
        if not part_entries:
            raise _index_error(
                f"registry part {relative!r} carries no rule entries",
                "Remove the empty part from the index or write its entries",
            )
        for entry in part_entries:
            if entry.id in by_id:
                raise _index_error(
                    f"registry part {relative!r} repeats entry {entry.id}",
                    "Keep each entry in exactly one part",
                )
            entry.source = relative
            by_id[entry.id] = entry
    seen_order: set[str] = set()
    for entry_id in index.order:
        if entry_id in seen_order:
            raise _index_error(
                f"registry-index order repeats {entry_id}",
                "List each entry id once",
            )
        seen_order.add(entry_id)
    unknown = [entry_id for entry_id in index.order if entry_id not in by_id]
    omitted = [entry_id for entry_id in by_id if entry_id not in seen_order]
    if unknown:
        raise _index_error(
            f"registry-index order names {len(unknown)} unknown id(s): "
            + ", ".join(unknown[:5]),
            "List exactly the ids the parts carry",
        )
    if omitted:
        raise _index_error(
            f"registry-index order omits {len(omitted)} registered id(s): "
            + ", ".join(omitted[:5]),
            "Add the missing ids to the order line",
        )
    return by_id


def load_registry(path: Path) -> list[RuleEntry]:
    """Load the registry from an explicit path, index or single file.

    An index resolves its parts relative to itself and returns entries in the
    index's declared global order; a plain registry file parses as before.
    Every layout defect (missing part, duplicate id, order omission/extra,
    path escape, index carrying entries) raises :class:`RegistryLayoutError`
    instead of yielding a partial or empty registry.
    """
    path = Path(path)
    text, index, parts = _read_layout(path)
    if index is None:
        entries = parse_registry(text)
        for entry in entries:
            entry.source = path.name
        return entries
    if _entry_blocks(text):
        raise _index_error(
            f"registry index {path.name} carries rule entries; entries live "
            "in its parts",
            "Move the entry blocks into the parts listed by the index",
        )
    by_id = _ordered_entries(index, parts)
    return [by_id[entry_id] for entry_id in index.order]


def load_registry_text(path: Path) -> str:
    """Return the registry as one text in declared order (lint / test seam).

    For a single-file registry this is the file text unchanged. For an index
    it is the index prose followed by its entry blocks in the declared global
    order, so a text-level consumer sees the same entries a caller of
    :func:`load_registry` sees.
    """
    path = Path(path)
    text, index, parts = _read_layout(path)
    if index is None:
        return text
    _ordered_entries(index, parts)
    blocks: dict[str, str] = {}
    for relative, part_path in parts:
        for entry_id, body in _entry_blocks(part_path.read_text(encoding="utf-8")):
            blocks[entry_id] = body
    return text.rstrip() + "\n\n" + "".join(
        blocks[entry_id] for entry_id in index.order
    )


def registry_split_errors(entries: list[RuleEntry]) -> list[str]:
    """V-4: the registry's split clause, measured against the real layout.

    A registry is *single-file* when every entry came from one source (a bare
    ``parse_registry`` has no source, so it counts as one). A split registry
    satisfies the clause; a single-file registry over either limit must
    split. The limits and the capability-domain grouping are unchanged.
    """
    groups = {entry.fields.get("capability-domain", "") for entry in entries}
    single_file = len({entry.source for entry in entries}) <= 1
    if single_file and (
        len(entries) > SPLIT_ENTRY_LIMIT or len(groups) > SPLIT_GROUP_LIMIT
    ):
        return [
            f"registry within the single-file limits ({len(entries)} entries "
            f"<= {SPLIT_ENTRY_LIMIT}, {len(groups)} capability-domain "
            f"group(s) <= {SPLIT_GROUP_LIMIT}), or split"
        ]
    return []


def _parse_owner(value: str) -> list[tuple[str, list[str]]]:
    """Parse ``first-hop -> R4|R3; other -> R1`` into (hop, routes) pairs."""
    hops: list[tuple[str, list[str]]] = []
    for part in value.split(";"):
        part = part.strip()
        if not part:
            continue
        if "->" not in part:
            hops.append((part, []))
            continue
        hop, _, routes = part.partition("->")
        hops.append((
            hop.strip(),
            [route.strip() for route in routes.split("|") if route.strip()],
        ))
    return hops


def _parse_refs(value: str) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    for token in re.split(r"[,\s]+", value.strip()):
        if not token:
            continue
        entry_id, _, version = token.partition("@")
        refs.append((entry_id, version))
    return refs


def validate_registry(
        entries: list[RuleEntry],
        governance_events: list[dict] | None = None,
) -> list[RegistryError]:
    """G8 product-level checks. Returns structured errors.

    Every error is a :class:`RegistryError` — a ``str`` carrying the exact
    historical message (so prefix filtering in ``scripts/validate.py`` and
    the existing tests keep working) plus the structured ``rule`` /
    ``expected`` / ``actual`` / ``repair`` face the Finding-model gates
    use (review advisory R4).

    ``governance_events`` (vNext S5 wiring) supplies the parsed
    rules-governance.jsonl events. When present, every machine-enforced
    entry's ``governance-ref`` must resolve to an adjudicated *promote*
    event targeting that rule at ``machine-enforced`` (rules-prototype
    8.2 / Q6=A: "every machine-enforced entry has a governance
    adjudication reference"). Without events the reference's existence is
    still required but cannot be resolved — the shipped registry holds no
    machine-enforced entries, so the wired check stays dormant until the
    first promotion lands.
    """
    errors: list[RegistryError] = []
    seen: dict[str, RuleEntry] = {}
    promotions = (
        rules_governance.promote_adjudications(governance_events)
        if governance_events is not None else {}
    )

    for entry in entries:
        _validate_entry_fields(entry, seen, errors)
        _validate_applicability(entry, errors)
        _validate_placeholder(entry, errors)
        _validate_governance(entry, governance_events, promotions, errors)
        _validate_owner(entry, errors)
        _validate_evidence_layers(entry, errors)
        _validate_authority_severity(entry, errors)
        _validate_threshold(entry, errors)

    _validate_references(entries, seen, errors)
    _validate_overrides(entries, errors)
    _validate_history(entries, errors)
    return errors


def _validate_entry_fields(
    entry: RuleEntry,
    seen: dict[str, RuleEntry],
    errors: list[RegistryError],
) -> None:
    label = entry.id
    if not ID_PATTERN.match(label):
        errors.append(RegistryError(
            f"{label}: entry id fails ^[A-Z][A-Z0-9]*-[0-9]{2}$",
            rule=label,
            expected="^[A-Z][A-Z0-9]*-[0-9]{2}$",
            actual=label,
            repair="Rename the entry heading and id to the SCHEMA-NN "
                   "pattern",
        ))
    if label in seen:
        errors.append(RegistryError(
            f"{label}: duplicate registry id",
            rule=label,
            expected="unique registry ids",
            actual=f"second entry with id {label}",
            repair="Merge the duplicate entries or renumber one",
        ))
    seen[label] = entry

    for key in REQUIRED_KEYS:
        if not entry.fields.get(key, "").strip():
            errors.append(RegistryError(
                f"{label}: missing required field {key}",
                rule=label,
                expected=f"{key}: <value>",
                actual="missing",
                repair=f"Add the {key} line to the entry's fenced block",
            ))

    version = entry.fields.get("version", "")
    if not version.isdigit() or int(version) < 1:
        errors.append(RegistryError(
            f"{label}: version must be a positive integer, got {version!r}",
            rule=label,
            expected="positive integer",
            actual=version,
            repair="Set the next integer version and append a matching "
                   "history line",
        ))

    enum_checks = (
        ("capability-domain", CAPABILITY_DOMAINS),
        ("executes-in", EXECUTES_IN),
        ("authority", AUTHORITIES),
        ("provenance", PROVENANCES),
        ("status", STATUSES),
        ("check-type", CHECK_TYPES),
        ("evidence-method", EVIDENCE_METHODS),
    )
    for key, allowed in enum_checks:
        value = entry.fields.get(key, "")
        if value and value not in allowed:
            errors.append(RegistryError(
                f"{label}: {key} {value!r} not in "
                f"{{{'|'.join(sorted(allowed))}}}",
                rule=label,
                expected="|".join(sorted(allowed)),
                actual=value,
                repair=f"Set {key} to one of the allowed values",
            ))

    severity = entry.fields.get("severity-default", "")
    if severity and not SEVERITY_PATTERN.match(severity):
        errors.append(RegistryError(
            f"{label}: severity-default must be S3|S2|S1|S0 "
            f"(optionally '/ fact' or '/ judgment'), got {severity!r}",
            rule=label,
            expected="S3|S2|S1|S0 (optionally '/ fact' or '/ judgment')",
            actual=severity,
            repair="Rewrite onto the consequence axis (ADR-0028 records "
                   "the former alias mapping)",
        ))


def _validate_applicability(entry: RuleEntry, errors: list[RegistryError]) -> None:
    label = entry.id
    for key in APPLICABILITY_KEYS:
        if key == "applicability-blocked":
            continue  # advisory entries may have no blocked exit; placeholders must
        value = entry.fields.get(key, "")
        if value and not value.strip():
            errors.append(RegistryError(
                f"{label}: {key} is blank",
                rule=label,
                expected=f"{key}: observable predicate wording",
                actual="blank",
                repair=f"State the {key} predicate",
            ))


def _validate_placeholder(entry: RuleEntry, errors: list[RegistryError]) -> None:
    label = entry.id
    # Placeholder entries need the full three-state predicate + blocked exit.
    if entry.provenance == "placeholder":
        missing = [
            key for key in APPLICABILITY_KEYS
            if not entry.fields.get(key, "").strip()
        ]
        if missing:
            errors.append(RegistryError(
                f"{label}: placeholder entry lacks applicability predicate "
                f"or blocked exit: {missing}",
                rule=label,
                expected="all three applicability keys + blocked exit",
                actual=f"missing {missing}",
                repair="Write the three-state predicate and the blocked "
                       "exit",
            ))


def _validate_governance(
    entry: RuleEntry,
    governance_events: list[dict] | None,
    promotions: dict[str, dict],
    errors: list[RegistryError],
) -> None:
    # machine-enforced entries need a governance adjudication reference.
    if entry.status != "machine-enforced":
        return
    label = entry.id
    ref = entry.fields.get("governance-ref", "")
    if not ref.strip():
        errors.append(RegistryError(
            f"{label}: machine-enforced entry requires a governance "
            "adjudication reference (governance-ref)",
            rule=label,
            expected="governance-ref: <adjudication event id>",
            actual="missing",
            repair="Reference the promote -> machine-enforced "
                   "adjudication event",
        ))
        return
    if governance_events is None:
        return
    event = promotions.get(label)
    if event is None or event.get("id") != ref.strip():
        errors.append(RegistryError(
            f"{label}: governance-ref {ref!r} does not resolve "
            "to a promote -> machine-enforced adjudication for "
            f"{label} in the governance log",
            rule=label,
            expected=f"promote adjudication for {label}",
            actual=ref,
            repair="Point governance-ref at the rule's promotion "
                   "event in rules-governance.jsonl",
        ))
        return
    target_version = event.get("target_version")
    if (isinstance(target_version, int)
            and not isinstance(target_version, bool)
            and target_version != entry.version):
        errors.append(RegistryError(
            f"{label}: governance-ref pins {label}@"
            f"{target_version} but the registry version is "
            f"v{entry.version}",
            rule=label,
            expected=f"{label}@{entry.version}",
            actual=f"{label}@{target_version}",
            repair="Re-pin the adjudication or bump the entry "
                   "in lockstep",
        ))

def _validate_owner(entry: RuleEntry, errors: list[RegistryError]) -> None:
    label = entry.id
    owner = entry.fields.get("owner", "")
    if owner:
        for hop, routes in _parse_owner(owner):
            if hop not in OWNER_FIRST_HOPS:
                errors.append(RegistryError(
                    f"{label}: owner first hop {hop!r} not in "
                    "spec|domain|craft|design|components|template|"
                    "native-craft|reference|baseline",
                    rule=label,
                    expected="spec|domain|craft|design|components|"
                             "template|native-craft|reference|baseline",
                    actual=hop,
                    repair="Use one of the eight first-hop artifacts",
                ))
            for route in routes:
                if route not in OWNER_SECOND_HOPS:
                    errors.append(RegistryError(
                        f"{label}: owner second hop {route!r} not in R1-R5",
                        rule=label,
                        expected="R1-R5",
                        actual=route,
                        repair="Route the hop to R1-R5",
                    ))
            if hop in OWNER_FIRST_HOPS and not routes:
                errors.append(RegistryError(
                    f"{label}: owner hop {hop!r} has no R1-R5 route",
                    rule=label,
                    expected="at least one R1-R5 route",
                    actual=f"{hop} has no route",
                    repair="Append '-> R<n>' to the hop",
                ))


def _validate_evidence_layers(entry: RuleEntry, errors: list[RegistryError]) -> None:
    label = entry.id
    layers = entry.fields.get("evidence-layers", "")
    if layers:
        for token in layers.split(","):
            token = token.strip()
            name, _, count = token.partition(">=")
            if name.strip() not in EVIDENCE_LAYERS:
                errors.append(RegistryError(
                    f"{label}: evidence layer {name.strip()!r} not in "
                    "source|rendered|interaction|measurement|decision",
                    rule=label,
                    expected="source|rendered|interaction|measurement"
                             "|decision",
                    actual=name.strip(),
                    repair="Use a declared evidence layer name",
                ))
            elif not count.strip().isdigit() or int(count.strip()) < 1:
                errors.append(RegistryError(
                    f"{label}: evidence layer {token!r} needs count >= 1",
                    rule=label,
                    expected="<layer>>=1",
                    actual=token,
                    repair="State a count >= 1 for the layer",
                ))


def _validate_references(
    entries: list[RuleEntry],
    seen: dict[str, RuleEntry],
    errors: list[RegistryError],
) -> None:
    for entry in entries:
        for key in ("related", "overrides", "supersedes"):
            value = entry.fields.get(key, "")
            if not value.strip():
                continue
            for ref_id, ref_version in _parse_refs(value):
                target = seen.get(ref_id)
                if target is None:
                    errors.append(RegistryError(
                        f"{entry.id}: {key} references unknown id {ref_id}",
                        rule=entry.id,
                        expected=f"{key}: existing registry id",
                        actual=ref_id,
                        repair="Fix the reference or register the target "
                               "entry first",
                    ))
                    continue
                if ref_version and ref_version.isdigit():
                    if int(ref_version) != target.version:
                        errors.append(RegistryError(
                            f"{entry.id}: {key} pins {ref_id}@{ref_version} "
                            f"but registry version is {target.version}",
                            rule=entry.id,
                            expected=f"{ref_id}@{target.version}",
                            actual=f"{ref_id}@{ref_version}",
                            repair=f"Re-pin {key} to {ref_id}@{target.version}",
                        ))


def _validate_authority_severity(entry: RuleEntry, errors: list[RegistryError]) -> None:
    authority = entry.fields.get("authority", "")
    match = SEVERITY_PATTERN.match(entry.fields.get("severity-default", ""))
    if authority not in AUTHORITY_SEVERITY or not match:
        return  # enum and format errors are reported by the field checks
    levels, klass = AUTHORITY_SEVERITY[authority]
    level, seen_class = match.group(1), match.group(2) or ""
    if level not in levels or (klass and seen_class != klass):
        expected = "|".join(sorted(levels)) + (f" / {klass}" if klass else "")
        errors.append(RegistryError(
            f"{entry.id}: authority {authority} allows severity-default "
            f"{expected}, got {entry.fields['severity-default']!r}",
            rule=entry.id,
            expected=expected,
            actual=entry.fields["severity-default"],
            repair="Recalibrate severity-default or the authority, and bump "
                   "the version with a history line",
        ))


def _validate_threshold(entry: RuleEntry, errors: list[RegistryError]) -> None:
    value = entry.fields.get("threshold", "").strip()
    if entry.fields.get("authority") == "measured-threshold" and not value:
        errors.append(RegistryError(
            f"{entry.id}: measured-threshold entry has no threshold field",
            rule=entry.id,
            expected="threshold: <term> <op> <number><unit>; ...",
            actual="missing",
            repair="Add the threshold line; it is the single source for the "
                   "rule's numbers",
        ))
        return
    if not value:
        return
    _, problems = parse_threshold(value)
    for problem in problems:
        errors.append(RegistryError(
            f"{entry.id}: threshold {problem}",
            rule=entry.id,
            expected="<term> <op> <number><unit> with op >=|<=|= and unit "
                     ":1|px|ms|s|%|count",
            actual=value,
            repair="Rewrite the clause in the threshold syntax; keep prose in "
                   "statement or check-inputs",
        ))


def _validate_overrides(entries: list[RuleEntry], errors: list[RegistryError]) -> None:
    graph = {
        entry.id: [ref_id for ref_id, _ in _parse_refs(entry.fields.get("overrides", ""))]
        for entry in entries
    }
    for start in graph:
        visited: set[str] = set()
        stack = list(graph.get(start, ()))
        while stack:
            node = stack.pop()
            if node == start:
                errors.append(RegistryError(
                    f"{start}: overrides graph has a cycle",
                    rule=start,
                    expected="acyclic overrides graph",
                    actual=f"cycle back to {start}",
                    repair="Break the cycle — overrides must form a DAG "
                           "(consider supersedes instead)",
                ))
                break
            if node in visited:
                continue
            visited.add(node)
            stack.extend(graph.get(node, ()))


def _validate_history(entries: list[RuleEntry], errors: list[RegistryError]) -> None:
    for entry in entries:
        history = entry.fields.get("history", "")
        versions: list[int] = []
        for line in history.split(";"):
            head = line.strip().split("|", 1)[0].strip()
            if head.isdigit():
                versions.append(int(head))
        if versions:
            if versions != sorted(versions) or len(set(versions)) != len(versions):
                errors.append(RegistryError(
                    f"{entry.id}: history versions must increase monotonically",
                    rule=entry.id,
                    expected="strictly increasing history versions",
                    actual=str(versions),
                    repair="Reorder or renumber the history lines",
                ))
            elif versions[-1] != entry.version:
                errors.append(RegistryError(
                    f"{entry.id}: history ends at v{versions[-1]} but entry is "
                    f"v{entry.version}",
                    rule=entry.id,
                    expected=f"history ends at v{entry.version}",
                    actual=f"history ends at v{versions[-1]}",
                    repair=f"Append a v{entry.version} history line",
                ))


@dataclass
class CraftAuditRow:
    """One seven-column craft audit row parsed from a fixture or run log."""

    id_version: str
    applicability: str
    reason: str
    result: str
    rendered: str
    source: str
    exception: str
    fix: str

    @property
    def entry_id(self) -> str:
        return self.id_version.split("@", 1)[0]


def parse_craft_rows(text: str, *, with_case_column: bool = False) -> list[CraftAuditRow]:
    """Parse seven-column audit rows from markdown text.

    ``with_case_column`` matches the contrast fixtures, which carry a leading
    Case column before the same seven columns.
    """
    pattern = CONTRAST_ROW if with_case_column else SEVEN_COL_ROW
    shift = 1 if with_case_column else 0
    rows: list[CraftAuditRow] = []
    for match in pattern.finditer(text):
        groups = match.groups()
        rows.append(CraftAuditRow(
            id_version=groups[shift],
            applicability=groups[shift + 1],
            reason=groups[shift + 2].strip(),
            result=groups[shift + 3],
            rendered=groups[shift + 4].strip(),
            source=groups[shift + 5].strip(),
            exception=groups[shift + 6].strip(),
            fix=groups[shift + 7].strip(),
        ))
    return rows


def validate_craft_rows(
        rows: list[CraftAuditRow], entries: list[RuleEntry],
) -> list[RegistryError]:
    """Validate seven-column rows against the registry.

    Returns structured :class:`RegistryError` values (historical message
    preserved; ``rule`` pins the offending ``ID@ver`` row) so the run-level
    G8 gate can lift the structured face into its findings.
    """
    errors: list[RegistryError] = []
    by_id = {entry.id: entry for entry in entries}
    for row in rows:
        label = row.id_version
        target = by_id.get(row.entry_id)
        if target is None:
            errors.append(RegistryError(
                f"{label}: unknown registry id {row.entry_id}",
                rule=label,
                expected="a registered entry id",
                actual=row.entry_id,
                repair="Reference an entry from references/rules.md",
            ))
        else:
            pinned = row.id_version.split("@", 1)[1]
            if not pinned.isdigit() or int(pinned) != target.version:
                errors.append(RegistryError(
                    f"{label}: pinned version does not match registry "
                    f"v{target.version}",
                    rule=label,
                    expected=f"{row.entry_id}@{target.version}",
                    actual=row.id_version,
                    repair=f"Re-pin the row to {row.entry_id}@{target.version}",
                ))
        if row.applicability == "applicable":
            if row.result not in {"clear", "hit"}:
                errors.append(RegistryError(
                    f"{label}: applicable row needs Result clear|hit",
                    rule=label,
                    expected="clear|hit",
                    actual=row.result,
                    repair="Record the predicate evaluation result",
                ))
            for name, value in (
                ("Rendered evidence", row.rendered),
                ("Source evidence", row.source),
            ):
                if not value or value == "-":
                    errors.append(RegistryError(
                        f"{label}: applicable row missing {name} "
                        "(missing proof must be recorded as Applicability: blocked)",
                        rule=label,
                        expected=f"{name} cell filled",
                        actual="empty or '-'",
                        repair="Link the evidence, or mark the row blocked "
                               "and state the missing proof",
                    ))
        else:
            if row.result != "-":
                errors.append(RegistryError(
                    f"{label}: Result must be '-' unless Applicability is applicable",
                    rule=label,
                    expected="'-'",
                    actual=row.result,
                    repair="Use '-' for not-applicable/blocked rows",
                ))
            if not row.reason or row.reason == "-":
                errors.append(RegistryError(
                    f"{label}: {row.applicability} row requires an observable "
                    "reason / missing proof (blank is invalid)",
                    rule=label,
                    expected="an observable reason / missing proof",
                    actual="blank",
                    repair="State why the predicate is not applicable or "
                           "which proof is missing",
                ))
        if row.result == "hit":
            for name, value in (
                ("Exception check", row.exception),
                ("Positive fix", row.fix),
            ):
                if not value or value == "-":
                    errors.append(RegistryError(
                        f"{label}: hit row requires {name}",
                        rule=label,
                        expected=f"{name} cell filled",
                        actual="empty or '-'",
                        repair=f"Fill the {name} cell",
                    ))
    return errors


# --- machine-detector bindings (T-144) -----------------------------------
#
# A ``check-type: machine-detector`` rule names the callable that judges it.
# ``callable_path`` is ``<module>:<attribute>`` under the ``scripts/`` import
# root; the callable takes one payload and returns findings. A rule with no
# callable is *not* covered — ``reason`` states why, so enumeration never
# reports silent coverage (the ecosystem failure I6 names).


@dataclass(frozen=True)
class DetectorBinding:
    """One registry rule bound to its detector callable (or a reason it is not)."""

    rule_id: str
    callable_path: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.callable_path and not self.reason:
            raise ValueError(
                f"{self.rule_id}: an unbound detector requires a reason"
            )

    @property
    def implemented(self) -> bool:
        return bool(self.callable_path)


DETECTOR_BINDINGS: dict[str, DetectorBinding] = {
    binding.rule_id: binding
    for binding in (
        DetectorBinding("A11Y-03", "detectors.contrast:detect"),
        DetectorBinding("A11Y-04", "detectors.hit_target:detect"),
        DetectorBinding("A11Y-05", "detectors.text_size:detect"),
        DetectorBinding(
            "CRAFT-11",
            reason=(
                "declared type/spacing/radius scales have no machine-readable "
                "artifact in a run, and near-duplicate hierarchy plus "
                "nested-radius conformance need layout-tree adjacency; a "
                "size-count-only check would under-cover the rule"
            ),
        ),
    )
}


def machine_detector_statuses(
        entries: list[RuleEntry],
) -> list[dict[str, Any]]:
    """Enumerate every ``machine-detector`` rule with its implementation status.

    Returns ``[{"ruleId", "implemented", "reason"}]`` in registry order. An
    entry with no binding is reported as unimplemented with an explicit
    reason — never as covered.
    """
    statuses: list[dict[str, Any]] = []
    for entry in entries:
        if entry.fields.get("check-type") != "machine-detector":
            continue
        binding = DETECTOR_BINDINGS.get(entry.id)
        statuses.append({
            "ruleId": entry.id,
            "implemented": bool(binding and binding.implemented),
            "reason": (
                binding.reason if binding is not None
                else "no detector bound (rule declares machine-detector)"
            ),
        })
    return statuses


def validate_detector_bindings(
        entries: list[RuleEntry],
) -> list[RegistryError]:
    """Check that the binding table points at real machine-detector rules."""
    by_id = {entry.id: entry for entry in entries}
    errors: list[RegistryError] = []
    for rule_id, binding in DETECTOR_BINDINGS.items():
        entry = by_id.get(rule_id)
        if entry is None:
            errors.append(RegistryError(
                f"detector binding: unknown registry id {rule_id}",
                rule=rule_id,
                expected="a registered entry id",
                actual=rule_id,
                repair="Bind a detector to an entry from references/rules.md",
            ))
        elif entry.fields.get("check-type") != "machine-detector":
            errors.append(RegistryError(
                f"detector binding: {rule_id} is not a machine-detector rule",
                rule=rule_id,
                expected="check-type: machine-detector",
                actual=entry.fields.get("check-type", "missing"),
                repair="Remove the binding or change the rule's check-type",
            ))
    return errors


def load_detector(rule_id: str) -> Callable[[object], list[dict[str, Any]]]:
    """Resolve the detector callable bound to ``rule_id`` (fail closed)."""
    binding = DETECTOR_BINDINGS.get(rule_id)
    if binding is None or not binding.implemented:
        reason = binding.reason if binding is not None else "no binding"
        raise NotImplementedError(f"{rule_id}: no detector implementation: {reason}")
    module_name, _, attribute = binding.callable_path.partition(":")
    # Resolve under this module's own name, never "whichever is importable".
    # A bare ``rules_registry`` and a packaged one would otherwise load the
    # detector twice, and the two copies' exception classes do not match.
    prefix = f"{__name__.rsplit('.', 1)[0]}." if "." in __name__ else ""
    leaf = module_name.partition(".")[2]
    return getattr(
        importlib.import_module(f"{prefix}detectors.{leaf}"), attribute
    )


def run_detector(rule_id: str, payload: object) -> list[dict[str, Any]]:
    """Run the bound detector over ``payload`` and return its findings."""
    return load_detector(rule_id)(payload)
