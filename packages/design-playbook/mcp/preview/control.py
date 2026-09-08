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

    def label_key(opt: str) -> str | None:
        """Render known confirm/revise labels in the ACTIVE locale.

        The submitted value stays the raw option (CONFIRM/REVISE union sets
        still classify it); only the visible label is localized, so options
        a caller copied from another locale's docs cannot mix languages into
        an otherwise locale-consistent control bar.
        """
        if opt in CONFIRM_LABELS or opt.casefold() in confirm_cf:
            return "confirm"
        if opt in REVISE_LABELS or opt.casefold() in revise_cf:
            return "revise"
        return None

    def display_label(opt: str) -> str:
        key = label_key(opt)
        return t(key) if key else opt

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
        key = label_key(opt)
        desc_attr = (
            f' title="{desc}" aria-description="{desc}"'
            f' data-i18n-title="{key}_desc" data-i18n-aria-description="{key}_desc"'
        ) if desc else ""
        label_attr = f' data-i18n="{key}"' if key else ""
        bit = (
            f'<button type="submit" name="choice" value="{safe_val}" class="{cls}"'
            f"{desc_attr}{label_attr}>{safe_label}</button>"
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
    from design_playbook.mcp.preview.i18n import EN, ZH, _STRINGS, lang
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

    i18n_json = _js_safe(_STRINGS[lang()])
    # Dual-locale dictionary for the live L toggle (v9): both tables ship so
    # the client can swap languages without a server round-trip.
    dual_json = _js_safe(
        {k: {"zh": _STRINGS[ZH][k], "en": _STRINGS[EN][k]}
         for k in _STRINGS[ZH]}
    )
    html_tpl, css_tpl, js_tpl, _review_tpl = _load_resources()
    js_formatted = js_tpl
    localized_copy = {f"t_{key}": html_lib.escape(t(key), quote=True) for key in _STRINGS[ZH]}
    localized_copy["t_round"] = html_lib.escape(t("round_n", n=round_n))
    html_formatted = html_tpl.format(
        locale=lang(),
        round_n=round_n,
        **localized_copy,
        summary_safe=summary_safe,
        criteria_html=_render_criteria_cards(criteria_items),
        criteria_hidden=criteria_hidden,
        criteria_count_label=criteria_count_label,
        criteria_count=criteria_count,
        criteria_toggle_hidden=criteria_toggle_hidden,
        secondary_html=secondary_html,
        primary_val=primary_val,
        primary_label=primary_label,
        primary_i18n=f' data-i18n="{label_key(primary_opt)}"' if label_key(primary_opt) else "",
        skip_val=html_lib.escape(t("skip"), quote=True),
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
