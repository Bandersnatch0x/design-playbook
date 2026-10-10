"""Own-UI self-audit: token contrast and text size of the shipped style sheets.

Reads the numbers from the rule registry (A11Y-03, A11Y-02, A11Y-05) and the
pairs to check from ``examples/self-audit/baseline.json``. A finding listed
in that ledger's ``known`` section is recorded debt; any other finding fails,
and so does a ledger entry that no longer fails (the debt was paid, so the
entry has to go).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

_PROP = re.compile(r"(--[\w-]+)\s*:\s*([^;]+);")
_FONT_PX = re.compile(r"(?<![\w-])font(?:-size)?\s*:[^;{}]*?(?<![\d.])(\d+(?:\.\d+)?)px")
_FONT_REM = re.compile(r"(?<![\w-])font-size\s*:\s*(\d*\.?\d+)rem")


@dataclass(frozen=True)
class Finding:
    key: str
    detail: str


def _blocks(css: str) -> list[tuple[str, str, str]]:
    """(enclosing at-rules, selector, body) for every leaf rule."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out: list[tuple[str, str, str]] = []
    stack: list[tuple[str, int]] = []
    start = 0
    for index, char in enumerate(css):
        if char == "{":
            stack.append((css[start:index].strip(), index))
            start = index + 1
        elif char == "}" and stack:
            selector, open_at = stack.pop()
            context = " ".join(sel for sel, _ in stack)
            out.append((context, selector, css[open_at + 1:index]))
            start = index + 1
        elif char == ";":
            start = index + 1
    return out


def appearance_tokens(css: str) -> dict[str, dict[str, str]]:
    """Custom properties per appearance (``light`` / ``dark``), aliases resolved."""
    result: dict[str, dict[str, str]] = {}
    for context, selector, body in _blocks(css):
        props = {k: v.strip() for k, v in _PROP.findall(body)}
        if not any(k.startswith("--dpb-") for k in props):
            continue
        appearance = "dark" if "dark" in selector or "dark" in context else "light"
        result.setdefault(appearance, {}).update(props)
    if "dark" in result:  # dark blocks override light ones; unset roles inherit
        result["dark"] = {**result.get("light", {}), **result["dark"]}
    for tokens in result.values():
        for _ in range(4):
            for key, value in tokens.items():
                alias = re.fullmatch(r"var\((--[\w-]+)\)", value)
                if alias and alias.group(1) in tokens:
                    tokens[key] = tokens[alias.group(1)]
    return result


def _rgba(value: str) -> tuple[float, float, float, float] | None:
    value = value.strip()
    if re.fullmatch(r"#[0-9a-fA-F]{3}|#[0-9a-fA-F]{6}", value):
        hexes = value[1:]
        if len(hexes) == 3:
            hexes = "".join(c * 2 for c in hexes)
        return (int(hexes[0:2], 16), int(hexes[2:4], 16), int(hexes[4:6], 16), 1.0)
    match = re.fullmatch(r"rgba?\(([^)]*)\)", value)
    if not match:
        return None
    parts = [float(p) for p in re.findall(r"\d*\.?\d+", match.group(1))]
    if len(parts) < 3:
        return None
    return (parts[0], parts[1], parts[2], parts[3] if len(parts) > 3 else 1.0)


def _over(top, bottom):
    alpha = top[3]
    return tuple(top[i] * alpha + bottom[i] * (1 - alpha) for i in range(3)) + (1.0,)


def _luminance(color) -> float:
    def channel(c: float) -> float:
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * channel(color[0]) + 0.7152 * channel(color[1]) + 0.0722 * channel(color[2])


def contrast(fg: str, bg: str, floor: str) -> float | None:
    """Contrast of ``fg`` over ``bg``, translucent layers composited on ``floor``."""
    fg_c, bg_c, floor_c = _rgba(fg), _rgba(bg), _rgba(floor)
    if not (fg_c and bg_c and floor_c):
        return None
    back = _over(bg_c, floor_c)
    front = _over(fg_c, back)
    high, low = sorted((_luminance(front), _luminance(back)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def token_gaps(definitions: str, consumers: str) -> list[str]:
    """G-2 findings for one token file and the text that reads it.

    ``dark-only:<token>``: set by a dark block but not by the light one, so
    the light theme has no value for it. ``undefined:<token>``: read through
    ``var()`` with no fallback but never set in the light block. ``unused:
    <token>``: set but read nowhere.
    """
    strip = lambda text: re.sub(r"/\*.*?\*/", "", text, flags=re.S)  # noqa: E731
    light: set[str] = set()
    dark: set[str] = set()
    for context, selector, body in _blocks(definitions):
        if selector.startswith("@"):
            continue
        names = {k for k, _ in _PROP.findall(body) if k.startswith("--dpb-")}
        (dark if "dark" in selector or "dark" in context else light).update(names)
    text = strip(definitions) + "\n" + strip(consumers)
    used = set(re.findall(r"var\(\s*(--dpb-[\w-]+)", text))
    bare = set(re.findall(r"var\(\s*(--dpb-[\w-]+)\s*\)", text))
    return ([f"dark-only:{name}" for name in sorted(dark - light)]
            + [f"undefined:{name}" for name in sorted(bare - light - dark)]
            + [f"unused:{name}" for name in sorted((light | dark) - used)])


def surface_sheets(surface: dict) -> list[str]:
    """The style sheets a surface loads, shared token file first."""
    return list(surface.get("stylesheets") or [surface["stylesheet"]])


def audit(root: Path, ledger: dict, floors: dict[str, float]) -> list[Finding]:
    """Every contrast and size finding across the ledger's surfaces."""
    findings: list[Finding] = []
    for surface in ledger["surfaces"]:
        missing = [rel for rel in surface_sheets(surface) if not (root / rel).is_file()]
        if missing:
            findings.append(Finding(f"{surface['name']}:missing-stylesheet", ", ".join(missing)))
            continue
        css = "\n".join((root / rel).read_text(encoding="utf-8")
                        for rel in surface_sheets(surface))
        for appearance, tokens in sorted(appearance_tokens(css).items()):
            floor = tokens.get("--dpb-bg", "#ffffff")
            for kind, pairs in (("text", ledger["text_pairs"]), ("nontext", ledger["nontext_pairs"])):
                need = floors["text-contrast"] if kind == "text" else floors["nontext-contrast"]
                for fg, bg in pairs:
                    if fg not in tokens or bg not in tokens:
                        continue
                    ratio = contrast(tokens[fg], tokens[bg], floor)
                    if ratio is not None and ratio + 1e-9 < need:
                        findings.append(Finding(
                            f"{surface['name']}:{appearance}:{fg}:{bg}",
                            f"{ratio:.2f}:1 under {need:g}:1"))
        sizes: dict[float, int] = {}
        for match in _FONT_PX.finditer(css):
            sizes[float(match.group(1))] = sizes.get(float(match.group(1)), 0) + 1
        for match in _FONT_REM.finditer(css):
            px = round(float(match.group(1)) * 16, 2)
            sizes[px] = sizes.get(px, 0) + 1
        for px, count in sorted(sizes.items()):
            if px < floors["text-min"]:
                findings.append(Finding(
                    f"{surface['name']}:font-size:{px:g}px",
                    f"{count} declaration(s) under {floors['text-min']:g}px"))
    return findings


def compare(findings: list[Finding], ledger: dict) -> tuple[list[Finding], list[str]]:
    """(findings not in the ledger, ledger entries that no longer fail)."""
    known = set(ledger.get("known", {}))
    seen = {finding.key for finding in findings}
    return ([f for f in findings if f.key not in known], sorted(known - seen))


def load_ledger(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
