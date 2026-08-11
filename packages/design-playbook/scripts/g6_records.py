"""Shared G6 ledger and manifest parsing primitives.

Both the hard evidence gate and soft warnings consume the same parsed records;
neither policy module owns the other's input model.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


def ledger_observed(text: str) -> list[tuple[str, str]]:
    """Return (criterion, observed) pairs for each evidence row.

    The G6 evidence path is the leading token of the observed line; trailing
    commentary after whitespace, a (full/half-width) paren, or a
    (full/half-width) comma / colon is tolerated so authors can annotate
    ``evidence/`` rows without a false-positive G6 fail (issue 03). Free-text
    observed is unaffected — G6 only checks evidence/ rows, and a leading
    token starting with ``evidence/`` never appears in free text.

    Keep the tolerated separators in sync with skills/ui-evaluator/SKILL.md
    (which teaches authors what punctuation may follow the artifact path).
    """
    pairs: list[tuple[str, str]] = []
    for block in re.split(r"\n\s*\n", text):
        criterion = re.search(r"^criterion:\s*(\S+)", block, re.I | re.M)
        observed_match = re.search(r"^observed:\s*(.+)$", block, re.I | re.M)
        if criterion and observed_match:
            raw = observed_match.group(1).strip()
            lead = re.match(r"[^\s（(,，:：]+", raw)
            observed = lead.group(0) if lead else raw
            pairs.append((criterion.group(1).strip(), observed))
    return pairs


def manifest_entries(evidence_dir: Path) -> list[dict]:
    """Read evidence/manifest.jsonl as one dict per non-empty valid line."""
    path = evidence_dir / "manifest.jsonl"
    if not path.is_file():
        return []
    entries: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            entries.append(data)
    return entries
