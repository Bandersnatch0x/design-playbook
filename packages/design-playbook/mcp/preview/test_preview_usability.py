"""Browser regressions for locale changes and non-destructive keyboard review."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.mcp.preview.test_browser_control import _write_control_page  # noqa: E402
from design_playbook.mcp.preview.control import _build_control  # noqa: E402
from design_playbook.mcp.preview.review_session import _build_parent_page  # noqa: E402


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(browser, tmp_path, monkeypatch):
    monkeypatch.setenv("DPB_PREVIEW_LANG", "zh-CN")
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.set_default_timeout(3000)
    page.goto(_write_control_page(tmp_path, []))
    page.evaluate("""() => {
      window.submittedChoices = [];
      document.getElementById('dpb-decide-form').addEventListener('submit', e => {
        e.preventDefault();
        window.submittedChoices.push(e.submitter && e.submitter.value);
      });
    }""")
    expect(page.locator("#dpb-onboarding-modal")).to_be_visible()
    yield page
    page.close()


def dismiss_intro(page):
    page.locator("#dpb-onboarding-close").click()


def test_escape_dismisses_onboarding_without_submitting_skip(page):
    page.keyboard.press("Escape")
    expect(page.locator("#dpb-onboarding-modal")).to_be_hidden()
    assert page.evaluate("window.submittedChoices") == []


def test_help_traps_focus_blocks_submit_and_restores_trigger(page):
    dismiss_intro(page)
    page.locator("#dpb-feedback").fill("The layout is ready for review")
    trigger = page.locator("#dpb-shortcuts-btn")
    trigger.click()
    dialog = page.locator("#dpb-shortcut-modal")
    expect(dialog).to_be_visible()
    page.keyboard.press("Control+Enter")
    assert page.evaluate("window.submittedChoices") == []
    for _ in range(5):
        page.keyboard.press("Tab")
        assert dialog.evaluate("el => el.contains(document.activeElement)")
    page.keyboard.press("Escape")
    expect(dialog).to_be_hidden()
    expect(trigger).to_be_focused()


def test_plain_escape_cancels_only_shift_escape_explicitly_skips(page):
    dismiss_intro(page)
    page.keyboard.press("Escape")
    assert page.evaluate("window.submittedChoices") == []
    page.keyboard.press("Shift+Escape")
    assert page.evaluate("window.submittedChoices") == ["跳过"]


def test_abort_defaults_to_cancel_and_returns_focus(page):
    dismiss_intro(page)
    page.locator("#dpb-abort").click()
    expect(page.locator("#dpb-abort-cancel")).to_be_focused()
    page.keyboard.press("Tab")
    expect(page.locator("#dpb-abort-confirm")).to_be_focused()
    page.keyboard.press("Tab")
    expect(page.locator("#dpb-abort-cancel")).to_be_focused()
    page.locator("#dpb-abort-cancel").click()
    expect(page.locator("#dpb-abort")).to_be_focused()
    assert page.evaluate("window.submittedChoices") == []


def test_ime_enter_does_not_create_annotation(page):
    dismiss_intro(page)
    field = page.locator("#dpb-comment-input")
    field.fill("正在输入中文")
    field.dispatch_event("keydown", {"key": "Enter", "code": "Enter", "isComposing": True})
    expect(field).to_have_value("正在输入中文")
    expect(page.locator("#dpb-anchors .dpb-anchor")).to_have_count(0)


def test_space_activates_focused_button_instead_of_panning(page):
    dismiss_intro(page)
    page.locator("#dpb-feedback").fill("The layout is ready for review")
    page.locator("#dpb-btn-approve").focus()
    page.keyboard.press("Space")
    assert page.evaluate("window.submittedChoices") == ["确认通过"]


def test_live_language_updates_chrome_accessibility_not_choice_values(page):
    dismiss_intro(page)
    page.locator("#dpb-feedback").fill("Keep user text 中文 unchanged")
    page.locator("#dpb-language-toggle").click()
    expect(page.locator("#dpb-root")).to_have_attribute("lang", "en")
    expect(page.locator("#dpb-btn-approve")).to_contain_text("Confirm")
    expect(page.locator("#dpb-theme-toggle")).to_have_attribute("aria-label", "Toggle light/dark theme")
    assert page.locator("#dpb-btn-skip").get_attribute("title").isascii()
    assert page.locator("#dpb-pin-toggle").get_attribute("title").isascii()
    assert page.locator("#dpb-btn-approve").get_attribute("value") == "确认通过"
    expect(page.locator("#dpb-feedback")).to_have_value("Keep user text 中文 unchanged")
    assert "without confirming approval" in page.locator("#dpb-btn-skip").get_attribute("title")
    assert "[P]" in page.locator("#dpb-pin-toggle").get_attribute("title")
    page.locator("#dpb-shortcuts-btn").click()
    assert "滚轮" not in page.locator("#dpb-shortcut-modal").inner_text()
    page.keyboard.press("Escape")
    page.keyboard.press("l")
    expect(page.locator("#dpb-root")).to_have_attribute("lang", "zh-CN")
    expect(page.locator("#dpb-theme-toggle")).to_have_attribute("aria-label", "切换明暗主题")
    expect(page.locator("#dpb-feedback")).to_have_value("Keep user text 中文 unchanged")


def test_annotation_kinds_localize_without_changing_payload(page):
    anchors = [
        {"selector": f"@note-{tag}", "label": "Author label", "comment": "用户意见", "tag": tag}
        for tag in ["copy", "layout", "visual", "draw", "box", "pin"]
    ] + [
        {"selector": "@note-plain", "label": "Author label", "comment": "用户意见", "tag": ""},
        {"selector": "#prototype", "label": "Author label", "comment": "用户意见", "tag": ""},
    ]
    page.evaluate("anchors => localStorage.setItem(window.DPB_DRAFT_KEY, JSON.stringify({anchors}))", anchors)
    page.reload()
    dismiss_intro(page)
    for labels in [
        ["文案 Copy", "布局 Layout", "视觉 Visual", "圈画", "框选", "定位点", "批注", "元素"],
        ["Copy", "Layout", "Visual", "Draw", "Box", "Pin", "Note", "Element"],
        ["文案 Copy", "布局 Layout", "视觉 Visual", "圈画", "框选", "定位点", "批注", "元素"],
    ]:
        expect(page.locator(".dpb-anchor-kind")).to_have_text(labels)
        assert json.loads(page.locator("#dpb-anchors-json").input_value()) == anchors
        page.locator("#dpb-language-toggle").click()


@pytest.mark.parametrize("selector", ["#dpb-btn-approve", "#dpb-status-approve"])
def test_empty_confirmation_announces_localized_feedback_hint(page, selector):
    dismiss_intro(page)
    hint = page.locator("#dpb-feedback-hint")
    expect(hint).to_be_hidden()
    for locale in ["zh", "en"]:
        message = page.evaluate("locale => window.DPB_I18N_DUAL.field_hint[locale]", locale)
        page.locator(selector).click()
        expect(hint).to_be_visible()
        expect(hint).to_have_text(message)
        expect(page.locator("#dpb-announce")).to_have_text(message)
        page.locator("#dpb-language-toggle").click()


def test_language_switch_does_not_translate_author_attributes_in_inline_prototype(page):
    dismiss_intro(page)
    page.locator("#prototype").evaluate(
        'el => { el.innerHTML = `<span data-i18n="confirm">Author wording</span><input data-i18n-placeholder="confirm" placeholder="Author placeholder">`; }'
    )
    page.evaluate("""() => {
      const prototype = document.getElementById('prototype');
      window.prototypeTranslationVisits = 0;
      const queryLabels = Element.prototype.querySelectorAll;
      Element.prototype.querySelectorAll = function (selector) {
        const matches = queryLabels.call(this, selector);
        if (selector.includes('data-i18n')) {
          window.prototypeTranslationVisits += Array.from(matches).filter(node => prototype.contains(node)).length;
        }
        return matches;
      };
      const matchesLabel = Element.prototype.matches;
      Element.prototype.matches = function (selector) {
        if (selector.includes('data-i18n') && prototype.contains(this)) window.prototypeTranslationVisits++;
        return matchesLabel.call(this, selector);
      };
    }""")
    page.locator("#dpb-language-toggle").click()
    assert page.evaluate("window.prototypeTranslationVisits") == 0
    expect(page.locator("#prototype span")).to_have_text("Author wording")
    expect(page.locator("#prototype input")).to_have_attribute("placeholder", "Author placeholder")


def test_language_switch_updates_owned_document_and_frame_not_author_content(page, tmp_path):
    prototype = '<html lang="en"><head><title>Author title</title></head><body>Author content</body></html>'
    target = tmp_path / "parent.html"
    target.write_text(_build_parent_page(prototype, _build_control(1, "Review", ["确认通过", "需要修改"])), encoding="utf-8")
    page.goto(target.as_uri())
    dismiss_intro(page)
    page.locator("#dpb-language-toggle").click()
    expect(page).to_have_title("Preview & Confirm")
    expect(page.locator("html")).to_have_attribute("lang", "en")
    expect(page.locator("iframe.dpb-proto-frame")).to_have_attribute("title", "Prototype under review")
    expect(page.frame_locator("iframe.dpb-proto-frame").locator("html")).to_have_attribute("lang", "en")
    expect(page.frame_locator("iframe.dpb-proto-frame").locator("body")).to_contain_text("Author content")


@pytest.mark.parametrize("width", [1280, 1024, 768])
def test_english_header_actions_remain_inside_window(page, tmp_path, width):
    page.goto(_write_control_page(tmp_path, [{"id": "A1", "title": "A real acceptance criterion"}]))
    dismiss_intro(page)
    page.locator("#dpb-language-toggle").click()
    page.set_viewport_size({"width": width, "height": 800})
    for selector in ["#dpb-language-toggle", "#dpb-btn-skip", "#dpb-btn-approve", "#dpb-shortcuts-btn"]:
        bounds = page.locator(selector).bounding_box()
        assert bounds is not None
        assert 0 <= bounds["x"] and bounds["x"] + bounds["width"] <= width, (selector, bounds)
    overlap = page.evaluate("""() => {
      const groups = ['.dpb-header-left', '.dpb-header-center', '.dpb-header-right'].map(s => document.querySelector(s).getBoundingClientRect());
      return groups.some((a, i) => groups.slice(i + 1).some(b =>
        Math.min(a.right,b.right) - Math.max(a.left,b.left) > 1 &&
        Math.min(a.bottom,b.bottom) - Math.max(a.top,b.top) > 1));
    }""")
    assert not overlap
    assert page.locator("#dpb-btn-approve").evaluate("el => getComputedStyle(el).backgroundColor") != "rgba(0, 0, 0, 0)"
    toolbar = page.locator("#dpb-toolbar").bounding_box()
    header = page.locator("#dpb-header").bounding_box()
    assert toolbar["y"] >= header["y"] + header["height"]
    assert page.locator("#dpb-status-approve span").evaluate("el => { const r = document.createRange(); r.selectNodeContents(el); return r.getClientRects().length; }") == 1


def test_compact_workspace_keeps_canvas_usable_and_panels_reachable(page, tmp_path):
    page.set_viewport_size({"width": 768, "height": 900})
    page.goto(_write_control_page(tmp_path, [{"id": "A1", "title": "Real criterion"}]))
    dismiss_intro(page)
    assert page.locator("#dpb-canvas").bounding_box()["width"] >= 400
    expect(page.locator("#dpb-criteria-toggle")).to_have_attribute("aria-expanded", "false")
    page.locator("#dpb-criteria-toggle").click()
    expect(page.locator("#dpb-criteria-toggle")).to_have_attribute("aria-expanded", "true")
    expect(page.locator("#dpb-drawer-toggle")).to_have_attribute("aria-expanded", "false")
    assert page.locator("#dpb-inspector").evaluate("el => el.inert")
    page.locator("#dpb-drawer-toggle").click()
    expect(page.locator("#dpb-drawer-toggle")).to_have_attribute("aria-expanded", "true")
    expect(page.locator("#dpb-criteria-toggle")).to_have_attribute("aria-expanded", "false")
    assert page.locator("#dpb-spec-panel").evaluate("el => el.inert")
