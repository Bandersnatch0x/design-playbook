"""i18n for the preview adapter UI (ADR: CJK-first, en supported).

Locale source: env DPB_PREVIEW_LANG (or LANG), default "zh-CN". Only zh-CN and
en are provided; unknown locales fall back to zh-CN.

CONFIRM/revise labels are locale-aware: DEFAULT_OPTIONS returns the options in
the active locale, and CONFIRM_LABELS is the union across locales so the
backend still recognises a confirm regardless of UI language.
"""
from __future__ import annotations
import os

ZH = "zh-CN"
EN = "en"

_STRINGS: dict[str, dict[str, str]] = {
    ZH: {
        "region_label": "预览确认",
        "round_n": "第 {n} 轮",
        "annotate": "批注",
        "pill_open": "评审确认",
        "ready": "可确认",
        "not_ready": "写意见或批注后再确认",
        "drawer_aria": "批注与确认",
        "collapse": "收起",
        "pin_toggle": "点选批注",
        "pin_count": "已选 {n} 处",
        "pin_on": "点选中 · 再点关闭",
        "pin_off": "点选批注",
        "anchor_num_pre": "锚点 ",
        "anchor_num_post": " 的修改意见",
        "anchor_placeholder": "这条要改什么",
        "remove_num_pre": "移除锚点 ",
        "pin_count_pre": "已选 ",
        "pin_count_post": " 处",
        # JS-side dynamic anchors (split pre/post because idx is a JS value):
        "anchors_head": "选中批注",
        "anchors_empty": "尚未选中元素。点上方「点选批注」后，再点页面上的元素。",
        "field_label": "整体批注",
        "field_hint": "请写整体意见或点选元素加批注后确认；空反馈会被拦下（ADR-0008）",
        "field_placeholder": "对整页的总意见；页面元素的局部问题用「点选批注」",
        "close": "关闭",
        "terminate": "终止评审",
        "terminate_confirm": "再点一次确认终止",
        "abort_cancelled": "已取消",
        "draft": "保留批注，暂不决定",
        "locate": "定位到该元素",
        "locate_anchor": "定位到该元素",
        "remove": "移除",
        "selected_n": "已选 {n} 处",
        "anchor_note_label": "锚点批注 ({n}):",
        "no_text": "(无文字)",
        "done_title": "已记录",
        "done_body": "窗口即将自动关闭。",
        "confirm": "确认通过",
        "revise": "需要修改",
        "floor_failure_empty": "confirm with no substantive feedback: empty feedback and no anchor with a non-empty comment",
        "floor_failure_selector": "anchor missing non-empty selector and comment: selector={sel!r} comment={note!r}",
        "log_anchor_missing": "锚点 #{n} 缺 selector 或 comment",
        "self_check_passed": "FLOOR SELF-CHECK PASSED",
    },
    EN: {
        "region_label": "Preview confirm",
        "round_n": "Round {n}",
        "annotate": "Annotate",
        "pill_open": "Review & confirm",
        "ready": "Ready",
        "not_ready": "Add notes or pin to confirm",
        "drawer_aria": "Annotate & confirm",
        "collapse": "Collapse",
        "pin_toggle": "Pick to annotate",
        "pin_count": "{n} selected",
        "pin_on": "Picking · click again to close",
        "pin_off": "Pick to annotate",
        "anchor_num_pre": "Anchor ",
        "anchor_num_post": " revision note",
        "anchor_placeholder": "What to change here",
        "remove_num_pre": "Remove anchor ",
        "pin_count_pre": "",
        "pin_count_post": " selected",
        "anchors_head": "Selected annotations",
        "anchors_empty": "No element selected. Click \"Pick to annotate\" above, then click an element on the page.",
        "field_label": "Overall feedback",
        "field_hint": "Write overall notes or pick an element to annotate before confirming; empty feedback is blocked (ADR-0008)",
        "field_placeholder": "Overall notes for the page; for a specific element use \"Pick to annotate\"",
        "close": "Close",
        "terminate": "End review",
        "terminate_confirm": "Click again to end review",
        "abort_cancelled": "Cancelled",
        "draft": "Keep notes, decide later",
        "locate": "Locate this element",
        "locate_anchor": "Locate this element",
        "anchor_aria": "Revision note for anchor \"{label}\"",
        "remove": "Remove",
        "selected_n": "{n} selected",
        "anchor_note_label": "Anchor notes ({n}):",
        "no_text": "(no text)",
        "done_title": "Recorded",
        "done_body": "This window will close shortly.",
        "confirm": "Confirm",
        "revise": "Needs changes",
        "floor_failure_empty": "confirm with no substantive feedback: empty feedback and no anchor with a non-empty comment",
        "floor_failure_selector": "anchor missing non-empty selector and comment: selector={sel!r} comment={note!r}",
        "log_anchor_missing": "anchor #{n} missing selector or comment",
        "self_check_passed": "FLOOR SELF-CHECK PASSED",
    },
}


def lang() -> str:
    """Active locale (zh-CN or en). Env DPB_PREVIEW_LANG, then LANG, default zh-CN."""
    raw = os.environ.get("DPB_PREVIEW_LANG") or os.environ.get("LANG") or ZH
    low = raw.replace("_", "-").lower()
    if low.startswith("en"):
        return EN
    return ZH


def t(key: str, **kw: object) -> str:
    """Translate a key in the active locale, with {kw} interpolation."""
    table = _STRINGS[lang()]
    val = table.get(key)
    if val is None:
        return key
    if kw:
        try:
            return val.format(**kw)
        except (KeyError, IndexError):
            return val
    return val


def default_options() -> list[str]:
    """[confirm_label, revise_label] in the active locale."""
    return [t("confirm"), t("revise")]


# Union of confirm labels across ALL locales - backend must recognise a confirm
# regardless of which locale the UI rendered in.
CONFIRM_LABELS: set[str] = {
    _STRINGS[ZH]["confirm"], _STRINGS[EN]["confirm"],
    "confirm", "confirmed", "pass", "ok",
}

# Union of revise labels across ALL locales - frontend must classify a revise
# regardless of which locale the UI rendered in.
REVISE_LABELS: set[str] = {
    _STRINGS[ZH]["revise"], _STRINGS[EN]["revise"],
    "revise", "needs changes", "needs-changes",
}
