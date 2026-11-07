"""Same-page defect facts for screenshot captures (page-probe/v1).

Provider artifacts only — never a verdict. Layout metrics stay in
``disclosure.py`` (handoff contract). This module owns leak / tap-target
JavaScript and the fail-closed parser for evaluate output.
"""
from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable

TAP_MIN_PX = 24
LEAK_KINDS = (
    "undefined",
    "NaN",
    "[object Object]",
    "lorem ipsum",
)
PROBE_SCHEMA = "page-probe/v1"

# Single IIFE; TAP_MIN inlined so the browser has no Python names.
DEFECT_PROBE_JS = (
    "() => {"
    f"  const TAP_MIN = {TAP_MIN_PX};"
    "  const hasLeak = (s) => {"
    "    const t = String(s == null ? '' : s);"
    "    if (/\\bundefined\\b/i.test(t)) return 'undefined';"
    "    if (/\\[object Object\\]/.test(t)) return '[object Object]';"
    "    if (/\\blorem ipsum\\b/i.test(t)) return 'lorem ipsum';"
    "    if (/\\bNaN\\b/.test(t)) return 'NaN';"
    "    return null;"
    "  };"
    "  const leaks = [];"
    "  const seen = {};"
    "  const addLeak = (kind, text) => {"
    "    const key = kind + '\\0' + text;"
    "    if (seen[key]) return;"
    "    seen[key] = 1;"
    "    leaks.push({kind: kind, text: text});"
    "  };"
    "  const walk = document.createTreeWalker("
    "    document.body || document.documentElement,"
    "    NodeFilter.SHOW_TEXT"
    "  );"
    "  while (walk.nextNode()) {"
    "    const raw = (walk.currentNode.textContent || '').trim();"
    "    if (!raw) continue;"
    "    const kind = hasLeak(raw);"
    "    if (kind) addLeak(kind, raw.slice(0, 80));"
    "  }"
    "  const nodes = document.querySelectorAll("
    "    'input, textarea, img, [placeholder], [alt]'"
    "  );"
    "  for (const el of nodes) {"
    "    const raw = String("
    "      el.value || el.getAttribute('placeholder') || el.alt || ''"
    "    ).trim();"
    "    if (!raw) continue;"
    "    const kind = hasLeak(raw);"
    "    if (kind) addLeak(kind, raw.slice(0, 80));"
    "  }"
    "  const tapFails = [];"
    "  const controls = document.querySelectorAll("
    "    'a, button, [role=\"button\"], input, select, textarea'"
    "  );"
    "  for (const el of controls) {"
    "    const r = el.getBoundingClientRect();"
    "    if (r.width <= 0 || r.height <= 0) continue;"
    "    const edge = Math.min(r.width, r.height);"
    "    if (edge < TAP_MIN) {"
    "      tapFails.push({"
    "        tag: (el.tagName || '').toLowerCase(),"
    "        width: Math.round(r.width),"
    "        height: Math.round(r.height)"
    "      });"
    "    }"
    "  }"
    "  return {leaks: leaks, tapFails: tapFails};"
    "}"
)


RENDER_TOKEN_SCHEMA = "page-render-tokens/v1"
RENDER_AXES = ("font-size", "color", "radius")
# Sub-pixel slack: a relative unit resolves to a fractional px value and the
# browser rounds the computed string.
RENDER_TOLERANCE_PX = 0.5
_FINDING_KINDS = {
    "font-size": ("off-scale-size",),
    "color": ("off-palette-color",),
    "radius": (
        "off-scale-radius",
        "inner-radius-exceeds-outer",
        "inner-radius-not-concentric",
    ),
}

# Same single-IIFE shape as DEFECT_PROBE_JS: one evaluate round trip, no Python
# names in the browser. __DECLARED__ becomes a JSON literal built here; a null
# scale means that axis has no declaration to compare against, so the check is
# skipped rather than silently reported clean.
RENDER_TOKEN_PROBE_JS = """() => {
  const DECL = __DECLARED__;
  const TOL = __TOL__;
  const findings = [];
  const undecidable = [];
  const seen = {};
  const seenNotes = {};
  const sizes = {};
  const add = (axis, kind, value, detail) => {
    const key = axis + '|' + kind + '|' + value;
    if (seen[key]) { seen[key].count += 1; return; }
    const row = {axis: axis, kind: kind, value: value, detail: detail, count: 1};
    seen[key] = row;
    findings.push(row);
  };
  const note = (axis, reason) => {
    const key = axis + '|' + reason;
    if (seenNotes[key]) return;
    seenNotes[key] = 1;
    undecidable.push({axis: axis, reason: reason});
  };
  const num = (v) => { const n = parseFloat(v); return isFinite(n) ? n : null; };
  const onScale = (scale, value) => scale.some((s) => Math.abs(s - value) <= TOL);
  // Computed colors come back as rgb()/rgba(). A translucent value is painted
  // over whatever is behind it, so it is not comparable to an opaque palette.
  const channel = (v) => {
    const m = String(v).match(/^rgba?\\(([^)]+)\\)$/);
    if (!m) return null;
    const parts = m[1].split(/[\\s,\\/]+/).filter((p) => p !== '');
    if (parts.length < 3) return null;
    const alpha = parts.length > 3 ? parseFloat(parts[3]) : 1;
    if (!(alpha > 0)) return {skip: 'transparent'};
    if (alpha < 1) return {skip: 'translucent'};
    return {key: 'rgb(' + parts[0] + ', ' + parts[1] + ', ' + parts[2] + ')'};
  };
  const CORNERS = [
    'borderTopLeftRadius', 'borderTopRightRadius',
    'borderBottomRightRadius', 'borderBottomLeftRadius'
  ];
  // The painted surface is body and its descendants. The document element is
  // read for its canvas background only: its own colour is the user-agent
  // default whenever a page sets text colour on body, which is a false
  // deviation rather than a rendered one.
  const body = document.body;
  const paintedEls = body
    ? [body].concat(Array.prototype.slice.call(body.querySelectorAll('*')))
    : [];
  const root = document.documentElement;
  if (DECL.colors && root) {
    const canvas = channel(getComputedStyle(root).backgroundColor);
    if (canvas && canvas.skip === 'translucent') {
      note('color', 'translucent document canvas: a composited value is not '
        + 'comparable to an opaque declared palette');
    } else if (canvas && canvas.key && DECL.colors.indexOf(canvas.key) < 0) {
      add('color', 'off-palette-color', canvas.key, 'document-canvas');
    }
  }
  for (const el of paintedEls) {
    const box = el.getBoundingClientRect();
    if (box.width <= 0 && box.height <= 0) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const tag = (el.tagName || '').toLowerCase();
    const size = num(cs.fontSize);
    if (size !== null) {
      sizes[String(size)] = 1;
      if (DECL.fontSizes && !onScale(DECL.fontSizes, size)) {
        add('font-size', 'off-scale-size', String(size), tag);
      }
    }
    if (DECL.colors) {
      const roles = [
        ['color', cs.color],
        ['background-color', cs.backgroundColor]
      ];
      const borderWidth = num(cs.borderTopWidth);
      if (borderWidth !== null && borderWidth > 0 && cs.borderTopStyle !== 'none') {
        roles.push(['border-color', cs.borderTopColor]);
      }
      for (const [role, raw] of roles) {
        const c = channel(raw);
        if (!c) continue;
        if (c.skip === 'translucent') {
          note('color', 'translucent ' + role + ': a composited value is not '
            + 'comparable to an opaque declared palette');
          continue;
        }
        if (c.key && DECL.colors.indexOf(c.key) < 0) {
          add('color', 'off-palette-color', c.key, role);
        }
      }
    }
    const radii = CORNERS.map((k) => num(cs[k])).filter((v) => v !== null);
    const rounded = radii.filter((v) => v > TOL);
    if (!rounded.length) continue;
    const inner = Math.max.apply(null, rounded);
    if (DECL.radii) {
      for (const v of rounded) {
        if (!onScale(DECL.radii, v)) add('radius', 'off-scale-radius', String(v), tag);
      }
    }
    let parent = el.parentElement;
    let outer = null;
    while (parent && parent !== document.documentElement) {
      const pcs = getComputedStyle(parent);
      const values = CORNERS.map((k) => num(pcs[k])).filter((v) => v !== null && v > TOL);
      if (values.length) {
        outer = {el: parent, cs: pcs, value: Math.max.apply(null, values)};
        break;
      }
      parent = parent.parentElement;
    }
    if (!outer) continue;
    const outerBox = outer.el.getBoundingClientRect();
    const inside = box.left >= outerBox.left - TOL && box.top >= outerBox.top - TOL
      && box.right <= outerBox.right + TOL && box.bottom <= outerBox.bottom + TOL;
    if (!inside) continue;
    if (inner > outer.value + TOL) {
      add('radius', 'inner-radius-exceeds-outer', String(inner), 'outer ' + outer.value);
      continue;
    }
    const pads = ['paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft']
      .map((k) => num(outer.cs[k]));
    const uniform = pads.every((v) => v !== null && Math.abs(v - pads[0]) <= TOL);
    if (!uniform) {
      note('radius', 'the rounded ancestor has non-uniform padding: which padding '
        + 'sits between the two corners is ambiguous');
      continue;
    }
    const expected = outer.value - pads[0];
    // padding alone already exceeds the outer radius: the concentric value
    // clamps to a square corner, so any radius here is a deliberate shape.
    if (expected <= TOL) continue;
    if (Math.abs(inner - expected) > TOL) {
      add('radius', 'inner-radius-not-concentric', String(inner),
        'outer ' + outer.value + ' minus padding ' + pads[0] + ' expects ' + expected);
    }
  }
  return {
    findings: findings,
    undecidable: undecidable,
    distinctFontSizes: Object.keys(sizes).map(Number).sort((a, b) => a - b)
  };
}"""


@dataclass(frozen=True)
class DefectFacts:
    """Fail-closed defect facts from one page.evaluate."""

    leaks: tuple[dict[str, str], ...] = ()
    tap_fails: tuple[dict[str, Any], ...] = ()
    measurement_status: str = "measured"
    measurement_error: str = ""


def probe_defects(evaluate: Callable[[str], Any]) -> DefectFacts:
    """Map evaluate output to coerced leak/tap facts (fail-closed)."""
    try:
        raw = evaluate(DEFECT_PROBE_JS)
    except Exception as exc:  # noqa: BLE001 — facts, not a judgment
        return DefectFacts(
            measurement_status="blocked",
            measurement_error=str(exc),
        )
    if not isinstance(raw, dict):
        return DefectFacts(
            measurement_status="blocked",
            measurement_error="defect probe output is not an object",
        )
    errors: list[str] = []
    if "leaks" not in raw:
        errors.append("leaks is missing")
        leaks: tuple[dict[str, str], ...] = ()
    else:
        leaks = _string_pairs(raw.get("leaks"), "leaks", errors)
    if "tapFails" not in raw:
        errors.append("tapFails is missing")
        taps: tuple[dict[str, Any], ...] = ()
    else:
        taps = _tap_rows(raw.get("tapFails"), errors)
    status = "blocked" if errors else "measured"
    return DefectFacts(
        leaks=leaks,
        tap_fails=taps,
        measurement_status=status,
        measurement_error="; ".join(errors),
    )


@dataclass(frozen=True)
class RenderTokenFacts:
    """Fail-closed rendered-token facts from one page.evaluate.

    ``findings`` are measured deviations from the bound declaration.
    ``undecidable`` names every axis the probe could not judge and why, so an
    empty finding list is never read as conformance on its own.
    """

    findings: tuple[dict[str, Any], ...] = ()
    undecidable: tuple[dict[str, str], ...] = ()
    distinct_font_sizes: tuple[float, ...] = ()
    measurement_status: str = "measured"
    measurement_error: str = ""


def declared_token_axes(
    declared: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], tuple[dict[str, str], ...]]:
    """Normalize a bound design declaration into per-axis probe input.

    ``axes`` keys mirror the browser-side names (``fontSizes``/``colors``/
    ``radii``); an axis is ``None`` when the declaration carries nothing usable
    for it, and each such axis is returned with a reason. A declaration entry
    this module cannot read as a literal value is reported too, never dropped.
    """
    source: Mapping[str, Any] = declared if isinstance(declared, Mapping) else {}
    axes: dict[str, Any] = {}
    notes: list[dict[str, str]] = []
    for axis, key, blank in (
        (
            "font-size",
            "fontSizes",
            "no declared type scale: off-scale font sizes cannot be judged; "
            "the distinct computed sizes are still reported as facts",
        ),
        (
            "radius",
            "radii",
            "no declared radius scale: off-scale radii cannot be judged; "
            "concentric radius relations are still measured",
        ),
    ):
        values, rejected = _px_values(source.get(key))
        axes[key] = values or None
        if not values:
            notes.append({"axis": axis, "reason": blank})
        notes.extend(
            {
                "axis": axis,
                "reason": f"declared {key} entry {literal!r} is not a finite px "
                "number: a unit or value with no rendered size cannot be compared",
            }
            for literal in rejected
        )
    colors, rejected_colors = _color_values(source.get("colors"))
    axes["colors"] = colors or None
    if not colors:
        notes.append(
            {
                "axis": "color",
                "reason": "no declared palette: off-palette colors cannot be judged",
            }
        )
    notes.extend(
        {
            "axis": "color",
            "reason": f"declared palette entry {literal!r} is not an opaque hex "
            "or rgb() color: only an opaque literal has a comparable computed value",
        }
        for literal in rejected_colors
    )
    return axes, tuple(notes)


def render_token_probe_js(declared: Mapping[str, Any] | None = None) -> str:
    """Build the rendered-token IIFE for a bound declaration."""
    axes, _ = declared_token_axes(declared)
    return _render_token_js(axes)


def probe_render_tokens(
    evaluate: Callable[[str], Any],
    declared: Mapping[str, Any] | None = None,
) -> RenderTokenFacts:
    """Map evaluate output to rendered-token findings (fail-closed).

    The concentric radius relation needs no declaration and is always measured;
    the scale and palette comparisons run only where the declaration supplies
    them, and every other axis is named in ``undecidable``.
    """
    axes, notes = declared_token_axes(declared)
    try:
        raw = evaluate(_render_token_js(axes))
    except Exception as exc:  # noqa: BLE001 — facts, not a judgment
        return RenderTokenFacts(
            undecidable=notes,
            measurement_status="blocked",
            measurement_error=str(exc),
        )
    if not isinstance(raw, dict):
        return RenderTokenFacts(
            undecidable=notes,
            measurement_status="blocked",
            measurement_error="render token probe output is not an object",
        )
    errors: list[str] = []
    if "findings" not in raw:
        errors.append("findings is missing")
        findings: tuple[dict[str, Any], ...] = ()
    else:
        findings = _finding_rows(raw.get("findings"), errors)
    if "undecidable" not in raw:
        errors.append("undecidable is missing")
        in_page: tuple[dict[str, str], ...] = ()
    else:
        in_page = _note_rows(raw.get("undecidable"), errors)
    if "distinctFontSizes" not in raw:
        errors.append("distinctFontSizes is missing")
        sizes: tuple[float, ...] = ()
    else:
        sizes = _number_list(raw.get("distinctFontSizes"), "distinctFontSizes", errors)
    return RenderTokenFacts(
        findings=findings,
        undecidable=notes + in_page,
        distinct_font_sizes=sizes,
        measurement_status="blocked" if errors else "measured",
        measurement_error="; ".join(errors),
    )


def _render_token_js(axes: Mapping[str, Any]) -> str:
    payload = json.dumps(axes, ensure_ascii=False).replace("</", "<\\/")
    return RENDER_TOKEN_PROBE_JS.replace("__DECLARED__", payload).replace(
        "__TOL__", repr(RENDER_TOLERANCE_PX)
    )


# CSS Syntax <number>: optional sign, ASCII digits with an optional fraction
# (or a leading dot), optional exponent. ``float()`` is more permissive than
# CSS — it reads PEP 515 underscores, Unicode digits, ``inf`` and ``nan`` — so
# the grammar is checked before the conversion, never the other way round.
_CSS_NUMBER = re.compile(
    r"[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
)
# CSS Syntax whitespace is exactly TAB, LF, FF, CR and SPACE. ``str.strip()``
# and ``str.split()`` also consume NBSP, vertical tab and other Unicode spaces,
# which CSS keeps inside the token — so trimming must use this subset and let
# the number grammar reject whatever is left.
_CSS_WHITESPACE = " \t\n\r\f"
_CSS_WS_RUN = re.compile(r"[ \t\n\r\f]+")


def _css_trim(text: str) -> str:
    """Strip only CSS whitespace from both ends."""
    return text.strip(_CSS_WHITESPACE)


def _css_number(text: str) -> float | None:
    """The value of a complete CSS ``<number>`` token, or None when it is not one."""
    if _CSS_NUMBER.fullmatch(text) is None:
        return None
    try:
        number = float(text)
    except (ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _px_values(value: object) -> tuple[list[float], list[str]]:
    """Read a declared px scale; anything else comes back as rejected text."""
    if value is None:
        return [], []
    if isinstance(value, (list, tuple)):
        items: list[object] = list(value)
    else:
        items = [value]
    values: list[float] = []
    rejected: list[str] = []
    for item in items:
        number: float | None = None
        if type(item) in (int, float):
            try:
                number = float(item)
            except OverflowError:
                number = None
        elif isinstance(item, str):
            text = _css_trim(item)
            # A CSS dimension has no space between the number and the unit, and
            # the number part must be the whole prefix: "1_6px" and "16 px" are
            # not dimensions even though float() would read their number.
            number = _css_number(text[:-2]) if text[-2:].lower() == "px" else None
        # "NaNpx"/"Infinitypx"/"1e309px" have no rendered size to compare, and
        # json.dumps would hand the page a bare NaN/Infinity scale entry that
        # the browser never parses as a font size. Reject, never default.
        if number is None or not math.isfinite(number) or number < 0:
            rejected.append(str(item))
        else:
            values.append(number)
    return sorted(set(values)), rejected


def _color_values(value: object) -> tuple[list[str], list[str]]:
    """Read a declared palette into the rgb() keys the browser computes."""
    if value is None:
        return [], []
    if isinstance(value, Mapping):
        items = list(value.values())
    elif isinstance(value, (list, tuple)):
        items = list(value)
    elif isinstance(value, str):
        items = [value]
    else:
        return [], []
    keys: list[str] = []
    rejected: list[str] = []
    for item in items:
        key = _color_key(item)
        if key is None:
            rejected.append(str(item))
        else:
            keys.append(key)
    return sorted(set(keys)), rejected


_HEX_COLOR = re.compile(r"^#([0-9a-f]{3}|[0-9a-f]{6})$")
_RGB_COLOR = re.compile(r"^rgba?\(([^)]+)\)$")


def _color_key(value: object) -> str | None:
    """Return the ``rgb(r, g, b)`` key the browser computes for a literal.

    Only an opaque literal has a comparable computed value: a translucent
    colour composes over whatever is behind it, so it is rejected (and thus
    named undecidable) rather than silently compared as its opaque channels.
    """
    if not isinstance(value, str):
        return None
    text = _css_trim(value).lower()
    match = _HEX_COLOR.match(text)
    if match:
        digits = match.group(1)
        if len(digits) == 3:
            digits = "".join(char * 2 for char in digits)
        channels = [int(digits[index : index + 2], 16) for index in (0, 2, 4)]
    else:
        match = _RGB_COLOR.match(text)
        if not match:
            return None
        parts, alpha = _rgb_body(match.group(1))
        if parts is None or (alpha is not None and not _opaque_alpha(alpha)):
            return None
        channels = []
        for part in parts:
            value = _css_number(part)
            if value is None or value < 0 or value > 255:
                return None
            # The browser serializes a fractional channel by rounding to the
            # nearest integer with ties toward +infinity (12.5 -> 13); Python's
            # round() is banker's rounding and would produce 12.
            channels.append(int(math.floor(value + 0.5)))
    if any(channel < 0 or channel > 255 for channel in channels):
        return None
    return "rgb({}, {}, {})".format(*channels)


def _rgb_body(body: str) -> tuple[list[str] | None, str | None]:
    """Split a modern ``rgb()`` body into three channels and an optional alpha.

    The comma form takes ``rgb(r, g, b[, a])``; the space form takes
    ``rgb(r g b[ / a])``. Anything else is malformed, and a malformed literal
    is never read as an opaque colour.
    """
    if "/" in body:
        if body.count("/") != 1:
            return None, None
        channel_text, alpha_text = body.split("/")
        parts = _CSS_WS_RUN.split(_css_trim(channel_text))
        alpha = _css_trim(alpha_text)
        if not alpha or len(parts) != 3 or not all(parts):
            return None, None
        return parts, alpha
    if "," in body:
        parts = [_css_trim(part) for part in body.split(",")]
        if len(parts) not in (3, 4) or not all(parts):
            return None, None
        return parts[:3], (parts[3] if len(parts) == 4 else None)
    parts = _CSS_WS_RUN.split(_css_trim(body))
    if len(parts) != 3 or not all(parts):
        return None, None
    return parts, None


def _opaque_alpha(text: str) -> bool:
    """True only for the alpha spellings that paint fully opaque."""
    if text.endswith("%"):
        value = _css_number(text[:-1])
        return value is not None and value == 100
    value = _css_number(text)
    return value is not None and value == 1


def _finding_rows(value: object, errors: list[str]) -> tuple[dict[str, Any], ...]:
    if value is None:
        errors.append("findings is null")
        return ()
    if not isinstance(value, list):
        errors.append("findings is not a list")
        return ()
    rows: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            errors.append("findings item is not an object")
            continue
        axis = item.get("axis")
        kind = item.get("kind")
        literal = item.get("value")
        detail = item.get("detail")
        count = item.get("count")
        if not isinstance(axis, str) or axis not in _FINDING_KINDS:
            errors.append(f"findings item axis is unknown: {axis!r}")
            continue
        if not isinstance(kind, str) or kind not in _FINDING_KINDS[axis]:
            errors.append(f"findings item kind is unknown for {axis}: {kind!r}")
            continue
        if not isinstance(literal, str) or not isinstance(detail, str):
            errors.append("findings item missing value/detail")
            continue
        if type(count) is not int or count < 1:
            errors.append("findings item count is not a positive integer")
            continue
        rows.append(
            {
                "axis": axis,
                "kind": kind,
                "value": literal,
                "detail": detail,
                "count": count,
            }
        )
    return tuple(rows)


def _note_rows(value: object, errors: list[str]) -> tuple[dict[str, str], ...]:
    if value is None:
        errors.append("undecidable is null")
        return ()
    if not isinstance(value, list):
        errors.append("undecidable is not a list")
        return ()
    rows: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            errors.append("undecidable item is not an object")
            continue
        axis = item.get("axis")
        reason = item.get("reason")
        if not isinstance(axis, str) or not isinstance(reason, str):
            errors.append("undecidable item missing axis/reason")
            continue
        rows.append({"axis": axis, "reason": reason})
    return tuple(rows)


def _number_list(value: object, name: str, errors: list[str]) -> tuple[float, ...]:
    if value is None:
        errors.append(f"{name} is null")
        return ()
    if not isinstance(value, list):
        errors.append(f"{name} is not a list")
        return ()
    rows: list[float] = []
    for item in value:
        if type(item) not in (int, float):
            errors.append(f"{name} item is not numeric")
            continue
        rows.append(float(item))
    return tuple(rows)


def _string_pairs(
    value: object, name: str, errors: list[str]
) -> tuple[dict[str, str], ...]:
    if value is None:
        errors.append(f"{name} is null")
        return ()
    if not isinstance(value, list):
        errors.append(f"{name} is not a list")
        return ()
    rows: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            errors.append(f"{name} item is not an object")
            continue
        kind = item.get("kind")
        text = item.get("text")
        if not isinstance(kind, str) or not isinstance(text, str):
            errors.append(f"{name} item missing kind/text")
            continue
        rows.append({"kind": kind, "text": text})
    return tuple(rows)


def _tap_rows(value: object, errors: list[str]) -> tuple[dict[str, Any], ...]:
    if value is None:
        errors.append("tapFails is null")
        return ()
    if not isinstance(value, list):
        errors.append("tapFails is not a list")
        return ()
    rows: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            errors.append("tapFails item is not an object")
            continue
        tag = item.get("tag")
        width = item.get("width")
        height = item.get("height")
        if not isinstance(tag, str):
            errors.append("tapFails item tag is not a string")
            continue
        if type(width) not in (int, float) or type(height) not in (int, float):
            errors.append("tapFails item size is not numeric")
            continue
        rows.append(
            {
                "tag": tag,
                "width": int(width),
                "height": int(height),
            }
        )
    return tuple(rows)
