"""Static-handoff disclosure review builder (Stage 9 evidence).

Produces the ``disclosure-review.json`` delivery credential defined by the
Static Handoff spec (docs/specs/2026-08-22-interactive-review-and-static-handoff
-implementation-plan.md §4.2): a single authoritative payload binding the run
identity, verdict, profile, decision authority, the five standard viewport
layout metrics (``sw`` / ``innerH`` / ``hOverflow`` / ``disclosure.inFold``),
and the G1–G8 gate count — so a front-end/QA consumer can reproduce and audit
the delivery without re-running Playwright.

Two seams keep the contract builder pure and testable without a browser:

* ``probe_layout(evaluate)`` — one DOM probe that reads the viewport layout
  facts a page exposes. It takes a callable with the same shape as Playwright's
  ``page.evaluate`` so tests inject a stub instead of launching Chromium.
  The probe JS string is also exposed (``LAYOUT_PROBE_JS``) for a static
  syntax/structure check.
* ``build_disclosure(...)`` — deterministic pure builder: no I/O, no browser.
  It only normalizes caller-supplied facts into the §4.2 shape.

``build_handoff_zip()`` packages the disclosure credential plus any caller-
supplied snapshot artifacts into a single ZIP for the local ``/export-zip``
endpoint (Stage 9 delivery mount). It never reads outside the caller-provided
file list.
"""

from __future__ import annotations

import json
import math
import zipfile
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Callable, Literal

# The five standard delivery viewports (spec §4.1). ``sw``/``innerH`` are the
# canonical metric values the probe should observe; the probe may return its
# own measured values, but the reference table is the single source for the
# expected matrix and the zip member naming.
VIEWPORTS: dict[str, dict[str, Any]] = {
    "1280x900": {"sw": 1280, "innerH": 900, "kind": "desktop"},
    "768x1024": {"sw": 768, "innerH": 1024, "kind": "tablet"},
    "390x844": {"sw": 390, "innerH": 844, "kind": "mobile"},
    "360x800": {"sw": 360, "innerH": 800, "kind": "compact"},
    "print": {"sw": 960, "innerH": 650, "kind": "print"},
}

# The delivery payload's canonical viewport key order (spec §4.2).
VIEWPORT_ORDER: tuple[str, ...] = (
    "1280x900",
    "768x1024",
    "390x844",
    "360x800",
    "print",
)

# Fold baseline used by the probe for the desktop/tablet fold check. The
# design's first-fold line sits at 900 CSS px on desktop; narrower viewports
# fall back to their own inner height so the fold metric stays honest.
FOLD_BASELINE = 900


@dataclass(frozen=True)
class ViewportMetrics:
    """Measured layout facts for one delivery viewport (spec §4.2)."""

    sw: int
    innerH: int
    hOverflow: int
    inFold: bool
    measurement_status: Literal["measured", "unmeasured", "blocked"] = "measured"
    measurement_error: str = ""


# One DOM probe that reads the layout facts a delivery page exposes. It is a
# self-contained IIFE so it can be passed verbatim to Playwright and reasoned
# about statically. Returns ``{sw, innerH, hOverflow, inFold}``.
#
# ``FOLD_BASELINE`` is inlined as a literal (not referenced by name) so the JS
# is self-contained: a browser has no ``FOLD_BASELINE`` binding and would raise
# ReferenceError, silently breaking the inFold probe under real Playwright.
LAYOUT_PROBE_JS = (
    "() => {"
    "  const de = document.documentElement;"
    "  const be = document.body;"
    "  const sw = Math.max(de.scrollWidth, be ? be.scrollWidth : 0);"
    "  const cw = de.clientWidth;"
    "  const innerH = window.innerHeight || de.clientHeight || 0;"
    "  const hOverflow = Math.max(0, sw - cw);"
    "  const fold = document.querySelector('[data-fold]')"
    "    || document.querySelector('main') || document.body;"
    "  const rect = fold ? fold.getBoundingClientRect() : null;"
    "  const bottom = rect ? rect.bottom : 0;"
    f"  const baseline = Math.min({FOLD_BASELINE}, innerH || {FOLD_BASELINE});"
    "  const inFold = bottom > 0 && bottom <= baseline;"
    "  return { sw: sw, innerH: innerH, hOverflow: hOverflow, inFold: inFold };"
    "}"
)


def probe_layout(evaluate: Callable[[str], dict[str, Any]]) -> ViewportMetrics:
    """Run the layout probe through a ``page.evaluate``-shaped callable.

    ``evaluate`` must accept the probe JS and return the mapped object. Values
    are coerced to ints/booleans so malformed host pages cannot poison the
    contract; non-finite or negative numbers fail closed to zero.
    """
    raw = evaluate(LAYOUT_PROBE_JS)
    if not isinstance(raw, dict):
        return ViewportMetrics(
            sw=0,
            innerH=0,
            hOverflow=0,
            inFold=False,
            measurement_status="blocked",
            measurement_error="probe returned a non-object result",
        )

    errors: list[str] = []

    def _int(key: str, *, require_positive: bool = False) -> int:
        value = raw.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append(f"{key} is not numeric")
            return 0
        if not math.isfinite(value):
            errors.append(f"{key} is not finite")
            return 0
        coerced = int(value)
        if coerced < 0:
            errors.append(f"{key} is negative")
        elif require_positive and coerced == 0:
            errors.append(f"{key} is zero")
        if coerced < 0:
            return 0
        return coerced

    sw = _int("sw", require_positive=True)
    inner_h = _int("innerH", require_positive=True)
    h_overflow = _int("hOverflow")
    in_fold_raw = raw.get("inFold")
    if not isinstance(in_fold_raw, bool):
        errors.append("inFold is not boolean")
    in_fold = in_fold_raw if isinstance(in_fold_raw, bool) else False
    return ViewportMetrics(
        sw=sw,
        innerH=inner_h,
        hOverflow=h_overflow,
        inFold=in_fold,
        measurement_status="blocked" if errors else "measured",
        measurement_error="; ".join(errors),
    )


def metric_payload(m: ViewportMetrics) -> dict[str, Any]:
    """Map one viewport's metrics to the §4.2 nested ``disclosure`` shape.

    The single canonical mapper (ADR-0026 rationale: a duplicated
    implementation drifts): both ``build_disclosure`` and the capture
    runtime's matrix results go through here so the metric shape has exactly
    one definition site.
    """
    payload = {
        "sw": m.sw,
        "innerH": m.innerH,
        "hOverflow": m.hOverflow,
        "disclosure": {"inFold": m.inFold},
        "measurementStatus": m.measurement_status,
    }
    if m.measurement_error:
        payload["measurementError"] = m.measurement_error
    return payload


def _default_metrics() -> dict[str, ViewportMetrics]:
    """Reference metrics for the standard matrix — explicitly UNMEASURED.

    Used when a caller builds a disclosure without live probes. The metrics
    carry the reference ``sw``/``innerH`` but ``hOverflow``/``inFold`` are set
    to ``0``/``False`` so an unprobed viewport is never mistaken for a passed
    fold check. The payload is complete (all five entries) but honest about
    what was not measured.
    """
    out: dict[str, ViewportMetrics] = {}
    for name, ref in VIEWPORTS.items():
        out[name] = ViewportMetrics(
            sw=ref["sw"],
            innerH=ref["innerH"],
            hOverflow=0,
            inFold=False,
            measurement_status="unmeasured",
        )
    return out


def build_disclosure(
    *,
    run_id: str,
    verdict: str,
    profile: str,
    authority: str,
    timestamp: str,
    decisions: list[dict[str, str]],
    gates_passed: int,
    viewport_metrics: dict[str, ViewportMetrics] | None = None,
) -> dict[str, Any]:
    """Build the ``disclosure-review.json`` payload (spec §4.2).

    Pure and deterministic. ``viewport_metrics`` keys may be a subset of the
    standard matrix; missing viewports fall back to the reference in-fold
    metrics so the payload always carries all five entries. Decisions are
    normalized to ``{id, title, authority}``.
    """
    metrics = _default_metrics()
    if viewport_metrics is not None:
        for key, value in viewport_metrics.items():
            if key in metrics:
                metrics[key] = value

    normalized_decisions = []
    for d in decisions:
        if not isinstance(d, dict):
            continue
        normalized_decisions.append(
            {
                "id": str(d.get("id") or ""),
                "title": str(d.get("title") or ""),
                "authority": str(d.get("authority") or authority),
            }
        )

    return {
        "runId": run_id,
        "verdict": verdict,
        "profile": profile,
        "authority": authority,
        "timestamp": timestamp,
        "decisions": normalized_decisions,
        "viewports": [
            {"name": name, "metrics": metric_payload(metrics[name])}
            for name in VIEWPORT_ORDER
        ],
        "gatesPassed": gates_passed,
    }


def disclosure_json(payload: dict[str, Any]) -> str:
    """Serialize a disclosure payload as the canonical delivery JSON."""
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def build_handoff_zip(
    disclosure_payload: dict[str, Any],
    *,
    artifact_files: dict[str, str] | None = None,
    text_members: dict[str, str] | None = None,
    zip_target: str | None = None,
) -> tuple[bytes, list[str]]:
    """Package the disclosure credential + snapshot artifacts into a ZIP.

    ``artifact_files`` maps the zip member name to an absolute/relative file
    path; only those exact files are read (no directory crawling).
    ``text_members`` maps a member name to literal text, for content the
    caller holds in memory rather than on disk (spec §4.1 ships the prototype
    source alongside the snapshots). Returns ``(zip_bytes, member_names)``.
    When ``zip_target`` is given the bytes are also written there; the bytes
    are always returned so callers can stream without a temp file.
    """
    artifact_files = artifact_files or {}
    members: list[str] = ["disclosure-review.json"]
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("disclosure-review.json", disclosure_json(disclosure_payload))
        for member, text in (text_members or {}).items():
            zf.writestr(member, text)
            members.append(member)
        for member, path in artifact_files.items():
            with open(path, "rb") as fh:
                zf.writestr(member, fh.read())
            members.append(member)
    payload = buffer.getvalue()
    if zip_target is not None:
        with open(zip_target, "wb") as fh:
            fh.write(payload)
    return payload, members
