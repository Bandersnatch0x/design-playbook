#!/usr/bin/env python3
"""Marker protocol SSOT for generated adapter artifacts (T-039, spec
2026-09-20 D4).

One module owns the generated-by convention: the marker-block tags, the
per-syntax comment forms, and the detection/normalization regexes. The
generator and the packaged doctor import from here instead of re-typing
string literals and regexes — changing the marker format (see issue #115
for the last one) now touches this module alone. Tests import the regexes
and marker text; fixture strings that simulate historical generated files
stay literal by design.
"""
from __future__ import annotations

import re

# Marker-block tags around generator-owned regions in shared markdown files.
BLOCK_BEGIN = "<!-- design-playbook:begin -->"
BLOCK_END = "<!-- design-playbook:end -->"

# The marker text itself, as it appears inside every comment form.
MARKER_TEXT = "generated-by design-playbook"


def generated_by_html(version: str) -> str:
    """``<!-- generated-by design-playbook v{version} -->\\n`` — the HTML
    comment form (codex/AGENTS.md, .mdc rules, windsurf/copilot files, and
    the first line inside every marker block)."""
    return f"<!-- {MARKER_TEXT} v{version} -->\n"


def generated_by_toml(version: str) -> str:
    """``# generated-by design-playbook v{version}\\n`` — the TOML comment
    form (.gemini/commands/*.toml)."""
    return f"# {MARKER_TEXT} v{version}\n"


# Detection (captures the marker version) and normalization (folds any
# marker version for byte comparison) — the doctor and the tests import
# these instead of re-deriving them.
MARKER_RE = re.compile(rf"{MARKER_TEXT} v(\d[^\s\"']*)")
MARKER_NORM_RE = re.compile(rf"{MARKER_TEXT} v\d[^\s\"']*")


def normalize_generation(text: str) -> str:
    """Marker-version + CRLF normalization for drift comparison: content
    that differs only by marker version (or line endings) compares equal."""
    return MARKER_NORM_RE.sub(f"{MARKER_TEXT} vNORM", text.replace("\r\n", "\n"))
