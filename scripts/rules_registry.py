"""First-party UX rule registry parsing and G8 product-level self-check.

Shared by ``scripts/validate.py`` (the product-level G8 gate) and the repo
unit tests. Owns exactly the machine-checkable face declared in
``skills/design-playbook/references/rules.md``:

- entry parsing: ``## <ID> — <title>`` heading + one fenced field block
- enum / format / reference checks (rules-prototype §8.2, decision Q6=A)
- seven-column craft audit row parsing for the migrated fixtures

Protocol-face fields (statement wording, signal quality, fix quality) are
intentionally not judged here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

RULES_PATH_PARTS = (
    "skills", "design-playbook", "references", "rules.md"
)

ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*-[0-9]{2}$")
ENTRY_HEADING = re.compile(r"^## ([A-Z][A-Z0-9]*-[0-9]{2})\b", re.M)
FIELD_LINE = re.compile(r"^([a-z][a-z0-9-]*):[ \t]*(.*)$", re.M)

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
EVIDENCE_LAYERS = frozenset({"source", "rendered", "interaction", "measurement"})
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


def validate_registry(entries: list[RuleEntry]) -> list[str]:
    """G8 product-level checks. Returns a list of failure descriptions."""
    errors: list[str] = []
    seen: dict[str, RuleEntry] = {}

    for entry in entries:
        label = entry.id
        if not ID_PATTERN.match(label):
            errors.append(f"{label}: entry id fails ^[A-Z][A-Z0-9]*-[0-9]{2}$")
        if label in seen:
            errors.append(f"{label}: duplicate registry id")
        seen[label] = entry

        for key in REQUIRED_KEYS:
            if not entry.fields.get(key, "").strip():
                errors.append(f"{label}: missing required field {key}")

        version = entry.fields.get("version", "")
        if not version.isdigit() or int(version) < 1:
            errors.append(f"{label}: version must be a positive integer, got {version!r}")

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
                errors.append(
                    f"{label}: {key} {value!r} not in {{{'|'.join(sorted(allowed))}}}"
                )

        severity = entry.fields.get("severity-default", "")
        if severity and not SEVERITY_PATTERN.match(severity):
            errors.append(
                f"{label}: severity-default must be S3|S2|S1|S0 "
                f"(optionally '/ fact' or '/ judgment'), got {severity!r}"
            )

        for key in APPLICABILITY_KEYS:
            if key == "applicability-blocked":
                continue  # advisory entries may have no blocked exit; placeholders must
            value = entry.fields.get(key, "")
            if value and not value.strip():
                errors.append(f"{label}: {key} is blank")

        # Placeholder entries need the full three-state predicate + blocked exit.
        if entry.provenance == "placeholder":
            missing = [
                key for key in APPLICABILITY_KEYS
                if not entry.fields.get(key, "").strip()
            ]
            if missing:
                errors.append(
                    f"{label}: placeholder entry lacks applicability predicate "
                    f"or blocked exit: {missing}"
                )

        # machine-enforced entries need a governance adjudication reference.
        if entry.status == "machine-enforced":
            ref = entry.fields.get("governance-ref", "")
            if not ref.strip():
                errors.append(
                    f"{label}: machine-enforced entry requires a governance "
                    "adjudication reference (governance-ref)"
                )

        owner = entry.fields.get("owner", "")
        if owner:
            for hop, routes in _parse_owner(owner):
                if hop not in OWNER_FIRST_HOPS:
                    errors.append(
                        f"{label}: owner first hop {hop!r} not in "
                        "spec|domain|craft|design|components|template|"
                        "native-craft|reference|baseline"
                    )
                for route in routes:
                    if route not in OWNER_SECOND_HOPS:
                        errors.append(
                            f"{label}: owner second hop {route!r} not in R1-R5"
                        )
                if hop in OWNER_FIRST_HOPS and not routes:
                    errors.append(f"{label}: owner hop {hop!r} has no R1-R5 route")

        layers = entry.fields.get("evidence-layers", "")
        if layers:
            for token in layers.split(","):
                token = token.strip()
                name, _, count = token.partition(">=")
                if name.strip() not in EVIDENCE_LAYERS:
                    errors.append(
                        f"{label}: evidence layer {name.strip()!r} not in "
                        "source|rendered|interaction|measurement"
                    )
                elif not count.strip().isdigit() or int(count.strip()) < 1:
                    errors.append(f"{label}: evidence layer {token!r} needs count >= 1")

    # Reference existence + pinned versions (related / overrides / supersedes).
    for entry in entries:
        for key in ("related", "overrides", "supersedes"):
            value = entry.fields.get(key, "")
            if not value.strip():
                continue
            for ref_id, ref_version in _parse_refs(value):
                target = seen.get(ref_id)
                if target is None:
                    errors.append(f"{entry.id}: {key} references unknown id {ref_id}")
                    continue
                if ref_version and ref_version.isdigit():
                    if int(ref_version) != target.version:
                        errors.append(
                            f"{entry.id}: {key} pins {ref_id}@{ref_version} "
                            f"but registry version is {target.version}"
                        )

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
                errors.append(f"{start}: overrides graph has a cycle")
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
                errors.append(f"{entry.id}: history versions must increase monotonically")
            elif versions[-1] != entry.version:
                errors.append(
                    f"{entry.id}: history ends at v{versions[-1]} but entry is "
                    f"v{entry.version}"
                )
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


def validate_craft_rows(rows: list[CraftAuditRow], entries: list[RuleEntry]) -> list[str]:
    """Validate seven-column rows against the registry. Returns failures."""
    errors: list[str] = []
    by_id = {entry.id: entry for entry in entries}
    for row in rows:
        label = row.id_version
        target = by_id.get(row.entry_id)
        if target is None:
            errors.append(f"{label}: unknown registry id {row.entry_id}")
        else:
            pinned = row.id_version.split("@", 1)[1]
            if not pinned.isdigit() or int(pinned) != target.version:
                errors.append(
                    f"{label}: pinned version does not match registry "
                    f"v{target.version}"
                )
        if row.applicability == "applicable":
            if row.result not in {"clear", "hit"}:
                errors.append(f"{label}: applicable row needs Result clear|hit")
            for name, value in (
                ("Rendered evidence", row.rendered),
                ("Source evidence", row.source),
            ):
                if not value or value == "-":
                    errors.append(
                        f"{label}: applicable row missing {name} "
                        "(missing proof must be recorded as Applicability: blocked)"
                    )
        else:
            if row.result != "-":
                errors.append(
                    f"{label}: Result must be '-' unless Applicability is applicable"
                )
            if not row.reason or row.reason == "-":
                errors.append(
                    f"{label}: {row.applicability} row requires an observable "
                    "reason / missing proof (blank is invalid)"
                )
        if row.result == "hit":
            for name, value in (
                ("Exception check", row.exception),
                ("Positive fix", row.fix),
            ):
                if not value or value == "-":
                    errors.append(f"{label}: hit row requires {name}")
    return errors
