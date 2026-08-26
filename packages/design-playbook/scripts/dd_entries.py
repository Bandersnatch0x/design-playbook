"""Design-decision entry artifacts (vNext S2, design-prototype 4.1).

Owns the versioned DD entry blocks appended to ``decision-report.md`` after
the verbatim top block (the Fill consumption face stays byte-identical), in
the same field-block style as the rule registry:

    ## DD-0003 — <question>

    ```yaml
    id: DD-0003
    tier: explore
    question: <one-line question>
    status: confirmed-user
    constraints:
      baseline: DESIGN.md sha256:<digest>
      spec: [l1.scenes, l6.c1]
      rules: [PERF-01@1]
    candidates:
      - {id: A, source: agent, created_at: <ts>, fidelity: description,
         summary: <one line>, deviations: none, assets: []}
    comparison:
      axes:
        - {axis: <axis name> (<source ref>), A: <statement>, B: <statement>}
      tradeoffs: "A trades X for Y; B trades P for Q"
    selection:
      candidate: B
      rationale: <must point back at an axis or trade-off>
      rejected:
        - {candidate: A, reason: <rejection reason>}
    confirmation:
      kind: user
      via: preview-round-1 decision_id:<hex>
      confirmed_at: <ts>
    supersedes: null
    stale: <reason + ts>                     # optional, baseline drift
    stale_review: {exit: keep, note: <review line + new sha256>}   # optional
    ```

Also owns the R/C/E trigger table (design-prototype 1.1/1.2): tier grading
signals that are machine-judgeable from run artifacts are collected by
:func:`collect_e_signals`; the rest (composition change, judgement calls)
stay protocol-side. Gate policy lives in ``g10_design_decisions.py``.

Flow-map values inside ``- {k: v, ...}`` items may not contain ASCII commas
or braces (use full-width punctuation in prose values); this is the declared
shape, same contract style as the seven-column audit rows. Items may fold
across lines (issue #44): a ``- {`` item that does not close its brace on
the marker line continues on the following lines until the braces balance —
single-line items parse exactly as before. Folds break at commas (the
schema example's shape): a break that does not end the accumulated text
with a comma (or the opening brace) would merge the next key into the
previous value, so the join records a :class:`FoldIssue` and G10 reports it
(:code:`G10.fold_break_not_comma`); a fold that never balances by the end
of the block records :code:`G10.fold_unterminated` (fail-closed, with the
remaining shape errors still firing).

``dd:`` is the R3 challenge channel, never an observation link: values
carried by positive (S0) findings are excluded from the challenge face and
reported as structural errors by G10 (issue #44).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from design_playbook.scripts.finding_syntax import parse_findings

# --- closed enums (design-prototype 4.1 machine face) -----------------------

DD_TIERS = frozenset({"record", "compare", "explore"})
DD_STATUSES = frozenset({
    "open", "compared", "confirmed-agent", "confirmed-user",
    "superseded", "invalidated",
})
RETIRED_STATUSES = frozenset({"superseded", "invalidated"})
CANDIDATE_SOURCES = frozenset({"agent", "provider-adapter", "user"})
CONFIRM_KINDS = frozenset({"user", "agent"})
STALE_EXITS = frozenset({"keep", "revise", "escalate"})
FIDELITIES = frozenset({
    "description", "sketch", "wireframe", "interactive-prototype",
})

# id: run-unique, 4-digit zero-padded (matches the decisions.jsonl id regex
# when projected); cross-run references look like ``<run>/DD-0003``.
DD_ID = re.compile(r"^DD-[0-9]{4}$")
DD_HEADING = re.compile(r"^## (DD-\S+)\b.*$", re.M)
DD_REF = re.compile(r"(DD-[0-9]{4})$")
SHA256 = re.compile(r"sha256:([0-9a-f]{64})", re.I)
PREVIEW_VIA = re.compile(
    r"^preview-round-([0-9]+)\s+decision_id:([0-9A-Za-z-]+)$")
AGENT_VIA = re.compile(r"^agent-record$")
BATCH_VIA = re.compile(r"^report-batch")
ADAPTER_HANDLE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# --- R/C/E trigger table (design-prototype 1.2; ◆ = machine-judgeable) ------

E_CRITERIA: tuple[tuple[str, str, bool], ...] = (
    ("identity", "candidate deviates from the bound baseline's visual "
                 "role, atmosphere, density, or motion conventions", False),
    ("composition", "candidate reorganizes the region set or weight "
                    "allocation rather than filling inside a region", False),
    ("upstream-route", "a T3 visual-direction open question arrives from "
                       "shaping (registered, not decided there)", True),
    ("re-entry", "an R3 finding challenges an existing decision's "
                 "assumptions or unrecorded trade-offs (dd: line)", True),
    ("baseline-conflict", "candidate conflicts with the baseline or hard "
                          "constraints and needs an explicit trade "
                          "(report baseline-changes != none)", True),
)

TIER_TIERS_DOC = (
    ("record", "single reasonable choice or local implementation inside "
               "confirmed declarations; agent decides; one-line rationale"),
    ("compare", "2-3 substantive candidates inside the baseline, no E "
                "criterion hit; agent decides and records the trade-offs"),
    ("explore", "any E criterion hit; user confirms; full entry with "
                "comparison matrix and confirmation record"),
)


@dataclass(frozen=True)
class DDEntry:
    """One parsed DD entry block (machine face + raw text)."""

    id: str
    fields: dict[str, str] = field(default_factory=dict)
    constraints: dict[str, str] = field(default_factory=dict)
    candidates: tuple[dict[str, str], ...] = ()
    comparison_axes: tuple[dict[str, str], ...] = ()
    comparison_tradeoffs: str = ""
    selection: dict[str, str] = field(default_factory=dict)
    rejected: tuple[dict[str, str], ...] = ()
    confirmation: dict[str, str] = field(default_factory=dict)
    supersedes: str = ""
    stale: str = ""
    stale_review: dict[str, str] = field(default_factory=dict)
    fold_issues: tuple["FoldIssue", ...] = ()
    block: str = ""

    # -- convenience accessors ------------------------------------------

    @property
    def tier(self) -> str:
        return self.fields.get("tier", "")

    @property
    def status(self) -> str:
        return self.fields.get("status", "")

    @property
    def question(self) -> str:
        return self.fields.get("question", "")

    @property
    def baseline_ref(self) -> str:
        return self.constraints.get("baseline", "")

    @property
    def baseline_sha(self) -> str:
        match = SHA256.search(self.baseline_ref)
        return match.group(1).lower() if match else ""

    @property
    def preview_link(self) -> tuple[int, str] | None:
        """``(round_n, decision_id)`` when confirmation rode a transaction."""
        via = self.confirmation.get("via", "")
        match = PREVIEW_VIA.match(via.strip())
        if match is None:
            return None
        return int(match.group(1)), match.group(2)

    @property
    def rules_refs(self) -> tuple[str, ...]:
        return _bracket_items(self.constraints.get("rules", ""))

    @property
    def supersedes_ref(self) -> str:
        """Normalized supersedes reference ("" when null/absent)."""
        value = self.supersedes.strip()
        return "" if value.casefold() in {"", "null", "none", "-"} else value

    def candidate_ids(self) -> list[str]:
        return [item.get("id", "") for item in self.candidates]


@dataclass(frozen=True)
class FoldIssue:
    """A fold defect found while joining folded flow-map items.

    ``kind`` is ``"break_not_comma"`` (the accumulated fold text did not end
    with a comma — or the opening brace — when a continuation was appended,
    so the next key merges into the previous value) or ``"unterminated"``
    (the braces never balanced before the block ended). ``line`` is the
    1-based line of the fold-opening marker inside the entry block;
    ``tail`` carries the offending text tail for the error face.
    """

    kind: str
    line: int
    tail: str = ""


@dataclass(frozen=True)
class ESignals:
    """Machine-judgeable E-criterion signals gathered from run artifacts."""

    fired: tuple[str, ...] = ()
    dd_targets: tuple[str, ...] = ()
    t3_questions: tuple[str, ...] = ()
    baseline_changed: bool = False


# --- parsing helpers ---------------------------------------------------------

def _scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1].strip()
    return value


def _bracket_items(value: str) -> tuple[str, ...]:
    value = value.strip()
    if not (value.startswith("[") and value.endswith("]")):
        return ()
    inner = value[1:-1].strip()
    if not inner:
        return ()
    return tuple(_scalar(part) for part in inner.split(",") if part.strip())


def _flow_map(item: str) -> dict[str, str]:
    """Parse ``{k: v, k: v}`` flow maps; non-map items become {'value': …}."""
    item = item.strip()
    if item.startswith("{") and item.endswith("}"):
        inner = item[1:-1]
        pairs = re.findall(
            r"([A-Za-z_][\w-]*):\s*(\"[^\"]*\"|'[^']*'|[^,{}]*)", inner)
        return {key: _scalar(value) for key, value in pairs}
    return {"value": _scalar(item)}


def _join_folded_flow_maps(
        lines: list[str]) -> tuple[list[str], tuple[FoldIssue, ...]]:
    """Join folded ``- {...}`` flow-map items onto their marker line.

    Issue #44: an item that opens a ``{`` without closing it on the marker
    line continues on the following lines (the fold the entry schema
    example already shows) until its braces balance; continuation text is
    appended to the marker line so the rest of the parser sees one logical
    line. Values never contain ASCII commas or braces (declared shape), so
    brace balance is an unambiguous fold terminator. Folds break at commas:
    a continuation appended to accumulated text that does not end with a
    comma (or the opening brace) would silently merge the next key into the
    previous value, so the break is recorded as a :class:`FoldIssue`
    (fail-closed; G10 reports it). An unterminated fold stays joined and
    records its own issue plus the downstream shape checks (fail-closed).
    Returns ``(joined lines, fold issues)``.
    """
    out: list[str] = []
    issues: list[FoldIssue] = []
    fold: str | None = None
    fold_line = 0
    for lineno, raw_line in enumerate(lines, 1):
        stripped = raw_line.strip()
        if fold is not None:
            if not fold.rstrip().endswith((",", "{")):
                issues.append(FoldIssue(
                    kind="break_not_comma",
                    line=fold_line,
                    tail=fold.strip()[-60:],
                ))
            fold = fold.rstrip() + " " + stripped
            if fold.count("{") <= fold.count("}"):
                out.append(fold)
                fold = None
            continue
        if (
            stripped.startswith("- ")
            and stripped.count("{") > stripped.count("}")
        ):
            fold = raw_line.rstrip()
            fold_line = lineno
            continue
        out.append(raw_line)
    if fold is not None:
        issues.append(FoldIssue(kind="unterminated", line=fold_line))
        out.append(fold)
    return out, tuple(issues)


def _entry_blocks(text: str) -> list[tuple[str, str]]:
    """Split the report into (id, body) blocks by DD entry heading."""
    matches = list(DD_HEADING.finditer(text))
    blocks: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) \
            else len(text)
        blocks.append((match.group(1), text[match.start():end]))
    return blocks


def _fenced_block(body: str) -> str:
    match = re.search(r"```[a-zA-Z]*\n(.*?)```", body, re.S)
    return match.group(1) if match else ""


def _parse_entry(entry_id: str, body: str) -> DDEntry:
    block = _fenced_block(body)
    fields: dict[str, str] = {}
    sections: dict[str, dict[str, Any]] = {}
    current_section: str | None = None
    current_list_key: str | None = None

    joined, fold_issues = _join_folded_flow_maps(block.splitlines())
    for raw_line in joined:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("```"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if indent == 0:
            current_section = None
            current_list_key = None
            match = re.match(r"^([a-z][a-z0-9_-]*):[ \t]*(.*)$", stripped)
            if match is None:
                continue
            key, value = match.group(1), match.group(2).strip()
            if value.startswith("{") and value.endswith("}"):
                # single-line flow map section (R-tier minimal form):
                # selection: {candidate: X, rationale: one line}
                sections[key] = dict(_flow_map(value))
                continue
            if value:
                fields[key] = _scalar(value)
            else:
                current_section = key
                sections.setdefault(key, {})
            continue
        if current_section is None:
            continue
        section = sections[current_section]
        if stripped.startswith("- "):
            item = _flow_map(stripped[2:].strip())
            if current_list_key is None:
                section.setdefault("_items_", []).append(item)
            else:
                section.setdefault(current_list_key, {"_items_": []})
                if isinstance(section[current_list_key], dict):
                    section[current_list_key].setdefault(
                        "_items_", []).append(item)
            continue
        match = re.match(r"^([a-z][a-z0-9_-]*):[ \t]*(.*)$", stripped)
        if match is None:
            continue
        key, value = match.group(1), match.group(2).strip()
        current_list_key = None
        if value:
            section[key] = _scalar(value)
        else:
            current_list_key = key
            section.setdefault(key, {"_items_": []})

    def _scalars(name: str) -> dict[str, str]:
        section = sections.get(name, {})
        return {
            key: value for key, value in section.items()
            if isinstance(value, str)
        }

    def _items(name: str, key: str | None = None) -> tuple[dict[str, str], ...]:
        section = sections.get(name, {})
        if key is None:
            values = section.get("_items_", [])
        else:
            holder = section.get(key, {})
            values = holder.get("_items_", []) if isinstance(holder, dict) else []
        return tuple(value for value in values if isinstance(value, dict))

    return DDEntry(
        id=entry_id,
        fields=fields,
        constraints=_scalars("constraints"),
        candidates=_items("candidates"),
        comparison_axes=_items("comparison", "axes"),
        comparison_tradeoffs=_scalars("comparison").get("tradeoffs", ""),
        selection=_scalars("selection"),
        rejected=_items("selection", "rejected"),
        confirmation=_scalars("confirmation"),
        supersedes=fields.get("supersedes", ""),
        stale=fields.get("stale", ""),
        stale_review=_scalars("stale_review"),
        fold_issues=fold_issues,
        block=block,
    )


def parse_dd_entries(text: str) -> list[DDEntry]:
    """Parse DD entry blocks from a decision report (no validation)."""
    return [
        _parse_entry(entry_id, body)
        for entry_id, body in _entry_blocks(text)
    ]


# ``none`` value token for the verbatim top block: a trailing same-line
# note after the token is tolerated commentary, never a declared change
# (issue #44). The token must end at whitespace or punctuation so values
# like ``nonempty`` and ``none_x`` stay fail-closed non-none (underscore
# joins the lookalike continuation class with ``-``, e.g. ``none-such``).
NONE_VALUE = re.compile(r"none(?=$|[^0-9A-Za-z_-])", re.I)


def top_block_baseline_change(text: str) -> bool:
    """True when the verbatim top block declares ``baseline-changes != none``.

    ``none`` may carry a trailing same-line note (anything after the value
    token); notes never turn ``none`` into a declared change. Substantive
    commentary belongs on its own line.
    """
    match = re.search(r"^baseline-changes:[ \t]*(\S.*)$", text, re.M)
    if match is None:
        return False
    return NONE_VALUE.match(match.group(1).strip()) is None


def is_positive_finding(parsed: dict[str, list[str]]) -> bool:
    """True when a parsed point-back finding sits on the S0 (info) axis."""
    values = parsed.get("severity") or [""]
    return values[0].strip().casefold() == "s0"


def positive_dd_refs(
        text: str) -> tuple[tuple[int, tuple[str, ...]], ...]:
    """``(finding index, dd refs)`` for every positive finding carrying ``dd:``.

    Issue #44: ``dd:`` is the R3 challenge channel and never rides a
    positive observation. These are structural errors G10 reports
    (fail-closed) instead of silently reading them as challenges.
    """
    out: list[tuple[int, tuple[str, ...]]] = []
    for index, parsed in enumerate(parse_findings(text), 1):
        refs = tuple(
            value.strip().rstrip(",") for value in parsed.get("dd", [])
            if value.strip())
        if refs and is_positive_finding(parsed):
            out.append((index, refs))
    return tuple(out)


def _positive_dd_block(block: str) -> bool:
    return any(
        parsed.get("dd") and is_positive_finding(parsed)
        for parsed in parse_findings(block)
    )


def dd_refs_in_pointback(text: str) -> tuple[str, ...]:
    """Collect ``dd:`` challenge targets from finding field lines.

    Issue #44: ``dd:`` values carried by positive (S0) findings record
    observation links, not challenges — their paragraphs are skipped so a
    positive observation can never fire a false re-entry / E3 signal.
    Paragraphs that are not findings (e.g. a bare ``dd:`` line) keep the
    legacy raw face.
    """
    targets: list[str] = []
    for block in re.split(r"\n\s*\n", text):
        if _positive_dd_block(block):
            continue
        for match in re.finditer(r"^dd:[ \t]*(\S+)", block, re.I | re.M):
            ref = match.group(1).strip().rstrip(",")
            targets.append(ref)
    return tuple(targets)


def local_dd_id(ref: str) -> str | None:
    """Resolve a reference to a same-report id; cross-run refs stay opaque."""
    match = DD_REF.search(ref.strip())
    return match.group(1) if match else None


def is_cross_run_ref(ref: str) -> bool:
    return "/" in ref.strip()


def t3_routed_questions(events: list[dict[str, Any]]) -> tuple[str, ...]:
    """T3 visual-direction questions registered by the shaping session.

    Shaping registers T3 questions without deciding them (the #28 routing
    interface); each one must land as an E-tier DD entry downstream.
    """
    return tuple(
        str(event.get("question_id") or event.get("text") or "")
        for event in events
        if event.get("event") == "asked" and event.get("tier") == "T3"
    )


def _has_deviations(candidate: dict[str, str]) -> bool:
    value = candidate.get("deviations", "").strip().strip("[]").strip()
    return bool(value) and value.casefold() not in {"none", "-"}


def collect_e_signals(
    entries: list[DDEntry],
    *,
    shaping_events: list[dict[str, Any]] | None = None,
    pointback_text: str | None = None,
    report_text: str | None = None,
) -> ESignals:
    """Gather the machine-judgeable E-criterion signals (design-prototype 1.2).

    Criteria 3/4/5 are machine-judgeable from artifacts; criteria 1/2 are
    only partially visible (declared ``deviations`` hint at 1/5; composition
    changes need judgement). The result feeds both G10 cross-checks and the
    protocol-side grading duty.
    """
    fired: list[str] = []
    shaping_events = shaping_events or []
    dd_targets = dd_refs_in_pointback(pointback_text) if pointback_text else ()
    t3 = t3_routed_questions(shaping_events)
    baseline_changed = (
        top_block_baseline_change(report_text) if report_text else False
    )
    if any(_has_deviations(candidate) for entry in entries
           for candidate in entry.candidates):
        fired.append("identity")
    if t3:
        fired.append("upstream-route")
    if dd_targets:
        fired.append("re-entry")
    if baseline_changed:
        fired.append("baseline-conflict")
    return ESignals(
        fired=tuple(fired),
        dd_targets=dd_targets,
        t3_questions=t3,
        baseline_changed=baseline_changed,
    )
