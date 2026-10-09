"""Source-text contracts for the preview control shell.

These assert on the shipped ``control.css`` text and on the control HTML the
server builds. Neither has a runtime equivalent, so the checks need no browser
and run in the no-chromium CI job instead of the browser-marked regression
module.
"""
import re
from pathlib import Path

PREVIEW = Path(__file__).resolve().parents[2] / "mcp" / "preview"
CSS = (PREVIEW / "control.css").read_text(encoding="utf-8")


def rule(selector: str) -> str:
    match = re.search(re.escape(selector) + r"\s*\{([^}]+)\}", CSS)
    assert match, selector
    return match.group(1)


# The pending class, the count and the badge class are asserted at runtime in
# test_visual_ui_regressions.test_rendered_editor_state_changes; grepping the
# shipped JS for the lines that set them only proved the text still existed.
# These keep the rule half, which has no runtime equivalent.
def test_pending_tab_uses_batch_count_and_accent() -> None:
    style = rule(".dpb-rail-tab.is-pending .dpb-filter-n")
    assert "color: var(--dpb-accent)" in style
    assert "font-weight: 700" in style


def test_webmcp_badge_activates_success_style() -> None:
    assert "color: var(--dpb-success)" in rule(".dpb-react-badge.is-on")


def test_computed_fields_clip_long_values_and_use_readable_labels() -> None:
    assert "font-size: 11px" in rule(".dpb-react-field")
    style = rule(".dpb-react-field input")
    assert "overflow: hidden" in style
    assert "text-overflow: ellipsis" in style


def test_popover_scrolls_within_viewport() -> None:
    style = rule(".dpb-anno-popover")
    assert "max-height: calc(100vh - 24px)" in style
    assert "overflow-y: auto" in style


def test_criteria_chip_does_not_repeat_the_tab_label() -> None:
    """The count chip sits beside the "验收准判" label, so it carries numbers only."""
    from design_playbook.mcp.preview import i18n
    from design_playbook.mcp.preview.control import _build_control

    for locale in (i18n.ZH, i18n.EN):
        assert i18n._STRINGS[locale]["criteria_count"] == "{checked}/{total}"

    html = _build_control(
        1, "criteria chip", ["Confirm"],
        criteria=[{"id": "AC-1", "title": "Title", "then": "Visible"}],
    )
    short = i18n.t("criteria_title_short")
    assert short in html
    assert "0/1" in html
    # "<short> <short> 0/1" is the defect this pins.
    assert f"{short}</span> <span class=\"dpb-filter-n\" id=\"dpb-criteria-count\">{short}" not in html


def test_next_step_copy_names_the_decision_not_the_feedback_only() -> None:
    """Visual edits ride along with the round decision, so the copy must say so.

    Pending visual edits alone do not satisfy the ADR-0008 floor, so the muted
    approve label still asks for a note or an annotation - and stays short,
    because the 768px header test owns that budget. The ride-along fact and the
    submit shortcut ride in the always-visible tooltip and the rendered
    visual-panel help instead.
    """
    from design_playbook.mcp.preview import i18n

    zh, en = i18n._STRINGS[i18n.ZH], i18n._STRINGS[i18n.EN]
    # The visual-panel help is rendered (`dpb-react-help`) and names the action.
    for table in (zh, en):
        assert "Ctrl" in table["visual_help"]
        assert "⌘" in table["visual_help"]
    # The approve tooltip is always reachable and states that pending edits
    # travel along with the decision, in both locales.
    assert "视觉修改" in zh["confirm_desc"]
    assert "一并提交" in zh["confirm_desc"]
    assert "visual edit" in en["confirm_desc"].lower()
    assert "ride along" in en["confirm_desc"].lower()
