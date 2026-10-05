"""UI review regressions for the preview-only visual editor."""
from pathlib import Path
import re

import pytest

PREVIEW = Path(__file__).resolve().parents[2] / "mcp" / "preview"
CSS = (PREVIEW / "control.css").read_text(encoding="utf-8")
JS = (PREVIEW / "control.react.js").read_text(encoding="utf-8")
HTML = (PREVIEW / "control.html").read_text(encoding="utf-8")


@pytest.fixture
def editor_page(tmp_path):
    from playwright.sync_api import sync_playwright
    from tests.preview.test_visual_edit_acceptance import PROTOTYPE, review_session
    from preview_e2e_helpers import dismiss_onboarding

    control = review_session._build_control(1, "Round 2 regression", ["Confirm"])
    path = tmp_path / "preview.html"
    path.write_text(review_session._build_parent_page(PROTOTYPE, control), encoding="utf-8")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.set_default_timeout(5000)
            page.goto(path.as_uri())
            dismiss_onboarding(page)
            yield page
        finally:
            browser.close()


@pytest.mark.parametrize("modifier", ["Control", "Meta"])
def test_visual_history_shortcuts_replay_only_in_active_editor(editor_page, modifier):
    from playwright.sync_api import expect

    page = editor_page
    proto = page.frame_locator("iframe.dpb-proto-frame")
    target = proto.locator("#panel-title")
    original = target.evaluate("el => getComputedStyle(el).backgroundColor")
    target.evaluate("el => el.click()")
    page.keyboard.press("Escape")
    page.locator("#dpb-tab-visual").click()
    field = page.locator('.dpb-react-field[data-property="background-color"] input')
    expect(field).to_be_enabled()
    field.fill("rgb(9, 9, 9)")
    count = page.locator("#dpb-visual-count")
    expect(count).to_have_text("1")

    # Unmodified keys and shortcuts on another tab must not replay the batch.
    page.locator("#dpb-tab-annotations").click()
    page.keyboard.press(f"{modifier}+z")
    expect(count).to_have_text("1")
    expect(target).to_have_css("background-color", "rgb(9, 9, 9)")
    page.locator("#dpb-tab-visual").click()
    page.keyboard.press("z")
    expect(count).to_have_text("1")

    # Exercise repeated replays to detect stale state captured at mount time.
    for redo in (f"{modifier}+Shift+z", f"{modifier}+y"):
        field.focus()
        page.keyboard.press(f"{modifier}+z")
        expect(count).to_have_text("0")
        expect(target).to_have_css("background-color", original)
        page.keyboard.press(redo)
        expect(count).to_have_text("1")
        expect(target).to_have_css("background-color", "rgb(9, 9, 9)")

    page.locator("iframe.dpb-proto-frame").evaluate(
        "el => el.dispatchEvent(new Event('load'))")
    expect(page.locator(".dpb-react-diagnostic")).to_have_attribute("data-stale", "true")
    page.keyboard.press(f"{modifier}+z")
    expect(count).to_have_text("1")
    expect(target).to_have_css("background-color", "rgb(9, 9, 9)")


def rule(selector):
    match = re.search(re.escape(selector) + r"\s*\{([^}]+)\}", CSS)
    assert match, selector
    return match.group(1)


def test_muted_approve_dot_never_pulses(editor_page):
    from playwright.sync_api import expect

    button = editor_page.locator("#dpb-btn-approve")
    dot = button.locator(".dpb-approve-dot")
    button.evaluate("el => { el.classList.remove('dpb-approve-muted'); el.classList.add('dpb-approve-ready'); }")
    expect(dot).to_have_css("animation-name", "dpb-ping")
    # Muted wins even when an earlier ready class remains on the control.
    button.evaluate("el => el.classList.add('dpb-approve-muted')")
    expect(dot).to_have_css("animation-name", "none")


def test_editor_input_inherits_panel_font(editor_page):
    from playwright.sync_api import expect

    editor_page.locator("#dpb-tab-visual").click()
    field = editor_page.locator(".dpb-react-field input").first
    parent_font = field.evaluate("el => getComputedStyle(el.parentElement).fontFamily")
    expect(field).to_have_css("font-family", parent_font)
    expect(field).to_have_css("font-size", "11px")


def test_preview_header_truncates_long_labels_without_overflow(editor_page):
    from playwright.sync_api import expect

    page = editor_page
    crumb = page.locator(".dpb-crumb-screen")
    crumb.evaluate("el => el.textContent = 'Long screen title '.repeat(20)")
    expect(crumb).to_have_css("overflow", "hidden")
    expect(crumb).to_have_css("text-overflow", "ellipsis")
    label = page.locator("#dpb-approve-label")
    label.evaluate("el => el.textContent = 'Confirm this reviewed design with annotations (999999999 annotations)'")
    expect(label).to_have_css("text-overflow", "ellipsis")
    expect(label).to_have_css("white-space", "nowrap")
    assert label.evaluate("el => el.scrollWidth > el.clientWidth")
    for selector in (".dpb-header", "#dpb-btn-approve"):
        assert page.locator(selector).evaluate("el => el.getBoundingClientRect().right <= innerWidth")
    assert page.locator(".dpb-toasts").evaluate("el => Number(getComputedStyle(el).zIndex)") > (
        page.locator(".dpb-header").evaluate("el => Number(getComputedStyle(el).zIndex)")
    )


@pytest.fixture
def console_page():
    from playwright.sync_api import expect, sync_playwright
    from tests.run_console.test_ui_browser import ConsoleHarness

    console = ConsoleHarness()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                page.set_default_timeout(5000)
                page.goto(console.url(f"#token={console.token}"))
                expect(page.locator("#view-ready")).to_be_visible()
                yield page
            finally:
                browser.close()
    finally:
        console.close()


def token_color(page, token):
    return page.evaluate("""token => {
        const probe = document.createElement('span');
        probe.style.color = 'var(' + token + ')';
        document.body.append(probe);
        const color = getComputedStyle(probe).color;
        probe.remove();
        return color;
    }""", token)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_console_export_dialog_uses_theme_tokens_and_focus_ring(console_page, theme):
    from playwright.sync_api import expect

    page = console_page
    page.emulate_media(color_scheme=theme)
    page.get_by_role("button", name="Export diagnostics").click()
    dialog = page.locator(".export-dialog")
    expect(dialog).to_be_visible()
    expect(dialog).to_have_css("background-color", token_color(page, "--dpb-elev"))
    expect(dialog).to_have_css("border-top-color", token_color(page, "--dpb-line-strong"))
    for selector in (".export-ref-input", ".export-pre"):
        for element in dialog.locator(selector).all():
            expect(element).to_have_css("background-color", token_color(page, "--dpb-bg"))
            expect(element).to_have_css("border-top-color", token_color(page, "--dpb-line-strong"))
    field = dialog.locator(".export-ref-input")
    field.focus()
    expect(field).to_have_css("outline-style", "solid")
    expect(field).to_have_css("outline-width", "2px")
    expect(field).to_have_css("outline-color", token_color(page, "--dpb-focus"))
    expect(dialog.locator(".export-error")).to_have_css("color", token_color(page, "--dpb-danger"))


def test_console_secondary_buttons_are_not_translucent(console_page):
    from playwright.sync_api import expect

    button = console_page.locator(".button-secondary").first
    expect(button).to_be_visible()
    expect(button).to_have_css("opacity", "1")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_console_next_action_stripe_is_neutral(console_page, theme):
    from playwright.sync_api import expect

    page = console_page
    page.emulate_media(color_scheme=theme)
    next_action = page.locator("#fact-grid .fact").nth(3)
    expect(next_action.locator("h3")).to_have_text("4. Next action")
    expect(next_action).to_have_css("border-top-color", token_color(page, "--dpb-muted"))
    assert next_action.evaluate("el => getComputedStyle(el).borderTopColor") != (
        page.locator("#fact-grid .fact").first.evaluate("el => getComputedStyle(el).borderTopColor")
    )


@pytest.mark.parametrize("width", [320, 480, 641, 1280])
def test_console_section_hint_text_remains_visible(console_page, width):
    from playwright.sync_api import expect

    page = console_page
    page.set_viewport_size({"width": width, "height": 900})
    hints = page.locator(".section-hint:visible")
    assert hints.count() > 1
    for hint in hints.all():
        expect(hint).to_have_css("white-space", "normal")
        expect(hint).to_have_css("overflow", "visible")
        expect(hint).not_to_have_css("text-overflow", "ellipsis")
        assert hint.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
        assert hint.evaluate("el => el.scrollHeight <= el.clientHeight + 1")


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


def test_round3_narrow_visual_inspector_has_one_column_and_clearance(editor_page):
    from playwright.sync_api import expect

    page = editor_page
    page.set_viewport_size({"width": 320, "height": 800})
    page.locator("#dpb-tab-visual").click()
    grid = page.locator(".dpb-react-fields")
    assert len(grid.evaluate("el => getComputedStyle(el).gridTemplateColumns").split()) == 1
    expect(page.locator("#dpb-visual-view")).to_have_css("padding-bottom", "80px")
    for prop in ("line-height", "margin", "padding"):
        field = page.locator(f'.dpb-react-field[data-property="{prop}"] input')
        field.scroll_into_view_if_needed()
        assert field.evaluate("el => { const r = el.getBoundingClientRect(); "
                              "return r.left >= 0 && r.right <= innerWidth && "
                              "document.elementFromPoint(r.x + r.width / 2, "
                              "r.y + r.height / 2) === el; }")


def test_round3_console_single_primary_compact_mobile_row(console_page):
    from playwright.sync_api import expect

    page = console_page
    page.set_viewport_size({"width": 320, "height": 800})
    expect(page.locator("#reload-button")).to_have_class(re.compile("button-secondary"))
    expect(page.locator("#refresh-button")).not_to_have_class(re.compile("button-secondary"))
    reload_box, refresh_box = page.locator("#reload-button, #refresh-button").evaluate_all(
        "els => els.map(el => el.getBoundingClientRect().toJSON())")
    assert abs(reload_box["y"] - refresh_box["y"]) <= 1
    assert refresh_box["x"] + refresh_box["width"] <= 320
