"""Single Evidence ledger syntax-facts parser (ADR-0025).

This is the one deep module that parses Evidence ledger point-back text into
information-preserving syntax facts. It applies no gate or status policy: G2
and G6 project their existing diagnostics from the result.

The facts preserved per row are exactly those the two consumers previously
reconstructed independently and with different fidelity:

* row order - the order rows (paragraph blocks) appear in the text;
* field occurrence order - the order ``criterion`` / ``required`` / ``observed``
  / ``result`` lines appear within a row, including interleaving;
* duplicate values - every value for a repeated field, in occurrence order;
* raw observed text - the stripped value of the first ``observed`` line,
  including any trailing commentary authors attach after the artifact token;
* the derived leading artifact token - the leading run of the observed value
  up to the first tolerated separator (whitespace or a full/half-width paren,
  comma, or colon), so authors can annotate ``evidence/`` rows without a
  false-positive G6 fail.

The tolerated separators mirror skills/ui-evaluator/SKILL.md, which teaches
authors what punctuation may follow the artifact path.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Evidence ledger field names (canonical lowercase).
EVIDENCE_FIELDS = ("criterion", "required", "observed", "result")

# One ``field: value`` line. ``[ \t]*`` (not ``\s*``) after the colon keeps the
# value on the same line - a blank value after the colon is preserved as the
# empty string rather than reaching onto the next line. ``re.I`` accepts any
# field-name casing; the captured name is lowercased into a FieldOccurrence.
_EVIDENCE_LINE = re.compile(
    r"^(criterion|required|observed|result):[ \t]*(.*)$",
    re.I | re.M,
)

# Leading artifact token: a run of characters that are not whitespace and not a
# tolerated trailing separator (full/half-width paren, comma, colon). When the
# raw observed value starts with such a separator the match fails and the whole
# raw value is treated as the token - which then fails the ``evidence/`` prefix
# check at the consumer, so it is handled as free text (issue 03).
_ARTIFACT_TOKEN = re.compile(r"[^\s（(,，:：]+")


@dataclass(frozen=True)
class FieldOccurrence:
    """A single ``field: value`` occurrence within a row, in order.

    ``name`` is the canonical lowercase field name; ``value`` is the stripped
    raw text of the line (before any token derivation).
    """

    name: str
    value: str


@dataclass(frozen=True)
class LedgerRow:
    """One Evidence ledger row: a paragraph block with >=1 evidence field.

    ``occurrences`` preserves field occurrence order and duplicate values.
    ``raw_observed`` and ``artifact_token`` are derived from the first
    ``observed`` occurrence (empty strings when the row has no observed line
    or the observed value is empty), matching the historical G6 first-match
    behavior; the full list of observed values remains available through
    ``values("observed")`` for G2's repeated-field check.
    """

    occurrences: tuple[FieldOccurrence, ...]
    raw_observed: str
    artifact_token: str

    def values(self, name: str) -> tuple[str, ...]:
        """All stripped values for ``name``, in occurrence order.

        Preserves duplicates. Returns an empty tuple when the field is absent.
        """
        return tuple(oc.value for oc in self.occurrences if oc.name == name)


@dataclass(frozen=True)
class LedgerFacts:
    """Parsed Evidence ledger facts: rows in input order."""

    rows: tuple[LedgerRow, ...]


def _artifact_token(raw_observed: str) -> str:
    """Derive the leading artifact token from the raw observed value.

    Matches the historical G6 derivation: the leading run up to the first
    tolerated separator, or the whole raw value when it starts with a
    separator. Empty input yields an empty token.
    """
    match = _ARTIFACT_TOKEN.match(raw_observed)
    return match.group(0) if match else raw_observed


def parse_ledger(text: str) -> LedgerFacts:
    """Parse Evidence ledger point-back text into syntax facts.

    A row is a paragraph block (text between blank lines) containing at least
    one ``criterion`` / ``required`` / ``observed`` / ``result`` line. Blocks
    with no evidence fields (prose, code fences without fields) are skipped.
    No policy is applied: every parsed row is returned regardless of field
    multiplicity or shape, so G2 and G6 can project their own diagnostics.
    """
    rows: list[LedgerRow] = []
    for block in re.split(r"\n\s*\n", text):
        matches = _EVIDENCE_LINE.findall(block)
        if not matches:
            continue
        occurrences = tuple(
            FieldOccurrence(name.lower(), value.strip())
            for name, value in matches
        )
        raw_observed = ""
        for occurrence in occurrences:
            if occurrence.name == "observed":
                raw_observed = occurrence.value
                break
        rows.append(LedgerRow(
            occurrences=occurrences,
            raw_observed=raw_observed,
            artifact_token=_artifact_token(raw_observed),
        ))
    return LedgerFacts(tuple(rows))
