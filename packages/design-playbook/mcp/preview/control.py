"""Confirm control-bar resources, builder, and feedback formatting.

Sibling module split from server.py. Loads bundled HTML/CSS/JS resources,
builds locale-aware adaptive-theme controls for runtime and frontend tests,
and formats structured annotation feedback.
"""
from __future__ import annotations

import html as html_lib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from i18n import CONFIRM_LABELS, REVISE_LABELS, t

HERE = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def _load_resources() -> tuple[str, str, str]:
    """Load immutable frontend resources bundled beside this module."""
    try:
        return tuple(
            (HERE / name).read_text(encoding="utf-8")
            for name in ("control.html", "control.css", "control.js")
        )
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(
            f"Failed to load preview control resources from {HERE}"
        ) from exc


def _build_control(round_n: int, summary: str, options: list[str]) -> str:
    """Build the injected confirm control-bar HTML (ADR-0008 floor-aware).

    Shared by _collect_via_browser (runtime) and test_floor_frontend
    (playwright) so the option/button markup is not duplicated across them.
    """
    confirm_cf = {c.casefold() for c in CONFIRM_LABELS}
    revise_cf = {r.casefold() for r in REVISE_LABELS}

    def display_label(opt: str) -> str:
        """Render known confirm/revise labels in the ACTIVE locale.

        The submitted value stays the raw option (CONFIRM/REVISE union sets
        still classify it); only the visible label is localized, so options
        a caller copied from another locale's docs cannot mix languages into
        an otherwise locale-consistent control bar.
        """
        if opt in CONFIRM_LABELS or opt.casefold() in confirm_cf:
            return t("confirm")
        if opt in REVISE_LABELS or opt.casefold() in revise_cf:
            return t("revise")
        return opt

    # JS object literal of revise labels across all locales (frontend classifies
    # a revise regardless of UI language). Keys are JSON-quoted/escaped.
    revise_js = ", ".join(
        f"{json.dumps(lbl, ensure_ascii=False)}: 1" for lbl in sorted(REVISE_LABELS))
    primary_bits: list[str] = []
    secondary_bits: list[str] = []
    confirm_desc = html_lib.escape(t("confirm_desc"), quote=True)
    revise_desc = html_lib.escape(t("revise_desc"), quote=True)
    for opt in options:
        safe_val = html_lib.escape(opt, quote=True)
        safe_label = html_lib.escape(display_label(opt))
        primary = opt in CONFIRM_LABELS or opt.casefold() in confirm_cf
        is_revise = opt in REVISE_LABELS or opt.casefold() in revise_cf
        cls = "dpb-btn dpb-btn-primary" if primary else "dpb-btn dpb-btn-secondary"
        desc = confirm_desc if primary else (revise_desc if is_revise else "")
        desc_attr = f' title="{desc}" aria-description="{desc}"' if desc else ""
        bit = (
            f'<button type="submit" name="choice" value="{safe_val}" class="{cls}"'
            f"{desc_attr}>{safe_label}</button>"
        )
        (primary_bits if primary else secondary_bits).append(bit)
    secondary_html = "\n".join(secondary_bits)
    # secondary actions surfaced on the floating pill (so revise is not hidden in the drawer)
    # Second replace rewrites the full class attr; a third partial replace would be dead.
    pill_secondary_html = "\n".join(
        b.replace('type="submit" name="choice"', 'type="button" data-pill-revise')
         .replace('class="dpb-btn dpb-btn-secondary"', 'class="dpb-btn-pill-secondary"')
        for b in secondary_bits
    )
    summary_safe = html_lib.escape(summary)
    primary_opt = next(
        (o for o in options if o in CONFIRM_LABELS or o.casefold() in confirm_cf),
        options[0] if options else t("confirm"),
    )
    primary_val = html_lib.escape(primary_opt, quote=True)
    primary_label = html_lib.escape(display_label(primary_opt))
    # JS-side strings: inject via JSON script (not .format into JS literals).
    # Translations with quotes, braces, or "/{" must not break JS or raise KeyError.
    # HTML {t_xxx} placeholders stay on .format (html.escape-safe static chrome).
    JS_KEYS = (
        "locate",
        "locate_anchor",
        "anchor_num_pre",
        "anchor_num_post",
        "anchor_placeholder",
        "remove_num_pre",
        "remove",
        "pin_count_pre",
        "pin_count_post",
        "ready",
        "not_ready",
        "pin_on",
        "pin_off",
        "terminate_confirm",
        "abort_cancelled",  # 4s-timeout a11y broadcast (window.DPB_I18N.abort_cancelled)
        "confirm_confirm",  # pill direct-confirm arm label
        "confirm_cancelled",  # 4s-timeout a11y broadcast for pill arm undo
    )
    # json.dumps is JS-safe for quotes/backslashes; also neutralize </script>
    # and U+2028/2029 (pre-ES2019 JS string breaks) in case translations ever
    # carry them — defense, not a current risk.
    i18n_json = (
        json.dumps({k: t(k) for k in JS_KEYS}, ensure_ascii=False)
        .replace("</", "<\\/")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )

    html_tpl, css_tpl, js_tpl = _load_resources()
    js_formatted = js_tpl.replace("__DPB_REVISE_LABELS__", revise_js)
    html_formatted = html_tpl.format(
        summary_safe=summary_safe,
        secondary_html=secondary_html,
        pill_secondary_html=pill_secondary_html,
        primary_val=primary_val,
        primary_label=primary_label,
        t_region=html_lib.escape(t("region_label"), quote=True),
        t_round=html_lib.escape(t("round_n", n=round_n)),
        t_annotate=html_lib.escape(t("annotate")),
        t_pill_open=html_lib.escape(t("pill_open")),
        t_not_ready=html_lib.escape(t("not_ready")),
        t_drawer_aria=html_lib.escape(t("drawer_aria"), quote=True),
        t_collapse=html_lib.escape(t("collapse"), quote=True),
        t_pin_toggle=html_lib.escape(t("pin_toggle")),
        t_pin_count=html_lib.escape(t("pin_count", n=0)),
        t_anchors_head=html_lib.escape(t("anchors_head")),
        t_anchors_empty=html_lib.escape(t("anchors_empty")),
        t_field_label=html_lib.escape(t("field_label")),
        t_field_hint=html_lib.escape(t("field_hint")),
        t_field_placeholder=html_lib.escape(t("field_placeholder"), quote=True),
        t_terminate=html_lib.escape(t("terminate")),
        t_terminate_desc=html_lib.escape(t("terminate_desc"), quote=True),
        t_draft=html_lib.escape(t("draft")),
        t_draft_desc=html_lib.escape(t("draft_desc"), quote=True),
        t_confirm_desc=html_lib.escape(t("confirm_desc"), quote=True),
    )

    return (
        f"<style>\n{css_tpl}\n</style>\n"
        f"{html_formatted}\n"
        f"<script>window.DPB_I18N = {i18n_json};</script>\n"
        f"<script>\n{js_formatted}\n</script>"
    )


def _format_feedback(feedback: str, anchors: list[dict[str, Any]]) -> str:
    feedback = (feedback or "").strip()
    if not anchors:
        return feedback
    lines = []
    if feedback:
        lines.append(feedback)
        lines.append("")
    lines.append(t("anchor_note_label", n=len(anchors)))
    for i, a in enumerate(anchors, 1):
        label = a.get("label") or a.get("tag") or "?"
        note = a.get("comment") or t("no_text")
        sel = a.get("selector") or ""
        lines.append(f"{i}. [{label}] {note} — {sel}")
    return "\n".join(lines)
