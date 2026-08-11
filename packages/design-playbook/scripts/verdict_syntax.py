"""Single Verdict syntax-facts parser (ADR-0025).

This is the one deep module that parses the Verdict section of point-back
text into information-preserving syntax facts. It applies no gate or status
policy: G3 (g2_g4_pointback) and run status (run_status) project their
existing diagnostics and status decisions from the result.

The facts recorded are exactly those the two consumers previously
reconstructed independently and with different fidelity:

* heading cardinality - the number of ``## Verdict`` headings in the text;
* value cardinality - the number of Pass/Recirculate verdict values in the
  (first) Verdict section body, with the punctuation G3 historically
  accepts (optional list marker, optional bold/italic, case-insensitive,
  word boundary);
* the canonical value - exposed only when exactly one valid Verdict exists
  (one heading and one value), so run status can never report a completed
  run from missing, malformed, ambiguous, or repeated Verdict text.

G3 retains its diagnostic mapping (G3.missing_verdict /
G3.repeated_verdict / G3.verdict_count). Run status reports
``Run complete (Pass)`` only from one uniquely valid ``Pass``.

Ledger and Verdict stay separate modules (ADR-0025): this module does not
parse Evidence ledger rows and is not consumed by G2/G6. It lives in
``scripts/`` next to both of its consumers (g2_g4_pointback and run_status)
rather than next to the unrelated Evidence ledger module.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# A Verdict heading: ``#+`` followed by optional whitespace, the literal
# ``Verdict``, then end-of-line. Trailing text (e.g. ``## Verdict notes``)
# is NOT a Verdict section - this strict anchor is what stops run status
# from completing a run on a misshapen heading. ``re.I`` accepts any casing.
_VERDICT_HEADING = re.compile(r"^#+\s*Verdict\s*$", re.I | re.M)

# A verdict value within the section body: optional leading whitespace, an
# optional list marker (``-`` or ``*`` plus optional whitespace), then up to
# two bold/italic markers, then ``Pass`` or ``Recirculate`` at a word
# boundary. This is the exact punctuation G3 historically accepted;
# preserving it keeps the migration behavior-compatible. ``re.I`` accepts
# any casing; the captured value is casefolded into VerdictFacts.values.
_VERDICT_VALUE = re.compile(
    r"^\s*(?:[-*]\s*)?\*{0,2}(Pass|Recirculate)\b",
    re.I | re.M,
)

# The next markdown heading, used to bound the Verdict section body so a
# ``Pass`` in a later section is never counted as the verdict.
_NEXT_HEADING = re.compile(r"^#+\s+", re.M)


@dataclass(frozen=True)
class VerdictFacts:
    """Parsed Verdict syntax facts.

    ``heading_count`` is the number of ``## Verdict`` headings in the text.
    ``value_count`` is the number of Pass/Recirculate values found in the
    first Verdict section body (0 when no heading exists). ``values`` lists
    them casefolded, in occurrence order. ``canonical`` is the casefolded
    verdict (``"pass"`` or ``"recirculate"``) only when exactly one heading
    and one value exist; otherwise ``None`` - which is what prevents run
    status from completing a run on missing, malformed, ambiguous, or
    repeated Verdict text.
    """

    heading_count: int
    value_count: int
    values: tuple[str, ...]
    canonical: str | None


def parse_verdict(text: str) -> VerdictFacts:
    """Parse point-back text into Verdict syntax facts.

    No policy is applied: every heading and value is reported regardless of
    multiplicity, so G3 and run status can project their own diagnostics
    and status decisions. The canonical value is exposed only when exactly
    one valid Verdict exists (one heading and one value).
    """
    headings = list(_VERDICT_HEADING.finditer(text))
    heading_count = len(headings)
    if heading_count == 0:
        return VerdictFacts(0, 0, (), None)

    start = headings[0].end()
    next_heading = _NEXT_HEADING.search(text[start:])
    end = start + next_heading.start() if next_heading else len(text)
    body = text[start:end]
    values = tuple(v.casefold() for v in _VERDICT_VALUE.findall(body))
    value_count = len(values)
    canonical = values[0] if heading_count == 1 and value_count == 1 else None
    return VerdictFacts(heading_count, value_count, values, canonical)
