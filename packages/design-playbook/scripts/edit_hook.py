#!/usr/bin/env python3
"""Edit-time hook: run the *source-decidable* slice of the rule registry.

Declared by ``hooks/hooks.json`` on the post-edit event, this entry reads the
host payload from stdin, re-reads the file the agent just changed, and returns
findings as a hint. It never blocks: a detector exception, a missing entry
point, or an unreadable file exits 0 with no output.

What the hook can judge from source (the whole list)
----------------------------------------------------
``A11Y-03`` — contrast, for the narrow case where one declaration block
carries *literal* values for foreground, background, and text size. The pair
and its floor are then computable without a cascade, and the registry's own
``detectors.contrast:detect`` judges it (no threshold is restated here).
``font-weight`` is read when literal; a block whose size lands in the
19-23.99 px window without a literal weight is skipped, because bold there
moves the floor and guessing would invent a threshold.

What the hook cannot judge (and why "hooked" is not "all rules are running")
----------------------------------------------------------------------------
``A11Y-03`` (the rest of it) — the resolved foreground/background comes from
the cascade, not from one block; ``var()``, inherited colors, gradients,
images and alpha colors have no single source-layer pair, and the
cross-appearance signal needs node matching across captures.
``A11Y-04`` — hit-target size needs measured target boxes from a rendered
viewport; source has no boxes.
``A11Y-05`` — the detector requires the 200 percent zoom capture plus computed
text metrics; source has neither.
``CRAFT-11`` — unbound in the registry itself: no machine-readable scale
artifact, and the check needs layout-tree adjacency.
The other 26 registry rules are ``check-type: protocol-check``, judged by the
evaluator layer over declared artifacts, not by a source scan.

So the hook covers one rule, partially, and every hint it prints repeats that
boundary. A finding never implies the other rules ran.

Scope: ``.css`` files only. ``<style>`` blocks and inline ``style=""`` in
HTML or JSX are not scanned — that needs a template or CSS-in-JS parser.
"""
from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

SCANNED_SUFFIX = ".css"
CONTRAST_RULE = "A11Y-03"
APPEARANCE_NAME = "source"
_BOUNDARY = (
    "Edit-time coverage: A11Y-03 same-block literal pairs only. A11Y-04, "
    "A11Y-05, CRAFT-11 and the protocol-check rules are not source-decidable; "
    "run the run-level detectors before declaring done."
)

#: Rule ids the source layer can judge at all, with the subset it covers.
SOURCE_DECIDABLE: dict[str, str] = {
    "A11Y-03": "same-block literal color + opaque background + font-size",
}

#: Registry rule ids the source layer cannot judge, with the missing input.
NOT_SOURCE_DECIDABLE: dict[str, str] = {
    "A11Y-03": (
        "outside the literal same-block triple: the resolved pair comes from "
        "the cascade (var(), inheritance, gradients, images, alpha colors)"
    ),
    "A11Y-04": "needs measured target boxes from a rendered viewport",
    "A11Y-05": "needs the 200 percent zoom capture plus computed text metrics",
    "CRAFT-11": "unbound in the registry: no scale artifact, needs layout-tree",
}

_HEX = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_PX = re.compile(r"^(\d+(?:\.\d+)?)px$")
_WEIGHT = re.compile(r"^(\d{3})$")
_BLOCK = re.compile(r"([^{}]*)\{([^{}]*)\}")
_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_IMPORTANT = re.compile(r"!\s*important$", re.IGNORECASE)
_LABEL_MAX = 60
#: The only width where an unknown literal font-weight moves the floor.
_DENSE_WEIGHT_FROM_PX = 19.0
_DENSE_WEIGHT_TO_PX = 24.0

Runner = Callable[[str, object], list[dict[str, Any]]]
_PAYLOAD_KEYS = ("label", "foreground", "background", "kind", "fontSizePx", "bold")


def _literal_hex(value: str) -> str | None:
    """Return ``value`` when it is exactly one opaque hex color, else None."""
    token = value.strip().lower()
    return token if _HEX.match(token) else None


def _opaque_background(declarations: Mapping[str, str]) -> str | None:
    explicit = declarations.get("background-color")
    if explicit is not None:
        return _literal_hex(explicit)
    shorthand = declarations.get("background")
    if shorthand is None:
        return None
    # Only a shorthand that is exactly one color counts: `url(...) #fff`,
    # gradients and layered shorthands have no single source-layer pair.
    return _literal_hex(shorthand)


def _font_size(declarations: Mapping[str, str]) -> float | None:
    raw = declarations.get("font-size")
    if raw is None:
        return None
    match = _PX.match(raw.strip().lower())
    return float(match.group(1)) if match else None


def _bold(declarations: Mapping[str, str]) -> bool | None:
    raw = declarations.get("font-weight")
    if raw is None:
        return None
    token = raw.strip().lower()
    if token in ("bold", "bolder"):
        return True
    if token in ("normal", "lighter"):
        return False
    match = _WEIGHT.match(token)
    return int(match.group(1)) >= 700 if match else None


def _declarations(body: str) -> dict[str, str]:
    """Split one declaration block; the last declaration of a property wins."""
    declarations: dict[str, str] = {}
    for statement in body.split(";"):
        name, separator, value = statement.partition(":")
        key = name.strip().lower()
        if not separator or not key:
            continue
        cleaned = _IMPORTANT.sub("", value.strip()).strip()
        declarations[key] = cleaned
    return declarations


def _label(selector: str) -> str:
    collapsed = " ".join(selector.split())
    if len(collapsed) <= _LABEL_MAX:
        return collapsed
    return collapsed[: _LABEL_MAX - 1] + "..."


def source_pairs(css: str) -> list[dict[str, Any]]:
    """Pairs from same-block literal triples, in file order (may be empty)."""
    stripped = _COMMENT.sub("", css)
    pairs: list[dict[str, Any]] = []
    for match in _BLOCK.finditer(stripped):
        declarations = _declarations(match.group(2))
        foreground = declarations.get("color")
        if foreground is None:
            continue
        background = _opaque_background(declarations)
        size = _font_size(declarations)
        if background is None or size is None:
            continue
        bold = _bold(declarations)
        if bold is None and _DENSE_WEIGHT_FROM_PX <= size < _DENSE_WEIGHT_TO_PX:
            continue
        pairs.append({
            "label": _label(match.group(1)) or "(anonymous block)",
            "foreground": foreground.strip(),
            "background": background,
            "kind": "text",
            "fontSizePx": size,
            "bold": bool(bold),
            "line": stripped.count("\n", 0, match.start()) + 1,
        })
    return pairs


def _payload(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    """The detector payload; ``line`` stays out of it (it is our own note)."""
    return {
        "appearances": [{
            "name": APPEARANCE_NAME,
            "pairs": [
                {key: pair[key] for key in _PAYLOAD_KEYS} for pair in pairs
            ],
        }],
    }


def _runner_or_default(runner: Runner | None) -> Runner:
    """Resolve the runner at call time so tests (and a missing entry) win."""
    if runner is not None:
        return runner
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import rules_registry

    return rules_registry.run_detector


def check_file(path: Path, runner: Runner | None = None) -> list[dict[str, Any]]:
    """Findings for one file; empty when it is out of scope or clean."""
    if path.suffix.lower() != SCANNED_SUFFIX:
        return []
    pairs = source_pairs(path.read_text(encoding="utf-8", errors="replace"))
    if not pairs:
        return []
    findings = _runner_or_default(runner)(CONTRAST_RULE, _payload(pairs))
    by_label = {pair["label"]: pair["line"] for pair in pairs}
    for finding in findings:
        label = finding.get("evidence", {}).get("label")
        if label in by_label:
            finding["line"] = by_label[label]
    return findings


def edited_path(payload: object) -> Path | None:
    """The file path a post-edit host payload names, if it names one."""
    if not isinstance(payload, Mapping):
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, Mapping):
        return None
    for key in ("file_path", "notebook_path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            return Path(value.strip())
    return None


def render(findings: list[dict[str, Any]], path: Path) -> str:
    """The hint text; empty when there is nothing to report."""
    if not findings:
        return ""
    body = "\n".join(
        f"- {CONTRAST_RULE}"
        + (f" (line {finding['line']})" if finding.get("line") else "")
        + f": {finding.get('message', '')}"
        for finding in findings
    )
    return f"design-playbook edit-time check on {path.name}\n{body}\n{_BOUNDARY}"


def main(
        stdin: Any = None,
        stdout: Any = None,
        runner: Runner | None = None,
) -> int:
    """Read one host payload, print a hint, always exit 0 (never blocks)."""
    source = stdin if stdin is not None else sys.stdin
    sink = stdout if stdout is not None else sys.stdout
    try:
        raw = source.read()
        payload = json.loads(raw) if raw.strip() else {}
        path = edited_path(payload)
        if path is None:
            return 0
        hint = render(check_file(path, runner), path)
        if hint:
            sink.write(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": hint,
            }}) + "\n")
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    # T-081: the one pipe-encoding seam. The hook prints findings, so its
    # output must be UTF-8 on a host whose code page is not.
    for _candidate in Path(__file__).resolve().parents:
        if (_candidate / "design_playbook.py").is_file():
            sys.path.insert(0, str(_candidate))
            break
    from design_playbook.scripts.stdio_encoding import configure_piped_utf8

    configure_piped_utf8()
    sys.exit(main())
