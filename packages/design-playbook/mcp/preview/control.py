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

from design_playbook.mcp.preview.i18n import (
    CONFIRM_LABELS,
    REVISE_LABELS,
    SKIP_LABELS,
    t,
)

HERE = Path(__file__).resolve().parent


def _normalise_criteria(criteria: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for criterion in criteria or []:
        if not isinstance(criterion, dict):
            continue
        criterion_id = str(
            criterion.get("id") or criterion.get("criterion_id") or ""
        ).strip()
        if not criterion_id:
            continue
        items.append({
            "id": criterion_id,
            "title": str(criterion.get("title") or "").strip(),
            "then": str(criterion.get("then") or "").strip(),
        })
    return items


def _render_criteria_cards(criteria: list[dict[str, str]]) -> str:
    if not criteria:
        return (
            '<p class="dpb-spec-empty i18n" data-i18n="criteria_empty">'
            f'{html_lib.escape(t("criteria_empty"))}</p>'
        )

    cards: list[str] = []
    for criterion in criteria:
        criterion_id = criterion["id"]
        title = criterion["title"]
        label = f"{criterion_id}: {title}" if title else criterion_id
        cards.append(
            '<article class="dpb-spec-card">'
            '<label class="dpb-spec-check-row">'
            '<input type="checkbox" class="dpb-criterion-check" '
            f'data-criterion-id="{html_lib.escape(criterion_id, quote=True)}" '
            f'data-criterion-title="{html_lib.escape(title, quote=True)}" />'
            f'<span>{html_lib.escape(label)}</span>'
            '</label>'
            f'<p>{html_lib.escape(criterion["then"])}</p>'
            '</article>'
        )
    return "\n".join(cards)


@lru_cache(maxsize=1)
def _load_resources() -> tuple[str, str, str, str]:
    """Load immutable frontend resources bundled beside this module."""
    try:
        html_tpl, css_tpl, js_tpl, review_tpl = tuple(
            (HERE / name).read_text(encoding="utf-8")
            for name in (
                "control.html",
                "control.css",
                "control.js",
                "control.review.js",
            )
        )
        marker = "/* DPB_REVIEW_INSERT */"
        if marker not in js_tpl:
            raise RuntimeError("control.js is missing the review insertion marker")
        js_tpl = js_tpl.replace(marker, review_tpl, 1)
        return html_tpl, css_tpl, js_tpl, review_tpl
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(
            f"Failed to load preview control resources from {HERE}"
        ) from exc


def _build_control(
    round_n: int,
    summary: str,
    options: list[str],
    criteria: list[dict[str, Any]] | None = None,
) -> str:
    """Build the injected confirm control-bar HTML (ADR-0008 floor-aware).

    Shared by collect_review (runtime) and test_floor_frontend
    (playwright) so the option/button markup is not duplicated across them.
    """
    confirm_cf = {c.casefold() for c in CONFIRM_LABELS}
    revise_cf = {r.casefold() for r in REVISE_LABELS}
    criteria_items = _normalise_criteria(criteria)
    criteria_hidden = html_lib.escape(
        json.dumps(
            [
                {"id": item["id"], "title": item["title"], "checked": False}
                for item in criteria_items
            ],
            ensure_ascii=False,
        ),
        quote=True,
    )
    criteria_count = len(criteria_items)
    criteria_count_label = html_lib.escape(
        t("criteria_count", checked=0, total=criteria_count)
    )
    criteria_toggle_hidden = " hidden" if criteria_count == 0 else ""

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
        "app_title",
        "locate",
        "locate_anchor",
        "skip",
        "mode_preview",
        "mode_annotate",
        "draw_label",
        "draw_on",
        "status_ready",
        "status_not_ready",
        "quick_approve",
        "filter_all",
        "filter_pending",
        "filter_resolved",
        "mark_resolved",
        "reopen",
        "tag_copy",
        "tag_layout",
        "tag_visual",
        "comment_placeholder",
        "field_label",
        "field_placeholder",
        "anchor_num_pre",
        "anchor_num_post",
        "anchor_placeholder",
        "remove_num_pre",
        "remove",
        "duplicate_anchor",
        "gate_hint",
        "terminate_confirm",
        "terminate_confirm_go",
        "abort_cancelled",
        "abort_popover_aria",
        "drawer_title",
        "criteria_title",
        "criteria_count",
        "criteria_empty",
        "criteria_toggle_title",
        "theme_toggle",
        "toast_mode_preview",
        "toast_mode_annotate",
        "toast_pin_added",
        "toast_loop_done",
        "toast_note_added",
        "toast_resolved",
        "toast_reopened",
        "toast_drawer_open",
        "toast_drawer_closed",
        "toast_lang",
        "toast_undo",
        "toast_focus",
        "toast_vp",
        "onboard_title",
        "onboard_pick",
        "onboard_write",
        "onboard_submit",
        "onboard_undo",
        "onboard_close",
    )
    # json.dumps is JS-safe for quotes/backslashes; also neutralize </script>
    # and U+2028/2029 (pre-ES2019 JS string breaks) in case translations ever
    # carry them - defense, not a current risk.
    def _js_safe(obj: object) -> str:
        return (
            json.dumps(obj, ensure_ascii=False)
            .replace("</", "<\\/")
            .replace("\u2028", "\\u2028")
            .replace("\u2029", "\\u2029")
        )

    i18n_json = _js_safe({k: t(k) for k in JS_KEYS})
    # Dual-locale dictionary for the live L toggle (v9): both tables ship so
    # the client can swap languages without a server round-trip.
    from design_playbook.mcp.preview.i18n import EN, ZH, _STRINGS

    dual_json = _js_safe(
        {k: {"zh": _STRINGS[ZH].get(k, ""), "en": _STRINGS[EN].get(k, "")}
         for k in JS_KEYS}
    )
    html_tpl, css_tpl, js_tpl, _review_tpl = _load_resources()
    js_formatted = js_tpl
    html_formatted = html_tpl.format(
        summary_safe=summary_safe,
        criteria_html=_render_criteria_cards(criteria_items),
        criteria_hidden=criteria_hidden,
        criteria_count_label=criteria_count_label,
        criteria_count=criteria_count,
        criteria_toggle_hidden=criteria_toggle_hidden,
        secondary_html=secondary_html,
        primary_val=primary_val,
        primary_label=primary_label,
        skip_val=html_lib.escape(t("skip"), quote=True),
        t_app_title=html_lib.escape(t("app_title")),
        t_round=html_lib.escape(t("round_n", n=round_n)),
        t_vp_desktop=html_lib.escape(t("vp_desktop"), quote=True),
        t_vp_tablet=html_lib.escape(t("vp_tablet"), quote=True),
        t_vp_mobile=html_lib.escape(t("vp_mobile"), quote=True),
        t_mode_preview=html_lib.escape(t("mode_preview")),
        t_mode_annotate=html_lib.escape(t("mode_annotate")),
        t_drawer_toggle=html_lib.escape(t("drawer_toggle"), quote=True),
        t_shortcuts_open=html_lib.escape(t("shortcuts_open"), quote=True),
        t_skip=html_lib.escape(t("skip")),
        t_skip_desc=html_lib.escape(t("skip_desc"), quote=True),
        t_terminate=html_lib.escape(t("terminate")),
        t_terminate_desc=html_lib.escape(t("terminate_desc"), quote=True),
        t_terminate_confirm=html_lib.escape(t("terminate_confirm")),
        t_terminate_confirm_go=html_lib.escape(t("terminate_confirm_go")),
        t_abort_popover_aria=html_lib.escape(t("abort_popover_aria"), quote=True),
        t_cancel=html_lib.escape(t("cancel")),
        t_confirm_desc=html_lib.escape(t("confirm_desc"), quote=True),
        t_tool_select=html_lib.escape(t("tool_select"), quote=True),
        t_tool_draw=html_lib.escape(t("tool_draw"), quote=True),
        t_tool_hand=html_lib.escape(t("tool_hand"), quote=True),
        t_undo_label=html_lib.escape(t("undo_label"), quote=True),
        t_zoom_out_t=html_lib.escape(t("zoom_out_t"), quote=True),
        t_zoom_in_t=html_lib.escape(t("zoom_in_t"), quote=True),
        t_zoom_fit=html_lib.escape(t("zoom_fit"), quote=True),
        t_draw_toggle=html_lib.escape(t("draw_toggle")),
        t_status_not_ready=html_lib.escape(t("status_not_ready")),
        t_quick_approve=html_lib.escape(t("quick_approve")),
        t_drawer_title=html_lib.escape(t("drawer_title")),
        t_criteria_title=html_lib.escape(t("criteria_title")),
        t_criteria_empty=html_lib.escape(t("criteria_empty")),
        t_criteria_toggle_title=html_lib.escape(t("criteria_toggle_title"), quote=True),
        t_theme_toggle=html_lib.escape(t("theme_toggle"), quote=True),
        t_roam_prev=html_lib.escape(t("roam_prev"), quote=True),
        t_roam_next=html_lib.escape(t("roam_next"), quote=True),
        t_roam_label=html_lib.escape(t("roam_label")),
        t_filter_all=html_lib.escape(t("filter_all")),
        t_filter_pending=html_lib.escape(t("filter_pending")),
        t_filter_resolved=html_lib.escape(t("filter_resolved")),
        t_tag_copy=html_lib.escape(t("tag_copy")),
        t_tag_layout=html_lib.escape(t("tag_layout")),
        t_tag_visual=html_lib.escape(t("tag_visual")),
        t_enter_hint=html_lib.escape(t("enter_hint")),
        t_comment_placeholder=html_lib.escape(t("comment_placeholder"), quote=True),
        t_comment_send=html_lib.escape(t("comment_send"), quote=True),
        t_field_label=html_lib.escape(t("field_label")),
        t_field_placeholder=html_lib.escape(t("field_placeholder"), quote=True),
        t_draft=html_lib.escape(t("draft")),
        t_draft_desc=html_lib.escape(t("draft_desc"), quote=True),
        t_lang_toggle=html_lib.escape(t("lang_toggle")),
        t_shortcuts_title=html_lib.escape(t("shortcuts_title")),
        t_group_global=html_lib.escape(t("group_global")),
        t_group_tools=html_lib.escape(t("group_tools")),
        t_got_it=html_lib.escape(t("got_it")),
        t_onboard_title=html_lib.escape(t("onboard_title")),
        t_onboard_pick=html_lib.escape(t("onboard_pick")),
        t_onboard_write=html_lib.escape(t("onboard_write")),
        t_onboard_submit=html_lib.escape(t("onboard_submit")),
        t_onboard_undo=html_lib.escape(t("onboard_undo")),
        t_onboard_close=html_lib.escape(t("onboard_close")),
    )

    # ADR-0008: SKIP_LABELS in i18n.py is the single label source. Ship the
    # whole cross-locale set rather than the active locale's word, so adding a
    # locale keeps the frontend and transaction.py in step automatically.
    skip_labels_json = json.dumps(
        sorted(label.casefold() for label in SKIP_LABELS), ensure_ascii=False
    )

    return (
        f"<style>\n{css_tpl}\n</style>\n"
        f"{html_formatted}\n"
        f"<script>window.DPB_I18N = {i18n_json};</script>\n"
        f"<script>window.DPB_I18N_DUAL = {dual_json};</script>\n"
        f"<script>window.DPB_SKIP_LABELS = {skip_labels_json};</script>\n"
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
