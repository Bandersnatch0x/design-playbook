"""Shared G6 ledger and manifest helpers (ADR-0023, ADR-0025).

``ledger_observed`` is the G6 projection over the single Evidence ledger
syntax-facts module (``mcp.evidence.ledger_syntax``): it projects the
``(criterion, leading-artifact-token)`` pairs G6 consumes from the parsed
rows. ``manifest_entries`` reads the on-disk manifest. Both the hard evidence
gate and soft warnings consume these projections; neither policy module owns
ledger parsing - the syntax facts come from one deep module (ADR-0025).
"""
from __future__ import annotations

from pathlib import Path

from design_playbook.mcp.evidence.ledger_syntax import LedgerFacts, parse_ledger
from design_playbook.scripts.run_facts import capture_run_facts


def ledger_observed(
    text: str,
    ledger_facts: LedgerFacts | None = None,
) -> list[tuple[str, str]]:
    """Return ``(criterion, observed-token)`` pairs for each contributing row.

    Projects the G6 view from the single ledger syntax-facts module
    (ADR-0025). The criterion is the first whitespace-delimited token of the
    row's first ``criterion`` value; the observed token is the derived leading
    artifact token of the row's first ``observed`` value. A row contributes a
    pair only when both are non-empty - matching the historical parser's
    ``^criterion:\\s*(\\S+)`` and ``^observed:\\s*(.+)`` row-inclusion rule.

    Trailing commentary after the token (whitespace or a (full/half-width)
    paren / comma / colon) is tolerated, so authors can annotate ``evidence/``
    rows without a false-positive G6 fail (issue 03). Free-text observed is
    unaffected - G6 only checks ``evidence/`` rows, and a leading token
    starting with ``evidence/`` never appears in free text.

    Keep the tolerated separators in sync with
    ``mcp/evidence/ledger_syntax.py`` and skills/ui-evaluator/SKILL.md (which
    teaches authors what punctuation may follow the artifact path).
    """
    pairs: list[tuple[str, str]] = []
    facts = ledger_facts or parse_ledger(text)
    for row in facts.rows:
        criterion_values = row.values("criterion")
        if not criterion_values or not criterion_values[0]:
            continue
        if not row.raw_observed:
            continue
        criterion_token = criterion_values[0].split()[0]
        pairs.append((criterion_token, row.artifact_token))
    return pairs


def manifest_entries(evidence_dir: Path) -> list[dict]:
    """Read evidence/manifest.jsonl as one dict per non-empty valid line."""
    return list(capture_run_facts(evidence_dir=evidence_dir).manifest_entries)
