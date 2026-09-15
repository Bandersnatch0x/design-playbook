"""Same-page defect facts for screenshot captures (page-probe/v1).

Provider artifacts only — never a verdict. Layout metrics stay in
``disclosure.py`` (handoff contract). This module owns leak / tap-target
JavaScript and the fail-closed parser for evaluate output.
"""
from __future__ import annotations

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
    leaks = _string_pairs(raw.get("leaks"), "leaks", errors)
    taps = _tap_rows(raw.get("tapFails"), errors)
    status = "blocked" if errors else "measured"
    return DefectFacts(
        leaks=leaks,
        tap_fails=taps,
        measurement_status=status,
        measurement_error="; ".join(errors),
    )


def _string_pairs(
    value: object, name: str, errors: list[str]
) -> tuple[dict[str, str], ...]:
    if value is None:
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
