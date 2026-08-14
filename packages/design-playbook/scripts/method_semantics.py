"""Manifest method-semantics keys (vNext S3, review-prototype 3.3 / Q6=A).

Five optional keys may be appended to an ``evidence/manifest.jsonl`` entry
by the orchestrator at binding time — ``method`` / ``observation`` /
``interpretation`` / ``scope`` / ``population``+``ethics``. The keys are
append-only optional: old readers ignore unknown keys and old entries with
no keys trigger no new checks (compatibility contract #3).

Machine face owned here:

- ``method`` nine-value enum (HCI research-method table, #24 D5);
- ``observation`` (fact) / ``interpretation`` (reading) separation — an
  interpretation without an observation is a structural error;
- ``scope`` is required once a method is declared, except for
  ``static-inspection`` (source facts have no run scope to bound);
- human-subject methods (``user-test`` / ``interview`` / ``survey`` /
  ``field-observation``) must carry ``population`` and ``ethics``; when
  either is missing the entry is *unusable* — it cannot support any
  judgment (recorded as blocked evidence, never silently dropped). A pass
  ledger row whose bound (latest) manifest entry is unusable fails the gate
  (connects to #29-Q2: pass must rest on usable runtime evidence).

The G6-adjacent gate check lives here as well, following the modular gate
precedent (g6_records / g6_warnings): pure semantics above, Findings below.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from design_playbook.scripts._diagnostics import Finding, finding

METHODS = frozenset({
    "static-inspection",
    "runtime-observation",
    "expert-review",
    "user-test",
    "interview",
    "survey",
    "field-observation",
    "telemetry",
    "controlled-comparison",
})
# Human-subject evidence: population + ethics become mandatory (#29 3.3).
HUMAN_SUBJECT_METHODS = frozenset({
    "user-test", "interview", "survey", "field-observation",
})
# Methods whose conclusions can generalize beyond the checked artifact need
# an explicit scope; source inspection is its own scope.
SCOPE_EXEMPT_METHODS = frozenset({"static-inspection"})

METHOD_KEYS = ("method", "observation", "interpretation", "scope",
               "population", "ethics")


@dataclass(frozen=True)
class MethodSemantics:
    """One manifest entry's parsed method-semantics values."""

    method: str = ""
    observation: str = ""
    interpretation: str = ""
    scope: str = ""
    population: str = ""
    ethics: str = ""

    @property
    def declared(self) -> bool:
        return any((self.method, self.observation, self.interpretation,
                    self.scope, self.population, self.ethics))

    @property
    def human_subject(self) -> bool:
        return self.method in HUMAN_SUBJECT_METHODS

    @property
    def usable(self) -> bool:
        return not self.unusable_reason

    @property
    def unusable_reason(self) -> str:
        if not self.human_subject:
            return ""
        missing = [
            name for name, value in (("population", self.population),
                                     ("ethics", self.ethics))
            if not value
        ]
        if missing:
            return (f"human-subject method {self.method!r} lacks "
                    + " and ".join(missing))
        return ""


def _text(value: Any) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def parse_method_semantics(entry: dict) -> MethodSemantics:
    """Parse the five optional keys off one manifest entry."""
    return MethodSemantics(
        method=_text(entry.get("method")).strip(),
        observation=_text(entry.get("observation")).strip(),
        interpretation=_text(entry.get("interpretation")).strip(),
        scope=_text(entry.get("scope")).strip(),
        population=_text(entry.get("population")).strip(),
        ethics=_text(entry.get("ethics")).strip(),
    )


def entry_errors(entry: dict) -> list[str]:
    """Structural method-semantics errors for one entry (empty = valid).

    Unusable human-subject evidence is *not* listed here: quarantine is a
    usability fact, not a structural break — see ``unusable_reason``.
    """
    semantics = parse_method_semantics(entry)
    if not semantics.declared:
        return []  # no keys -> no new checks (backward compatible)
    errors: list[str] = []
    if not semantics.method:
        errors.append("method key required once method semantics are present")
    elif semantics.method not in METHODS:
        errors.append(
            f"method {semantics.method!r} not in the nine-value enum "
            f"({'|'.join(sorted(METHODS))})"
        )
    if semantics.interpretation and not semantics.observation:
        errors.append(
            "interpretation without observation breaks the fact / reading "
            "separation"
        )
    if semantics.method in METHODS:
        if not semantics.observation:
            errors.append(
                "observation required once a method is declared "
                "(facts are recorded separately from interpretation)"
            )
        if (not semantics.scope
                and semantics.method not in SCOPE_EXEMPT_METHODS):
            errors.append(
                f"scope required for method {semantics.method!r} "
                "(generalization bounds; only static-inspection is exempt)"
            )
    return errors


def _entry_label(entry: dict) -> str:
    criterion = _text(entry.get("criterion")) or "?"
    artifact = _text(entry.get("artifact")) or "?"
    return f"{criterion}/{artifact}"


def check_method_semantics(
        entries: list[dict],
        ledger_rows: list[tuple[str, str, str]],
) -> tuple[list[Finding], list[Finding]]:
    """G6-adjacent gate over manifest method semantics.

    ``ledger_rows`` carries ``(criterion, result, observed-token)`` triples.
    Returns ``(errors, warnings)``. Errors: structural key violations, and
    any pass ledger row whose latest bound entry is unusable. Warnings:
    unusable entries that support no pass row (quarantined as blocked
    evidence — recorded, never silently dropped, never a pass basis).
    """
    errs: list[Finding] = []
    warns: list[Finding] = []
    for entry in entries:
        label = _entry_label(entry)
        for error in entry_errors(entry):
            errs.append(finding(
                "G6.method_invalid",
                f"G6 method: manifest entry {label}: {error}",
                owner="evidence/manifest.jsonl",
                expected="method enum + observation (+ interpretation), "
                         "scope, population+ethics when human-subject",
                actual=error,
                repair="Rewrite the entry's method-semantics keys at the "
                       "binding site (append a newer entry; latest wins)",
            ))

    # Pass rows must not rest on unusable evidence (#29-Q2 linkage).
    for criterion, result, observed in ledger_rows:
        if result.casefold() != "pass":
            continue
        if not observed.casefold().startswith("evidence/"):
            continue  # free-text observed: planning-only face, G6 skips
        leaf = observed[len("evidence/"):]
        bound = [
            entry for entry in entries
            if _text(entry.get("criterion")) == criterion
            and _text(entry.get("artifact")) == leaf
        ]
        if not bound:
            continue  # binding itself is G6.no_binding's diagnostic
        latest = max(bound, key=lambda m: _text(m.get("ts")))
        reason = parse_method_semantics(latest).unusable_reason
        if reason:
            errs.append(finding(
                "G6.method_unusable_pass",
                f"G6 method: {criterion} pass rests on unusable evidence "
                f"{observed}: {reason}",
                owner=f"point-back.md#{criterion}",
                expected="usable bound evidence (population+ethics present "
                         "for human-subject methods)",
                actual=reason,
                repair="Record population+ethics in a newer manifest entry "
                       "or rebind the pass row to usable evidence",
            ))

    # Quarantine: unusable entries that support no pass row are warned.
    pass_bound_leaves = {
        (criterion, observed[len("evidence/"):])
        for criterion, result, observed in ledger_rows
        if result.casefold() == "pass"
        and observed.casefold().startswith("evidence/")
    }
    for entry in entries:
        reason = parse_method_semantics(entry).unusable_reason
        if not reason:
            continue
        key = (_text(entry.get("criterion")),
               _text(entry.get("artifact")))
        if key in pass_bound_leaves:
            continue  # already an error above
        warns.append(finding(
            "G6.method_unusable_quarantined",
            f"G6 method: manifest entry {_entry_label(entry)} unusable "
            f"({reason}); quarantined as blocked evidence — it cannot "
            "support any judgment",
            owner="evidence/manifest.jsonl",
            expected="population+ethics on human-subject evidence",
            actual=reason,
            repair="Record consent/anonymisation/retention (ethics) and "
                   "the population, or stop binding the artifact",
            severity="warning",
        ))
    return errs, warns
