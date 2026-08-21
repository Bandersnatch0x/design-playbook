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

from design_playbook.mcp.preview.i18n import CONFIRM_LABELS, REVISE_LABELS, t

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

    Shared by collect_review (runtime) and test_floor_frontend
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

    # Draft persistence key (wayfinder canvas-upgrade 07): per-run isolation so
    # one preview run's draft never leaks into another page/run.
    import hashlib
    draft_key = "dpb.draft." + hashlib.sha256(
        f"{round_n}|{summary}".encode("utf-8")).hexdigest()[:16]
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
    # Scheme A′: pill revise is a real submit (same choice value as drawer secondary).
    # Keep type=submit name=choice; only restyle for the pill.
    pill_secondary_html = "\n".join(
        b.replace('class="dpb-btn dpb-btn-secondary"', 'class="dpb-btn-pill-secondary"')
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
        "skip",
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
        "terminate_confirm_go",
        "abort_cancelled",  # popover dismiss a11y broadcast
        "abort_popover_aria",
        "quick_feedback_placeholder",
        "pin_toggle_desc",  # #58 pill annotate-button title while pinning
        "duplicate_anchor",  # #60 duplicate pick live announcement ({n})
        "onboard_title",  # #59 one-time onboarding card
        "onboard_pick",
        "onboard_write",
        "onboard_submit",
        "onboard_undo",
        "onboard_close",
    )
    # json.dumps is JS-safe for quotes/backslashes; also neutralize </script>
    # and U+2028/2029 (pre-ES2019 JS string breaks) in case translations ever
    # carry them — defense, not a current risk.
    i18n_json = (
        json.dumps({k: t(k) for k in JS_KEYS}, ensure_ascii=False)
        .replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )

    html_tpl, css_tpl, js_tpl = _load_resources()
    js_formatted = js_tpl
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
        t_drawer_title=html_lib.escape(t("drawer_title")),
        t_drawer_empty_title=html_lib.escape(t("drawer_empty_title")),
        t_drawer_empty_desc=html_lib.escape(t("drawer_empty_desc")),
        t_skip=html_lib.escape(t("skip")),
        t_skip_desc=html_lib.escape(t("skip_desc"), quote=True),
        t_zoom_fit=html_lib.escape(t("zoom_fit")),
        skip_val=html_lib.escape(t("skip"), quote=True),
        t_collapse=html_lib.escape(t("collapse"), quote=True),
        t_pin_toggle=html_lib.escape(t("pin_toggle")),
        t_pin_toggle_desc=html_lib.escape(t("pin_toggle_desc"), quote=True),
        t_pin_count=html_lib.escape(t("pin_count", n=0)),
        t_anchors_head=html_lib.escape(t("anchors_head")),
        t_field_label=html_lib.escape(t("field_label")),
        t_field_placeholder=html_lib.escape(t("field_placeholder"), quote=True),
        t_terminate=html_lib.escape(t("terminate")),
        t_terminate_desc=html_lib.escape(t("terminate_desc"), quote=True),
        t_terminate_confirm=html_lib.escape(t("terminate_confirm")),
        t_terminate_confirm_go=html_lib.escape(t("terminate_confirm_go")),
        t_abort_popover_aria=html_lib.escape(t("abort_popover_aria"), quote=True),
        t_cancel=html_lib.escape(t("cancel")),
        t_quick_feedback_placeholder=html_lib.escape(
            t("quick_feedback_placeholder"), quote=True
        ),
        t_ready_hint=html_lib.escape(t("ready_hint"), quote=True),
        t_draft=html_lib.escape(t("draft")),
        t_draft_desc=html_lib.escape(t("draft_desc"), quote=True),
        t_confirm_desc=html_lib.escape(t("confirm_desc"), quote=True),
        t_onboard_title=html_lib.escape(t("onboard_title"), quote=True),
        t_onboard_pick=html_lib.escape(t("onboard_pick")),
        t_onboard_write=html_lib.escape(t("onboard_write")),
        t_onboard_submit=html_lib.escape(t("onboard_submit")),
        t_onboard_undo=html_lib.escape(t("onboard_undo")),
        t_onboard_close=html_lib.escape(t("onboard_close")),
    )

    return (
        f"<style>\n{css_tpl}\n</style>\n"
        f"{html_formatted}\n"
        f"<script>window.DPB_I18N = {i18n_json};</script>\n"
        f"<script>window.DPB_DRAFT_KEY = {json.dumps(draft_key)};</script>\n"
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
