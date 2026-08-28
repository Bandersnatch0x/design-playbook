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

import re
from dataclasses import dataclass, field

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

CAPABILITY_DOMAINS = frozenset(f"D{i}" for i in range(1, 9))
EXECUTES_IN = frozenset({
    "D4:product", "D4:interaction", "D4:cross-cutting", "registry-only",
})
AUTHORITIES = frozenset({
    "hard-constraint", "project-declaration", "platform-convention",
    "measured-threshold", "advisory-aesthetic",
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
    """Parse registry entries into RuleEntry objects (no validation)."""
    entries: list[RuleEntry] = []
    for entry_id, body in _entry_blocks(text):
        block = _fenced_block(body)
        fields = {
            match.group(1): match.group(2).strip()
            for match in FIELD_LINE.finditer(block)
        }
        entries.append(RuleEntry(id=entry_id, fields=fields))
    return entries


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
    errors: list[str] = []
    seen: dict[str, RuleEntry] = {}
    promotions = (
        rules_governance.promote_adjudications(governance_events)
        if governance_events is not None else {}
    )

    for entry in entries:
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

        # machine-enforced entries need a governance adjudication reference.
        if entry.status == "machine-enforced":
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
            elif governance_events is not None:
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
                else:
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

    # Reference existence + pinned versions (related / overrides / supersedes).
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

    # Overrides graph must be acyclic.
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

    # History versions must increase and end at the current version.
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
    return errors


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
