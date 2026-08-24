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
        "drawer_title": "批注与确认",
        "drawer_empty_title": "还没有批注",
        "drawer_empty_desc": "开启「点选批注」后点击页面元素添加锚点，或直接在下方写整体修改意见",
        "collapse": "收起",
        "pin_toggle": "点选批注",
        "pin_toggle_desc": "开启后点击页面元素添加批注锚点；再点一次或按 Esc 退出",
        "duplicate_anchor": "该元素已是批注 {n}，未重复添加",
        "onboard_title": "标注速览（仅出现一次）",
        "onboard_pick": "点「批注」→「点选批注」，再点击页面元素添加锚点",
        "onboard_write": "为每个锚点填写修改意见，或写整体批注",
        "onboard_submit": "提交确认",
        "onboard_undo": "撤销批注（Shift 重做）",
        "onboard_close": "知道了",
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
        "field_hint": "请写整体意见或点选元素加批注后确认；空反馈会被拦下",
        "field_placeholder": "对整页的总意见；页面元素的局部问题用「点选批注」",
        "close": "关闭",
        "cancel": "取消",
        "terminate": "终止评审",
        "terminate_confirm": "确认终止本次预览？",
        "terminate_confirm_go": "确认终止",
        "terminate_desc": "终止整次预览会话（不是通过/修改）；需在弹出层再次确认",
        "abort_cancelled": "已取消终止",
        "abort_popover_aria": "确认终止预览",
        "quick_feedback_placeholder": "一句话反馈（宽屏）",
        "ready_hint": "点击聚焦反馈区",
        "draft": "保留批注，暂不决定",
        "draft_desc": "关闭抽屉并保留批注，不提交本轮决定",
        "locate": "定位到该元素",
        "locate_anchor": "定位到该元素",
        "remove": "移除",
        "selected_n": "已选 {n} 处",
        "anchor_note_label": "锚点批注 ({n}):",
        "no_text": "(无文字)",
        "done_title": "已记录",
        "done_body": "窗口即将自动关闭。",
        "confirm": "确认通过",
        "skip": "跳过",
        "skip_desc": "无问题跳过，直接通过（不需要修改）",
        "zoom_fit": "自适应",
        "draw_toggle": "圈画标注",
        "draw_on": "圈画中 · 再点关闭",
        "draw_label": "圈画 {n}",
        "app_title": "预览确认",
        "mode_preview": "预览",
        "mode_annotate": "批注",
        "vp_desktop": "桌面视图 [1024px]",
        "vp_tablet": "平板视图 [768px]",
        "vp_mobile": "手机视图 [375px]",
        "filter_all": "全部",
        "filter_pending": "待处理",
        "filter_resolved": "已解决",
        "mark_resolved": "标记为已解决",
        "reopen": "重新打开",
        "tag_copy": "文案 Copy",
        "tag_layout": "布局 Layout",
        "tag_visual": "视觉 Visual",
        "comment_placeholder": "输入批注或改进建议（Enter 发送）…",
        "comment_send": "发送批注",
        "enter_hint": "Enter 发送",
        "status_ready": "已定位 {n} 处批注 · 随时可确认通过",
        "status_not_ready": "写意见或添加批注后再确认",
        "quick_approve": "快捷确认",
        "shortcuts_title": "快捷键指南",
        "group_global": "全局决策流转",
        "group_tools": "画布与交互工具",
        "lang_toggle": "切换中英双语",
        "roam_prev": "上一个批注",
        "roam_next": "下一个批注",
        "roam_label": "上一处/下一处批注",
        "tool_select": "选择：点击画布添加 Pin",
        "tool_draw": "按住拖拽圈画涂鸦",
        "tool_hand": "抓手平移画布（Space 按住拖拽）",
        "undo_label": "撤销标注",
        "zoom_in_t": "放大",
        "zoom_out_t": "缩小",
        "drawer_toggle": "收起/展开批注抽屉",
        "shortcuts_open": "查看完整快捷键指南",
        "got_it": "知道了",
        "toast_mode_preview": "进入纯净预览模式",
        "toast_mode_annotate": "进入批注评审模式",
        "toast_pin_added": "已添加 Pin #{n}",
        "toast_loop_done": "圈画完成！请在右侧输入修改意见",
        "toast_note_added": "已添加批注 #{n}",
        "toast_resolved": "批注 #{n} 已标记为已解决",
        "toast_reopened": "批注 #{n} 已重新打开",
        "toast_drawer_open": "展开批注抽屉",
        "toast_drawer_closed": "已收起批注抽屉（点击右侧把手或按 [ 展开）",
        "toast_lang": "已切换至中文模式",
        "toast_undo": "已撤销上一笔圈画",
        "toast_focus": "聚焦批注 #{n}",
        "toast_vp": "已切换视口宽度",
        "confirm_desc": "确认本轮通过并进入实现（Fill）；需有批注或整体意见",
        "revise": "需要修改",
        "revise_desc": "提交修改意见，进入下一轮原型",
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
        "drawer_title": "Annotations & confirm",
        "drawer_empty_title": "No annotations yet",
        "drawer_empty_desc": "Turn on pin mode and click an element to anchor a note, or write overall feedback below",
        "collapse": "Collapse",
        "pin_toggle": "Pick to annotate",
        "pin_toggle_desc": "When on, click page elements to add annotation anchors; click again or press Esc to exit",
        "duplicate_anchor": "Already annotated as #{n}; not added again",
        "onboard_title": "Annotation quick tour (shown once)",
        "onboard_pick": "Click \"Annotate\" then \"Pick to annotate\", and click a page element to add an anchor",
        "onboard_write": "Write a note for each anchor, or add overall feedback",
        "onboard_submit": "Submit confirm",
        "onboard_undo": "Undo annotation (Shift to redo)",
        "onboard_close": "Got it",
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
        "field_hint": "Write overall notes or pick an element to annotate before confirming; empty feedback is blocked",
        "field_placeholder": "Overall notes for the page; for a specific element use \"Pick to annotate\"",
        "close": "Close",
        "cancel": "Cancel",
        "terminate": "Abort preview",
        "terminate_confirm": "Abort this preview session?",
        "terminate_confirm_go": "Confirm abort",
        "terminate_desc": "Stops the whole preview session (not pass/fail); confirm again in the popover",
        "abort_cancelled": "Abort cancelled",
        "abort_popover_aria": "Confirm abort preview",
        "quick_feedback_placeholder": "Quick note (wide layout)",
        "ready_hint": "Click to focus feedback",
        "draft": "Keep notes, decide later",
        "draft_desc": "Close drawer and keep notes; do not submit a decision yet",
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
        "skip": "Skip",
        "skip_desc": "Pass without changes (no issues)",
        "zoom_fit": "Fit",
        "draw_toggle": "Draw",
        "draw_on": "Drawing · click to stop",
        "draw_label": "Draw {n}",
        "app_title": "Preview & Confirm",
        "mode_preview": "Preview",
        "mode_annotate": "Annotate",
        "vp_desktop": "Desktop [1024px]",
        "vp_tablet": "Tablet [768px]",
        "vp_mobile": "Mobile [375px]",
        "filter_all": "All",
        "filter_pending": "Pending",
        "filter_resolved": "Resolved",
        "mark_resolved": "Mark as Resolved",
        "reopen": "Reopen",
        "tag_copy": "Copy",
        "tag_layout": "Layout",
        "tag_visual": "Visual",
        "comment_placeholder": "Add note or feedback (Enter to send)…",
        "comment_send": "Send note",
        "enter_hint": "Enter to send",
        "status_ready": "{n} annotations · Ready to approve",
        "status_not_ready": "Add notes or pin to confirm",
        "quick_approve": "Quick Approve",
        "shortcuts_title": "Keyboard Shortcuts",
        "group_global": "Global Actions",
        "group_tools": "Canvas & Tools",
        "lang_toggle": "Toggle ZH/EN",
        "roam_prev": "Previous annotation",
        "roam_next": "Next annotation",
        "roam_label": "Next / Prev Annotation",
        "tool_select": "Select: click canvas to drop a pin",
        "tool_draw": "Draw: drag to loop",
        "tool_hand": "Hand: pan canvas (Space+drag)",
        "undo_label": "Undo annotation",
        "zoom_in_t": "Zoom in",
        "zoom_out_t": "Zoom out",
        "drawer_toggle": "Toggle annotation drawer",
        "shortcuts_open": "Shortcut guide",
        "got_it": "Got it",
        "toast_mode_preview": "Clean preview mode",
        "toast_mode_annotate": "Annotation mode",
        "toast_pin_added": "Dropped Pin #{n}",
        "toast_loop_done": "Loop drawn! Type note in the drawer",
        "toast_note_added": "Added note #{n}",
        "toast_resolved": "Note #{n} marked as resolved",
        "toast_reopened": "Note #{n} reopened",
        "toast_drawer_open": "Drawer opened",
        "toast_drawer_closed": "Drawer collapsed (click the right tab or press [ )",
        "toast_lang": "Switched to English",
        "toast_undo": "Undone last drawing",
        "toast_focus": "Focused note #{n}",
        "toast_vp": "Viewport width switched",
        "confirm_desc": "Approve this round and proceed to Fill; needs notes or annotations",
        "revise": "Needs changes",
        "revise_desc": "Submit revision notes and open the next prototype round",
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


# Union of skip labels across ALL locales - a skip is an explicit
# non-confirm disposition (ADR-0008): it never enters CONFIRM_LABELS and
# can never satisfy the confirm floor or G5.
SKIP_LABELS: set[str] = {
    _STRINGS[ZH]["skip"], _STRINGS[EN]["skip"],
    "skip",
}

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
