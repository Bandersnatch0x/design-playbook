"""UI review regressions for the preview-only visual editor."""
from pathlib import Path
import re

import pytest

PREVIEW = Path(__file__).resolve().parents[2] / "mcp" / "preview"
CSS = (PREVIEW / "control.css").read_text(encoding="utf-8")
JS = (PREVIEW / "control.react.js").read_text(encoding="utf-8")
HTML = (PREVIEW / "control.html").read_text(encoding="utf-8")


def rule(selector):
    match = re.search(re.escape(selector) + r"\s*\{([^}]+)\}", CSS)
    assert match, selector
    return match.group(1)


def test_pending_tab_uses_batch_count_and_accent():
    assert 'classList.toggle("is-pending", pending.length > 0)' in JS
    assert 'textContent = String(pending.length)' in JS
    style = rule(".dpb-rail-tab.is-pending .dpb-filter-n")
    assert "color: var(--dpb-accent)" in style
    assert "font-weight: 700" in style


def test_webmcp_badge_activates_success_style():
    assert 'className: "dpb-react-badge" + (webmcp ? " is-on" : "")' in JS
    assert "color: var(--dpb-success)" in rule(".dpb-react-badge.is-on")


@pytest.mark.parametrize("action", ["undo", "redo"])
def test_history_buttons_have_names_and_keyboard_focus(action):
    assert f'"aria-label": t("visual_{action}")' in JS
    assert "outline: 2px solid var(--dpb-ring-accent)" in rule(
        ".dpb-react-actions button:focus-visible")


def test_computed_fields_clip_long_values_and_use_readable_labels():
    assert "font-size: 11px" in rule(".dpb-react-field")
    style = rule(".dpb-react-field input")
    assert "overflow: hidden" in style
    assert "text-overflow: ellipsis" in style


def test_popover_scrolls_within_viewport():
    style = rule(".dpb-anno-popover")
    assert "max-height: calc(100vh - 24px)" in style
    assert "overflow-y: auto" in style


def test_stale_diagnostic_has_distinct_color():
    assert '"data-stale": stale' in JS
    assert "color: var(--dpb-danger)" in rule(
        '.dpb-react-diagnostic[data-stale="true"]')


@pytest.mark.parametrize("tab", ["visual", "annotations", "spec"])
def test_tabpanels_are_labelled_by_their_tab(tab):
    panel = re.search(r'<div[^>]*id="dpb-' + tab + r'-view"[^>]*>', HTML)
    assert panel
    assert f'aria-labelledby="dpb-tab-{tab}"' in panel.group()


@pytest.mark.parametrize("webmcp", [False, True])
def test_rendered_editor_state_changes(tmp_path, webmcp):
    from playwright.sync_api import expect, sync_playwright
    from tests.preview.test_visual_edit_acceptance import PROTOTYPE, review_session
    from preview_e2e_helpers import dismiss_onboarding

    control = review_session._build_control(1, "UI regression", ["Confirm"])
    document = review_session._build_parent_page(PROTOTYPE, control)
    path = tmp_path / "preview.html"
    path.write_text(document, encoding="utf-8")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.set_default_timeout(5000)
            if webmcp:
                page.add_init_script("""document.modelContext = {
                    registerTool() {}, unregisterTool() {}
                };""")
            page.goto(path.as_uri())
            dismiss_onboarding(page)
            badge = page.locator(".dpb-react-badge")
            expect(badge).to_have_class("dpb-react-badge" + (" is-on" if webmcp else ""))
            tab = page.locator("#dpb-tab-visual")
            count = page.locator("#dpb-visual-count")
            expect(count).to_have_text("0")
            expect(tab).not_to_have_class(re.compile(r"\bis-pending\b"))
            proto = page.frame_locator("iframe.dpb-proto-frame")
            proto.locator("#panel-title").evaluate("el => el.click()")
            page.keyboard.press("Escape")
            tab.click()
            field = page.locator('.dpb-react-field[data-property="background-color"] input')
            expect(field).to_be_enabled()
            field.fill("rgb(9, 9, 9)")
            expect(count).to_have_text("1")
            expect(tab).to_have_class(re.compile(r"\bis-pending\b"))
            expect(page.locator(".dpb-react-pending-count")).to_contain_text("1")
            actions = page.locator(".dpb-react-actions button")
            for button in actions.all():
                assert button.get_attribute("aria-label") == button.inner_text()
            page.keyboard.press("Tab")
            actions.first.focus()
            assert actions.first.evaluate("el => getComputedStyle(el).outlineStyle") == "solid"
            actions.first.click()
            expect(count).to_have_text("0")
            expect(tab).not_to_have_class(re.compile(r"\bis-pending\b"))
            expect(page.locator(".dpb-react-pending-count")).to_contain_text("0")
            actions.nth(1).click()
            expect(count).to_have_text("1")
            expect(tab).to_have_class(re.compile(r"\bis-pending\b"))
            for name in ("visual", "annotations", "spec"):
                expect(page.locator(f"#dpb-{name}-view")).to_have_attribute(
                    "aria-labelledby", f"dpb-tab-{name}")
            # A reloaded frame makes existing drafts stale, never source-applied.
            page.locator("iframe.dpb-proto-frame").evaluate(
                "el => el.dispatchEvent(new Event('load'))")
            diagnostic = page.locator(".dpb-react-diagnostic")
            expect(diagnostic).to_have_attribute("data-stale", "true")
            assert diagnostic.evaluate("""el => {
                const probe = document.createElement('span');
                probe.style.color = 'var(--dpb-danger)'; el.append(probe);
                const matches = getComputedStyle(el).color === getComputedStyle(probe).color;
                probe.remove(); return matches;
            }""")
        finally:
            browser.close()
