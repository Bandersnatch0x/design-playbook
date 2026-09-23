"""Browser regressions for locale changes and non-destructive keyboard review.

T-083 notes: the v10 shell replaces the blocking onboarding modal with a
non-modal coachmark (REC-03/R9) and the drawer free-note input with an
in-context popover (REC-01). The IME guard (R2) now lives on the popover
textarea; this file keeps the same lockstep patterns against the new DOM.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from tests.preview.test_browser_control import _write_control_page  # noqa: E402
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
    # REC-03: the coachmark is non-blocking; assert it is present for first
    # use, then close it so scenarios start from a quiet shell.
    expect(page.locator("#dpb-coachmark")).to_be_visible()
    yield page
    page.close()


def dismiss_intro(page):
    card = page.locator("#dpb-coachmark")
    if card.is_visible():
        page.locator("#dpb-coachmark-close").click()
    expect(card).to_be_hidden()


def open_popover(page, selector="#prototype h1"):
    """REC-01 helper: pick an element and land on the in-context popover."""
    page.click(selector)
    expect(page.locator("#dpb-anno-popover")).to_be_visible()
    return page.locator("#dpb-anno-input")


def save_anchor(page, text, selector="#prototype h1"):
    ta = open_popover(page, selector)
    ta.fill(text)
    page.keyboard.press("Enter")
    expect(page.locator("#dpb-anno-popover")).to_be_hidden()
    expect(page.locator("#dpb-anchors .dpb-anchor")).to_have_count(1)


def test_coachmark_persists_until_first_anchor_not_timed_out(page):
    # R9: the card is non-modal and never auto-hides; the canvas is operable.
    page.wait_for_timeout(2600)
    expect(page.locator("#dpb-coachmark")).to_be_visible()
    save_anchor(page, "第一处批注")
    expect(page.locator("#dpb-coachmark")).to_be_hidden()


def test_escape_dismisses_coachmark_without_submitting_skip(page):
    page.keyboard.press("Escape")
    expect(page.locator("#dpb-coachmark")).to_be_hidden()
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


def test_ime_enter_does_not_save_annotation_draft(page):
    # R2 (lockstep, was test_ime_enter on the drawer input): an IME Enter
    # commits composition inside the popover textarea, never the draft.
    dismiss_intro(page)
    ta = open_popover(page)
    ta.fill("正在输入中文")
    ta.dispatch_event("keydown", {"key": "Enter", "code": "Enter", "isComposing": True})
    expect(ta).to_have_value("正在输入中文")
    expect(page.locator("#dpb-anno-popover")).to_be_visible()
    expect(page.locator("#dpb-anchors .dpb-anchor")).to_have_count(0)


def test_text_target_suspends_single_key_shortcuts(page):
    # R2: while the popover textarea holds focus, single-character hotkeys
    # type text instead of switching tools/viewports.
    dismiss_intro(page)
    ta = open_popover(page)
    for key in ["b", "1", "v", "d", "s", "j"]:
        ta.press(key)
    expect(ta).to_have_value("b1vdsj")
    expect(page.locator("#dpb-anno-popover")).to_be_visible()
    expect(page.locator("#dpb-anchors .dpb-anchor")).to_have_count(0)


def test_space_activates_focused_button_instead_of_panning(page):
    dismiss_intro(page)
    page.locator("#dpb-feedback").fill("The layout is ready for review")
    page.locator("#dpb-btn-approve").focus()
    page.keyboard.press("Space")
    assert page.evaluate("window.submittedChoices") == ["确认通过"]


def test_enter_saves_returns_focus_and_next_click_reopens(page):
    # R4: Enter saves; focus lands on the canvas; the pick channel stays on so
    # the very next click opens a fresh bubble.
    dismiss_intro(page)
    page.evaluate("""() => {
      const proto = document.getElementById('prototype');
      const p = document.createElement('p');
      p.id = 'second-el';
      p.textContent = '第二目标';
      proto.appendChild(p);
    }""")
    save_anchor(page, "第一处")
    assert page.evaluate("document.activeElement.id") == "dpb-canvas"
    ta = open_popover(page, "#second-el")
    expect(ta).to_be_focused()
    ta.fill("第二处")
    page.keyboard.press("Enter")
    expect(page.locator("#dpb-anno-popover")).to_be_hidden()
    assert page.evaluate(
        "() => JSON.parse(document.getElementById('dpb-anchors-json').value).length"
    ) == 2


def test_escape_cancels_empty_draft_without_anchor(page):
    # REC-01 guard: an untyped draft self-destructs; no ghost anchor lands.
    dismiss_intro(page)
    open_popover(page)
    page.keyboard.press("Escape")
    expect(page.locator("#dpb-anno-popover")).to_be_hidden()
    assert page.evaluate("window.submittedChoices") == []
    assert page.evaluate(
        "() => JSON.parse(document.getElementById('dpb-anchors-json').value).length"
    ) == 0


def test_popover_flips_inside_viewport_near_right_edge(page):
    # R3 (minimal 4-quadrant flip): a wide element hugging the right side of
    # the artboard must not push the popover off-screen.
    dismiss_intro(page)
    page.evaluate("""() => {
      const proto = document.getElementById('prototype');
      const wide = document.createElement('div');
      wide.id = 'wide-el';
      wide.style.cssText = 'height:40px;background:#eee;';
      proto.appendChild(wide);
    }""")
    open_popover(page, "#wide-el")
    box = page.locator("#dpb-anno-popover").bounding_box()
    vw = page.evaluate("window.innerWidth")
    assert box is not None
    assert box["x"] + box["width"] <= vw, (box, vw)


def test_live_language_updates_chrome_accessibility_not_choice_values(page):
    dismiss_intro(page)
    page.locator("#dpb-feedback").fill("Keep user text 中文 unchanged")
    page.locator("#dpb-language-toggle").click()
    expect(page.locator("#dpb-root")).to_have_attribute("lang", "en")
    expect(page.locator("#dpb-btn-approve")).to_contain_text("Approve")
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
        ["文案", "布局", "视觉", "圈画", "框选", "定位点", "批注", "元素"],
        ["Copy", "Layout", "Visual", "Draw", "Box", "Pin", "Note", "Element"],
        ["文案", "布局", "视觉", "圈画", "框选", "定位点", "批注", "元素"],
    ]:
        expect(page.locator(".dpb-anchor-kind")).to_have_text(labels)
        assert json.loads(page.locator("#dpb-anchors-json").input_value()) == anchors
        page.locator("#dpb-language-toggle").click()


def test_empty_confirmation_announces_localized_feedback_hint(page):
    dismiss_intro(page)
    hint = page.locator("#dpb-feedback-hint")
    expect(hint).to_be_hidden()
    for locale in ["zh", "en"]:
        message = page.evaluate("locale => window.DPB_I18N_DUAL.field_hint[locale]", locale)
        page.locator("#dpb-btn-approve").click()
        expect(hint).to_be_visible()
        expect(hint).to_have_text(message)
        expect(page.locator("#dpb-announce")).to_have_text(message)
        page.locator("#dpb-language-toggle").click()


def test_skip_stays_a_visible_secondary_button(page):
    # R8: skip is a visible secondary action in the header; only abort (with
    # its confirm popover) is a two-step tucked-away disposition.
    dismiss_intro(page)
    skip = page.locator("#dpb-btn-skip")
    expect(skip).to_be_visible()
    skip.click()
    assert page.evaluate("window.submittedChoices") == ["跳过"]


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
    assert page.locator("#dpb-btn-approve span#dpb-approve-label").evaluate("el => { const r = document.createRange(); r.selectNodeContents(el); return r.getClientRects().length; }") == 1


def test_compact_workspace_keeps_canvas_usable_and_rail_reachable(page, tmp_path):
    # REC-02: one rail owns criteria AND annotations, so the canvas keeps its
    # width even on compact screens; the rail stays collapsible.
    page.set_viewport_size({"width": 768, "height": 900})
    page.goto(_write_control_page(tmp_path, [{"id": "A1", "title": "Real criterion"}]))
    dismiss_intro(page)
    assert page.locator("#dpb-canvas").bounding_box()["width"] >= 400
    expect(page.locator("#dpb-drawer-toggle")).to_have_attribute("aria-expanded", "true")
    page.locator("#dpb-drawer-toggle").click()
    expect(page.locator("#dpb-drawer-toggle")).to_have_attribute("aria-expanded", "false")
    assert page.locator("#dpb-inspector").evaluate("el => el.inert")
    page.locator("#dpb-drawer-toggle").click()
    expect(page.locator("#dpb-drawer-toggle")).to_have_attribute("aria-expanded", "true")
    # the spec tab is reachable inside the same rail (S hotkey too)
    page.click("#dpb-tab-spec")
    expect(page.locator("#dpb-spec-view")).to_be_visible()
    expect(page.locator("#dpb-annotations-view")).to_be_hidden()
    page.click("#dpb-tab-annotations")
    expect(page.locator("#dpb-annotations-view")).to_be_visible()
