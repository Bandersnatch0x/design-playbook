"""The one Python frontmatter parser for skills and command prompts.

``generate_adapter.py`` renders prompts from the same files ``scripts/validate.py``
checks. Two parsers meant a file could pass one and be dropped by the other;
this module is the shared reading rule. Values are single-line (YAML-lite),
which is all the shipped files use.
"""
from __future__ import annotations

import re

_KEY_VALUE = re.compile(r"^([\w-]+):\s*(.+)$")


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Return ``(meta, body)``. A file without frontmatter is all body."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta: dict[str, str] = {}
    for line in parts[1].splitlines():
        match = _KEY_VALUE.match(line)
        if match:
            meta[match.group(1)] = match.group(2).strip()
    return meta, parts[2].lstrip("\n")
