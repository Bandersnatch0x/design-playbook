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
    assert "outline: 2px solid var(--dpb-accent)" in rule(
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


@pytest.fixture
def pending_visual_edit(editor_page):
    from playwright.sync_api import expect

    page = editor_page
    target = page.frame_locator("iframe.dpb-proto-frame").locator("#panel-title")
    target.evaluate("el => el.click()")
    page.keyboard.press("Escape")
    page.locator("#dpb-tab-visual").click()
    field = page.locator('.dpb-react-field[data-property="background-color"] input')
    expect(field).to_be_enabled()
    field.fill("rgb(9, 9, 9)")
    expect(page.locator("#dpb-visual-count")).to_have_text("1")
    return page


@pytest.mark.parametrize("modifier", ["Control", "Meta"])
@pytest.mark.parametrize("selector", ["#dpb-feedback", "#dpb-anno-input"])
def test_n1_native_text_undo_does_not_replay_visual_history(
    pending_visual_edit, modifier, selector,
):
    from playwright.sync_api import expect

    page = pending_visual_edit
    if selector == "#dpb-anno-input":
        page.frame_locator("iframe.dpb-proto-frame").locator("#panel-title").evaluate(
            "el => el.click()")
    field = page.locator(selector)
    field.focus()
    page.keyboard.type("Audit note")
    page.evaluate("""() => {
        window.addEventListener('keydown', event => {
            if (event.key.toLowerCase() === 'z') window.undoPrevented = event.defaultPrevented;
        });
    }""")
    page.keyboard.press(f"{modifier}+z")
    expect(page.locator("#dpb-visual-count")).to_have_text("1")
    assert page.evaluate("window.undoPrevented") is False
    # Chromium on Windows uses Control for native undo; Meta still must pass through.
    if modifier == "Control":
        assert len(field.input_value()) < len("Audit note")
        page.keyboard.press("Control+Shift+z")
    expect(field).to_have_value("Audit note")
    expect(page.locator("#dpb-visual-count")).to_have_text("1")


@pytest.mark.parametrize("modifier", ["Control", "Meta"])
def test_n1_visual_button_shortcuts_own_visual_history(pending_visual_edit, modifier):
    from playwright.sync_api import expect

    page = pending_visual_edit
    count = page.locator("#dpb-visual-count")
    actions = page.locator(".dpb-react-actions button")
    for redo in (f"{modifier}+Shift+z", f"{modifier}+y"):
        actions.first.focus()
        page.keyboard.press(f"{modifier}+z")
        expect(count).to_have_text("0")
        actions.nth(1).focus()
        page.keyboard.press(redo)
        expect(count).to_have_text("1")


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("action", ["undo", "redo"])
def test_n2_history_focus_contrast_at_least_three(pending_visual_edit, theme, action):
    from playwright.sync_api import expect

    page = pending_visual_edit
    page.locator("#dpb-root").evaluate("(el, theme) => el.dataset.theme = theme", theme)
    actions = page.locator(".dpb-react-actions button")
    if action == "redo":
        actions.first.click()
        expect(page.locator("#dpb-visual-count")).to_have_text("0")
    button = actions.nth(int(action == "redo"))
    page.keyboard.press("Tab")
    button.focus()
    assert button.evaluate("el => el.matches(':focus-visible')")
    expect(button).to_have_css("outline-style", "solid")
    expect(button).to_have_css("outline-width", "2px")
    colors = button.evaluate("""el => {
        const outline = getComputedStyle(el).outlineColor;
        for (let parent = el.parentElement; parent; parent = parent.parentElement) {
            const background = getComputedStyle(parent).backgroundColor;
            if (background.startsWith('rgb(')) return {outline, background};
            if (background !== 'rgba(0, 0, 0, 0)') throw Error('Non-opaque background');
        }
        throw Error('Missing focus background');
    }""")
    foreground = [float(v) for v in re.findall(r"[\d.]+", colors["outline"])]
    background = [float(v) for v in re.findall(r"[\d.]+", colors["background"])]
    alpha = foreground[3] if len(foreground) == 4 else 1
    composite = [alpha * f + (1 - alpha) * b for f, b in zip(foreground, background)]

    def luminance(rgb):
        linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4
                  for v in (channel / 255 for channel in rgb)]
        return sum(v * weight for v, weight in zip(linear, (.2126, .7152, .0722)))

    low, high = sorted((luminance(composite), luminance(background)))
    contrast = (high + .05) / (low + .05)
    print(f"N2 {theme} {action}: {colors}, contrast={contrast:.3f}:1")
    assert contrast >= 3, (theme, action, colors, contrast)


@pytest.mark.parametrize("locale", ["en", "zh-CN"])
def test_n3_language_accessible_name_contains_visible_target(console_page, locale):
    from playwright.sync_api import expect

    page = console_page
    button = page.locator("#lang-toggle-button")
    if locale == "zh-CN":
        button.click()
    expect(page.locator("html")).to_have_attribute("lang", locale)
    target = page.locator("#lang-toggle-label").inner_text()
    print(f"N3 {locale}: visible={target}, accessible={button.aria_snapshot()}")
    expect(button).to_have_accessible_name(re.compile(re.escape(target)))


@pytest.mark.parametrize("modifier", ["Control", "Meta"])
def test_n1_annotation_history_stays_in_its_context(pending_visual_edit, modifier):
    from playwright.sync_api import expect

    page = pending_visual_edit
    page.frame_locator("iframe.dpb-proto-frame").locator("#panel-title").evaluate(
        "el => el.click()")
    page.locator("#dpb-anno-input").fill("Annotation history")
    page.locator("#dpb-anno-input").press("Enter")
    count = page.locator("#dpb-count-badge")
    expect(count).to_have_text("1")
    page.locator("#dpb-theme-toggle").focus()
    page.keyboard.press(f"{modifier}+z")
    expect(count).to_have_text("1")
    expect(page.locator("#dpb-visual-count")).to_have_text("1")
    page.locator("#dpb-undo-btn").focus()
    page.keyboard.press(f"{modifier}+z")
    expect(count).to_have_text("0")
    page.keyboard.press(f"{modifier}+Shift+z")
    expect(count).to_have_text("1")
    expect(page.locator("#dpb-visual-count")).to_have_text("1")

def test_section_collapse_expand(editor_page):
    from playwright.sync_api import expect

    page = editor_page
    proto = page.frame_locator("iframe.dpb-proto-frame")
    proto.locator("#panel-title").evaluate("el => el.click()")
    page.keyboard.press("Escape")
    page.locator("#dpb-tab-visual").click()

    section = page.locator('.dpb-inspector-section[data-section="typography"]')
    expect(section).to_have_class(re.compile(r"\bis-open\b"))
    header = section.locator(".dpb-section-header")
    header.click()
    expect(section).to_have_class(re.compile(r"\bis-collapsed\b"))
    expect(section.locator(".dpb-section-body")).not_to_be_visible()
    header.click()
    expect(section).to_have_class(re.compile(r"\bis-open\b"))
    expect(section.locator(".dpb-section-body")).to_be_visible()


def test_quad_row_trbl_input(editor_page):
    from playwright.sync_api import expect

    page = editor_page
    proto = page.frame_locator("iframe.dpb-proto-frame")
    target = proto.locator("#panel-title")
    target.evaluate("el => el.click()")
    page.keyboard.press("Escape")
    page.locator("#dpb-tab-visual").click()

    quad_cell_top = page.locator('.dpb-react-quad-row[data-quad="padding"] .dpb-quad-cell[data-axis="T"] input')
    expect(quad_cell_top).to_be_enabled()
    quad_cell_top.fill("16px")
    count = page.locator("#dpb-visual-count")
    expect(count).to_have_text("1")
    expect(target).to_have_css("padding-top", "16px")


def test_selection_overlay_resize_handle_drag(editor_page):
    from playwright.sync_api import expect

    page = editor_page
    proto = page.frame_locator("iframe.dpb-proto-frame")
    target = proto.locator("#panel-title")
    target.evaluate("el => el.click()")
    handle = proto.locator('.dpb-resize-handle[data-handle="se"]')
    expect(handle).to_be_visible()
    box = handle.bounding_box()
    assert box is not None
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] / 2 + 30, box["y"] + box["height"] / 2 + 20)
    page.mouse.up()
    count = page.locator("#dpb-visual-count")
    expect(count).not_to_have_text("0")


def test_alignment_guide_visibility(editor_page):
    from playwright.sync_api import expect

    page = editor_page
    proto = page.frame_locator("iframe.dpb-proto-frame")
    target = proto.locator("#panel-title")
    target.evaluate("el => el.click()")
    move_body = proto.locator(".dpb-move-body")
    expect(move_body).to_be_visible()
    guide_v = proto.locator("#dpb-guide-v")
    guide_h = proto.locator("#dpb-guide-h")
    assert guide_v is not None and guide_h is not None
    box = move_body.bounding_box()
    assert box is not None
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] / 2 + 10, box["y"] + box["height"] / 2 + 10)
    page.mouse.up()


def test_floating_text_toolbar_toggle(editor_page):
    from playwright.sync_api import expect

    page = editor_page
    proto = page.frame_locator("iframe.dpb-proto-frame")
    target = proto.locator("#panel-title")
    target.evaluate("el => el.click()")
    page.locator("#dpb-tab-visual").click()
    btn_bold = proto.locator('.dpb-tb-btn[data-action="bold"]')
    expect(btn_bold).to_be_visible()
    btn_bold.click()
    expect(target).to_have_css("font-weight", re.compile(r"^(400|normal)$"))
    count = page.locator("#dpb-visual-count")
    expect(count).to_have_text("1")
    btn_bold.click()
    expect(target).to_have_css("font-weight", re.compile(r"^(700|bold)$"))
    expect(count).to_have_text("2")


def test_color_picker_hex_input(editor_page):
    from playwright.sync_api import expect

    page = editor_page
    proto = page.frame_locator("iframe.dpb-proto-frame")
    target = proto.locator("#panel-title")
    target.evaluate("el => el.click()")
    color_btn = proto.locator(".dpb-tb-color-btn")
    expect(color_btn).to_be_visible()
    color_btn.click()
    color_picker = proto.locator("#dpb-color-picker")
    expect(color_picker).to_have_class(re.compile(r"\bis-open\b"))
    hex_input = color_picker.locator(".dpb-cp-hex")
    expect(hex_input).to_be_visible()
    hex_input.fill("#e11d48")
    hex_input.press("Enter")
    expect(target).to_have_css("color", "rgb(225, 29, 72)")


def test_bridge_supports_resize_and_move_messages(editor_page):
    from playwright.sync_api import expect

    page = editor_page
    proto = page.frame_locator("iframe.dpb-proto-frame")
    target = proto.locator("#panel-title")
    target.evaluate("el => el.click()")
    page.locator("iframe.dpb-proto-frame").evaluate('''el => {
        el.contentWindow.postMessage({
            dpbVisualEdit: { type: "resize", selector: "#panel-title", width: "250px", height: "80px" }
        }, "*");
    }''')
    expect(target).to_have_css("width", "250px")
    expect(target).to_have_css("height", "80px")
    page.locator("iframe.dpb-proto-frame").evaluate('''el => {
        el.contentWindow.postMessage({
            dpbVisualEdit: { type: "move", selector: "#panel-title", dx: 15, dy: 25 }
        }, "*");
    }''')
    expect(target).to_have_css("transform", "matrix(1, 0, 0, 1, 15, 25)")


# Independent interaction review: IR-01 through IR-19.
def select_interaction_target(page, css=""):
    from playwright.sync_api import expect

    target = page.frame_locator("iframe.dpb-proto-frame").locator("#panel-title")
    if css:
        target.evaluate("(el, css) => el.style.cssText = css", css)
    target.evaluate("el => el.click()")
    page.keyboard.press("Escape")
    page.locator("#dpb-tab-visual").click()
    expect(page.locator('.dpb-react-field[data-property="width"] input')).to_be_enabled()
    return target


def drag_interaction(page, handle, dx, dy, release=True):
    box = handle.bounding_box()
    assert box is not None
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    rect = handle.evaluate("el => ({width: el.getBoundingClientRect().width, height: el.getBoundingClientRect().height})")
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + dx * box["width"] / rect["width"], y + dy * box["height"] / rect["height"], steps=3)
    if release:
        page.mouse.up()


@pytest.mark.parametrize("edge", ["nw", "n", "ne", "e", "se", "s", "sw", "w"])
def test_resize_anchors_opposite_edge_and_content_box(editor_page, edge):
    from playwright.sync_api import expect

    page = editor_page
    target = select_interaction_target(page,
        "position:absolute;left:120px;top:100px;width:200px;height:100px;"
        "padding:12px;border:3px solid black;margin:0;box-sizing:content-box")
    before = target.evaluate("el => el.getBoundingClientRect().toJSON()")
    initial_style = target.get_attribute("style")
    proto = page.frame_locator("iframe.dpb-proto-frame")
    dx = -20 if "w" in edge else 30 if "e" in edge else 0
    dy = -15 if "n" in edge else 25 if "s" in edge else 0
    drag_interaction(page, proto.locator(f'[data-handle="{edge}"]'), dx, dy)
    after = target.evaluate("el => el.getBoundingClientRect().toJSON()")
    assert after["width"] == pytest.approx(before["width"] + abs(dx), abs=1)
    assert after["height"] == pytest.approx(before["height"] + abs(dy), abs=1)
    assert after["x"] == pytest.approx(before["x"] + min(dx, 0), abs=1)
    assert after["y"] == pytest.approx(before["y"] + min(dy, 0), abs=1)
    page.locator(".dpb-react-actions button").first.click()
    expect(page.locator("#dpb-visual-count")).to_have_text("0")
    assert target.get_attribute("style") == initial_style


@pytest.mark.parametrize("prop,value", [("font-size", "16px"), ("letter-spacing", "normal"), ("width", "auto"), ("line-height", "normal")])
def test_units_never_duplicate_suffix_or_label_keywords(editor_page, prop, value):
    from playwright.sync_api import expect

    target = select_interaction_target(editor_page)
    field = editor_page.locator(f'.dpb-react-field[data-property="{prop}"]')
    field.locator("input").fill(value)
    expect(field.locator(".dpb-unit-suffix")).to_have_count(0)
    if prop == "font-size":
        field.locator("input").fill("")
        field.locator("input").press_sequentially("20")
        expect(field.locator(".dpb-unit-suffix")).to_have_text("px")
        field.locator("input").press_sequentially("px")
        field.locator("input").press("Enter")
        expect(target).to_have_css("font-size", "20px")
        expect(field.locator(".dpb-unit-suffix")).to_have_count(0)


def test_quad_shorthand_and_sides_stay_in_sync(editor_page):
    from playwright.sync_api import expect

    page = editor_page
    target = select_interaction_target(page)
    quad = page.locator('[data-quad="padding"]')
    summary = quad.locator('[data-property="padding"] input')
    summary.fill("4px 8px 12px 16px")
    for axis, value in zip("TRBL", ["4px", "8px", "12px", "16px"]):
        expect(quad.locator(f'[data-axis="{axis}"] input')).to_have_value(value)
    summary.press("Enter")
    expect(target).to_have_css("padding-left", "16px")
    top = quad.locator('[data-axis="T"] input')
    top.fill("20px")
    expect(summary).to_have_value("20px 8px 12px 16px")
    top.press("Enter")
    expect(target).to_have_css("padding-top", "20px")
    page.locator(".dpb-react-actions button").first.click()
    expect(top).to_have_value("4px")
    expect(summary).to_have_value("4px 8px 12px 16px")


@pytest.mark.parametrize("prop", ["color", "background-color", "border-color"])
def test_inspector_swatch_opens_shared_picker_for_its_property(editor_page, prop):
    from playwright.sync_api import expect

    page = editor_page
    target = select_interaction_target(page)
    swatch = page.locator(f'[data-property="{prop}"] .dpb-color-swatch-preview')
    expect(swatch).to_have_attribute("type", "button")
    swatch.click()
    picker = page.frame_locator("iframe.dpb-proto-frame").locator("#dpb-color-picker")
    expect(picker).to_be_visible()
    picker.locator('.dpb-cp-swatch[data-color="#ef4444"]').click()
    expect(target).to_have_css(prop, "rgb(239, 68, 68)")
    expect(page.locator("#dpb-visual-count")).to_have_text("1")


def test_collapsed_header_indicates_pending_modifications(editor_page):
    from playwright.sync_api import expect

    page = editor_page
    select_interaction_target(page)
    section = page.locator('[data-section="typography"]')
    section.locator('[data-property="font-size"] input').fill("30px")
    expect(page.locator("#dpb-visual-count")).to_have_text("1")
    section.locator(".dpb-section-header").click()
    expect(section.locator(".dpb-section-modified")).to_be_visible()
    page.locator(".dpb-react-actions button").first.click()
    expect(section.locator(".dpb-section-modified")).to_have_count(0)


@pytest.mark.parametrize("transform", ["translate(-50%, -50%)", "rotate(20deg) scale(1.2)", "matrix(1, 0.2, 0.1, 1, 4, 5)"])
def test_move_preserves_stylesheet_transforms_and_undo(editor_page, transform):
    from playwright.sync_api import expect

    page = editor_page
    target = select_interaction_target(page, "position:absolute;left:200px;top:180px;width:180px;height:80px;margin:0")
    target.evaluate("(el, value) => { const style = document.createElement('style'); style.textContent = '#panel-title {transform:' + value + '}'; document.head.append(style); }", transform)
    target.evaluate("el => el.click()")
    before = target.evaluate("el => {const m = new DOMMatrix(getComputedStyle(el).transform); return [m.a,m.b,m.c,m.d,m.e,m.f]}")
    move = page.frame_locator("iframe.dpb-proto-frame").locator(".dpb-move-body")
    drag_interaction(page, move, 20, 10)
    after = target.evaluate("el => {const m = new DOMMatrix(getComputedStyle(el).transform); return [m.a,m.b,m.c,m.d,m.e,m.f]}")
    assert after[:4] == pytest.approx(before[:4])
    assert after[4:] == pytest.approx([before[4] + 20, before[5] + 10], abs=1)
    page.locator(".dpb-react-actions button").first.click()
    expect(page.locator("#dpb-visual-count")).to_have_text("0")
    assert target.evaluate("el => el.style.transform") == ""


def test_resize_hud_and_cached_raf_guides(editor_page):
    from playwright.sync_api import expect

    page = editor_page
    target = select_interaction_target(page, "position:absolute;left:120px;top:100px;width:200px;height:100px;margin:0")
    target.evaluate("""el => {
      window.siblingReads = 0;
      for (const sibling of el.parentElement.children) {
        if (sibling === el || sibling.id === 'dpb-float-root') continue;
        const read = sibling.getBoundingClientRect.bind(sibling);
        sibling.getBoundingClientRect = () => { window.siblingReads++; return read(); };
      }
    }""")
    proto = page.frame_locator("iframe.dpb-proto-frame")
    drag_interaction(page, proto.locator('[data-handle="se"]'), 20, 10, release=False)
    hud = proto.locator("#dpb-dimension-hud")
    expect(hud).to_have_text("220 × 110")
    reads = target.evaluate("() => window.siblingReads")
    assert reads > 0
    frames = target.evaluate("""el => {
      let frames = 0;
      const request = window.requestAnimationFrame;
      window.requestAnimationFrame = callback => { frames++; return request(callback); };
      const handle = document.querySelector('[data-handle="se"]');
      const rect = handle.getBoundingClientRect();
      for (let i = 0; i < 20; i++) handle.dispatchEvent(new PointerEvent('pointermove', {clientX:rect.x+i,clientY:rect.y+i}));
      return frames;
    }""")
    assert frames == 1
    handle_box = proto.locator('[data-handle="se"]').bounding_box()
    page.mouse.move(handle_box["x"] + 10, handle_box["y"] + 10, steps=5)
    assert target.evaluate("() => window.siblingReads") == reads
    page.mouse.up()
    expect(hud).not_to_be_visible()
    assert 'requestAnimationFrame(draw)' in (PREVIEW / "pin_bridge.py").read_text(encoding="utf-8")


@pytest.mark.parametrize("markup,visible", [("<span>Nested title</span>", False), ('<img alt="asset">', False), ("Direct title", True)])
def test_toolbar_only_appears_for_direct_text(editor_page, markup, visible):
    from playwright.sync_api import expect

    target = select_interaction_target(editor_page)
    target.evaluate("(el, html) => {el.innerHTML = html; el.click()}", markup)
    toolbar = editor_page.frame_locator("iframe.dpb-proto-frame").locator("#dpb-text-toolbar")
    if visible:
        expect(toolbar).to_be_visible()
    else:
        expect(toolbar).not_to_be_visible()


def test_toolbar_flips_below_top_text_and_italic_has_serifs(editor_page):
    from playwright.sync_api import expect

    target = select_interaction_target(editor_page, "position:absolute;top:0;left:0;margin:0;width:180px;height:30px")
    toolbar = editor_page.frame_locator("iframe.dpb-proto-frame").locator("#dpb-text-toolbar")
    top = toolbar.evaluate("el => el.getBoundingClientRect().top")
    bottom = target.evaluate("el => el.getBoundingClientRect().bottom")
    assert top >= bottom + 10
    expect(toolbar.locator(".dpb-tb-italic")).to_have_css("font-family", re.compile("Georgia"))


def test_picker_alpha_and_opacity_commit_once_per_gesture(editor_page):
    from playwright.sync_api import expect

    page = editor_page
    target = select_interaction_target(page, "color:rgb(239,68,68)")
    proto = page.frame_locator("iframe.dpb-proto-frame")
    proto.locator(".dpb-tb-color-btn").click()
    track = proto.locator(".dpb-cp-alpha")
    box = track.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 4, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=3)
    expect(target).to_have_css("color", "rgba(239, 68, 68, 0.5)")
    expect(page.locator("#dpb-visual-count")).to_have_text("0")
    page.mouse.up()
    expect(page.locator("#dpb-visual-count")).to_have_text("1")
    opacity = proto.locator(".dpb-cp-opacity")
    opacity.fill("75")
    expect(target).to_have_css("color", "rgba(239, 68, 68, 0.75)")
    opacity.press("Enter")
    expect(page.locator("#dpb-visual-count")).to_have_text("2")
    page.locator(".dpb-react-actions button").first.click()
    expect(target).to_have_css("color", "rgba(239, 68, 68, 0.5)")


def test_picker_dismissal_active_ring_and_namespaced_root(editor_page):
    from playwright.sync_api import expect

    page = editor_page
    select_interaction_target(page)
    proto = page.frame_locator("iframe.dpb-proto-frame")
    button = proto.locator(".dpb-tb-color-btn")
    picker = proto.locator("#dpb-color-picker")
    button.click()
    swatch = picker.locator('[data-color="#ef4444"]')
    swatch.click()
    expect(swatch).to_have_attribute("aria-pressed", "true")
    expect(swatch).to_have_css("outline-style", "solid")
    swatch.press("Escape")
    expect(picker).not_to_be_visible()
    button.click()
    proto.locator(".row").click(force=True)
    expect(picker).not_to_be_visible()
    root = proto.locator("#dpb-float-root")
    assert root.locator("#dpb-selection-overlay").count() == 1
    assert root.locator("#dpb-color-picker").count() == 1
    assert root.evaluate("el => [...el.querySelectorAll('[id]')].every(node => node.id.startsWith('dpb-'))")


@pytest.mark.parametrize("slider", ["sv", "hue", "alpha"])
def test_picker_sliders_support_keyboard(editor_page, slider):
    from playwright.sync_api import expect

    page = editor_page
    target = select_interaction_target(page, "color:rgb(239,68,68)")
    proto = page.frame_locator("iframe.dpb-proto-frame")
    proto.locator(".dpb-tb-color-btn").click()
    control = proto.locator(".dpb-cp-" + slider)
    expect(control).to_have_attribute("role", "slider")
    expect(control).to_have_attribute("tabindex", "0")
    original = target.evaluate("el => getComputedStyle(el).color")
    control.press("Shift+ArrowLeft" if slider != "hue" else "Shift+ArrowRight")
    assert target.evaluate("el => getComputedStyle(el).color") != original
    expect(control).to_have_css("outline-style", "solid")
    expect(page.locator("#dpb-visual-count")).to_have_text("1")


@pytest.mark.parametrize("control,step", [("[data-handle=nw]", 1), ("[data-handle=se]", 10), (".dpb-move-body", 10)])
def test_canvas_handles_support_keyboard_steps(editor_page, control, step):
    from playwright.sync_api import expect

    page = editor_page
    target = select_interaction_target(page, "position:absolute;left:120px;top:100px;width:200px;height:100px;margin:0")
    handle = page.frame_locator("iframe.dpb-proto-frame").locator(control)
    expect(handle).to_have_attribute("role", "slider")
    expect(handle).to_have_attribute("tabindex", "0")
    handle.press("Shift+ArrowRight" if step == 10 else "ArrowRight")
    expect(handle).to_have_css("outline-style", "solid")
    rect = target.evaluate("el => el.getBoundingClientRect().toJSON()")
    if control == ".dpb-move-body":
        assert rect["x"] == 130
    else:
        assert rect["width"] == 199 if step == 1 else rect["width"] == 210
    page.locator(".dpb-react-actions button").first.click()
    expect(page.locator("#dpb-visual-count")).to_have_text("0")


def test_gesture_receipt_does_not_settle_inflight_inspector_request(editor_page):
    from playwright.sync_api import expect

    page = editor_page
    page.add_init_script("""
      window.heldReceipts = []; window.gestureReceipts = [];
      addEventListener('message', e => {
        const payload = e.data.dpbVisualEditChange || e.data.dpbVisualEditSelection;
        if (!payload || e.released) return;
        if (typeof payload.requestId === 'number') {
          e.stopImmediatePropagation(); window.heldReceipts.push(e);
        } else if (e.data.dpbVisualEditChange) window.gestureReceipts.push(payload);
      }, true);
    """)
    page.reload()
    from preview_e2e_helpers import dismiss_onboarding

    dismiss_onboarding(page)
    target = select_interaction_target(page, "width:200px;height:100px")
    field = page.locator('[data-property="color"] input')
    field.fill("red")
    field.press("Enter")
    expect(target).to_have_css("color", "rgb(255, 0, 0)")
    page.frame_locator("iframe.dpb-proto-frame").locator('[data-handle="se"]').press("Shift+ArrowRight")
    expect(page.locator("#dpb-visual-count")).not_to_have_text("0")
    expect(page.locator(".dpb-react-actions button").first).to_be_disabled()
    receipts = page.evaluate("() => window.gestureReceipts")
    assert len(receipts) == 1 and receipts[0]["requestId"].startswith("gesture-")
    assert isinstance(receipts[0]["changes"], list)
    page.evaluate("""() => { for (const e of heldReceipts) {
      const receipt = new MessageEvent('message', {data:e.data,source:e.source});
      receipt.released=true; dispatchEvent(receipt);
    }}""")
    expect(page.locator(".dpb-react-actions button").first).to_be_enabled()
    assert any(edit["property"] == "color" for edit in page.evaluate("DPB_VISUAL_EDIT_BATCH.edits"))


@pytest.mark.parametrize("width", [320, 375, 480])
def test_narrow_toolbar_stays_inside_canvas_without_covering_handles(editor_page, width):
    page = editor_page
    page.locator("iframe.dpb-proto-frame").evaluate("(el, width) => el.style.width = width + 'px'", width)
    target = select_interaction_target(page, "position:absolute;left:0;top:0;margin:0;width:300px;height:30px")
    toolbar = page.frame_locator("iframe.dpb-proto-frame").locator("#dpb-text-toolbar")
    rect = toolbar.evaluate("el => el.getBoundingClientRect().toJSON()")
    assert rect["left"] >= 0 and rect["right"] <= width
    assert rect["top"] >= target.evaluate("el => el.getBoundingClientRect().bottom") + 10


def test_corner_resize_has_one_receipt_and_atomic_undo_redo(editor_page):
    from playwright.sync_api import expect

    page = editor_page
    target = select_interaction_target(page, "width:200px;height:100px")
    page.evaluate("""() => {window.receipts=[]; addEventListener('message', e => {
      if(e.data.dpbVisualEditChange) receipts.push(e.data.dpbVisualEditChange);
    });}""")
    proto = page.frame_locator("iframe.dpb-proto-frame")
    drag_interaction(page, proto.locator('[data-handle="se"]'), 20, 10)
    expect(page.locator("#dpb-visual-count")).to_have_text("2")
    receipts = page.evaluate("receipts")
    assert len(receipts) == 1
    assert receipts[0]["requestId"].startswith("gesture-")
    assert {edit["property"] for edit in receipts[0]["changes"]} == {"width", "height"}
    page.locator(".dpb-react-actions button").first.click()
    expect(target).to_have_css("width", "200px")
    expect(target).to_have_css("height", "100px")
    expect(page.locator("#dpb-visual-count")).to_have_text("0")
    page.locator(".dpb-react-actions button").nth(1).click()
    expect(target).to_have_css("width", "220px")
    expect(target).to_have_css("height", "110px")
    expect(page.locator("#dpb-visual-count")).to_have_text("2")


def test_batched_bridge_rejects_invalid_second_axis_without_partial_mutation(editor_page):
    from playwright.sync_api import expect

    page = editor_page
    target = select_interaction_target(page, "width:200px;height:100px")
    page.evaluate("""() => {window.rejections=[]; addEventListener('message', e => {
      if(e.data.dpbVisualEditRejected) rejections.push(e.data.dpbVisualEditRejected);
    });}""")
    page.locator("iframe.dpb-proto-frame").evaluate("""el => el.contentWindow.postMessage({
      dpbVisualEdit: {type:'set-style', requestId:991, selector:'#panel-title', changes:[
        {property:'width',value:'300px'}, {property:'height',value:'broken-value'}
      ]}}, '*')""")
    page.wait_for_function("rejections.length === 1")
    assert page.evaluate("rejections[0].code") == "visual_rejected"
    expect(target).to_have_css("width", "200px")
    expect(target).to_have_css("height", "100px")
    expect(page.locator("#dpb-visual-count")).to_have_text("0")


def test_cancelled_drag_restores_inline_values_without_pending_edits(editor_page):
    from playwright.sync_api import expect

    page = editor_page
    target = select_interaction_target(page, "width:200px;height:100px")
    original = target.get_attribute("style")
    handle = page.frame_locator("iframe.dpb-proto-frame").locator('[data-handle="nw"]')
    drag_interaction(page, handle, -20, -10, release=False)
    handle.dispatch_event("pointercancel", {"pointerId": 1})
    page.mouse.up()
    assert target.get_attribute("style") == original
    expect(page.locator("#dpb-visual-count")).to_have_text("0")


def test_narrow_host_docks_text_actions_outside_canvas_and_drawer(editor_page):
    from playwright.sync_api import expect

    page = editor_page
    page.set_viewport_size({"width": 320, "height": 900})
    target = select_interaction_target(page)
    if page.locator("#dpb-root").get_attribute("lang").startswith("zh"):
        page.locator("#dpb-language-toggle").click()
    dock = page.locator(".dpb-compact-text-toolbar")
    expect(dock).to_be_visible()
    expect(page.frame_locator("iframe.dpb-proto-frame").locator("#dpb-text-toolbar")).not_to_be_visible()
    button = dock.get_by_role("button", name="Italic", exact=True)
    button.click()
    expect(target).to_have_css("font-style", "italic")
    expect(page.locator("#dpb-visual-count")).to_have_text("1")
    expect(button).to_have_attribute("aria-pressed", "true")
    box = button.bounding_box()
    feedback = page.locator("#dpb-feedback").bounding_box()
    assert box["y"] + box["height"] < feedback["y"]


# IP-01..IP-13: full state, keyboard, localization and stable geometry.
def set_review_locale(page, locale):
    if page.locator("#dpb-root").get_attribute("lang").split("-")[0] != locale:
        page.locator("#dpb-language-toggle").click()


@pytest.mark.parametrize("locale", ["zh", "en"])
def test_ip01_filtered_empty_guidance_and_ip02_resolved_badge(editor_page, locale):
    from playwright.sync_api import expect

    page = editor_page
    set_review_locale(page, locale)
    proto = page.frame_locator("iframe.dpb-proto-frame")
    proto.locator("#panel-title").evaluate("el => el.click()")
    page.locator("#dpb-anno-input").fill("Review this title")
    page.locator("#dpb-anno-input").press("Enter")
    page.locator("#dpb-filter-resolved").click()
    empty = page.locator(".dpb-anchor-empty")
    expect(empty).to_be_visible()
    expect(empty.locator("svg")).to_be_visible()
    expect(empty).to_contain_text("当前筛选" if locale == "zh" else "match this filter")
    page.locator("#dpb-filter-all").click()
    expect(empty).to_have_count(0)
    page.locator(".dpb-anchor-resolve").click()
    badge = proto.locator(".dpb-pin-badge")
    expect(badge).to_have_class(re.compile("dpb-resolved"))
    expect(badge).to_have_css("opacity", "0.5")
    page.locator(".dpb-anchor-resolve").click()
    expect(badge).not_to_have_class(re.compile("dpb-resolved"))


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_ip03_all_review_and_bridge_controls_have_focus_rings(editor_page, theme):
    from playwright.sync_api import expect

    page = editor_page
    page.locator("#dpb-root").evaluate("(el, theme) => el.dataset.theme = theme", theme)
    page.keyboard.press("Tab")
    for selector in ("#dpb-roam-prev", "#dpb-roam-next", "#dpb-inspector-close",
                     "#dpb-draft", "#dpb-abort", "#dpb-language-toggle", "#dpb-theme-toggle",
                     "#dpb-drawer-toggle", "#dpb-shortcuts-btn", "#dpb-filter-all", "#dpb-btn-approve"):
        button = page.locator(selector)
        button.focus()
        expect(button).to_have_css("outline-style", "solid")
        expect(button).to_have_css("outline-width", "2px")
    select_interaction_target(page)
    proto = page.frame_locator("iframe.dpb-proto-frame")
    for selector in (".dpb-tb-italic", ".dpb-handle-se"):
        control = proto.locator(selector)
        control.focus()
        expect(control).to_have_css("outline-style", "solid")
    proto.locator(".dpb-tb-color-btn").click()
    page.keyboard.press("Tab")
    for selector in (".dpb-cp-hue", ".dpb-cp-hex", ".dpb-cp-swatch"):
        control = proto.locator(selector).first
        control.focus()
        expect(control).to_have_css("outline-style", "solid")


def test_ip04_loading_until_bridge_ready_and_reduced_motion(editor_page):
    from playwright.sync_api import expect

    page = editor_page
    expect(page.locator("#dpb-prototype-loading")).to_be_hidden()
    page.locator("#dpb-tab-visual").click()
    page.locator("iframe.dpb-proto-frame").evaluate("el => el.srcdoc = '<html><body>Loading route</body></html>'")
    loading = page.locator("#dpb-prototype-loading")
    expect(loading).to_be_visible()
    expect(page.locator(".dpb-react-editor .dpb-loading")).to_be_visible()
    expect(page.locator("#dpb-artboard-inner")).to_have_attribute("aria-busy", "true")
    page.emulate_media(reduced_motion="reduce")
    expect(loading.locator(".dpb-skeleton")).to_have_css("animation-name", "none")
    page.reload()
    expect(loading).to_be_hidden()
    expect(page.locator("#dpb-artboard-inner")).to_have_attribute("aria-busy", "false")


@pytest.mark.parametrize("modifier", ["Control", "Meta"])
def test_ip05_frame_shortcuts_and_ip08_canvas_history(pending_visual_edit, modifier):
    from playwright.sync_api import expect

    page = pending_visual_edit
    proto = page.frame_locator("iframe.dpb-proto-frame")
    handle = proto.locator(".dpb-handle-se")
    handle.focus()
    page.keyboard.press(f"{modifier}+z")
    expect(page.locator("#dpb-visual-count")).to_have_text("0")
    page.keyboard.press(f"{modifier}+Shift+z")
    expect(page.locator("#dpb-visual-count")).to_have_text("1")
    old_lang = page.locator("#dpb-root").get_attribute("lang")
    page.keyboard.press("l")
    expect(page.locator("#dpb-root")).not_to_have_attribute("lang", old_lang)
    page.keyboard.press("?")
    expect(page.locator("#dpb-shortcut-close")).to_be_focused()
    page.keyboard.press("Escape")
    page.evaluate("""() => {
      window.submitted = [];
      document.querySelector('form').addEventListener('submit', e => {
        e.preventDefault(); window.submitted.push(e.submitter.id);
      });
    }""")
    handle.focus()
    page.keyboard.press(f"{modifier}+Enter")
    page.wait_for_function("window.submitted.includes('dpb-btn-approve')")
    # Wait for the advisory floor's asynchronous focus before returning to the frame.
    expect(page.locator("#dpb-feedback")).to_be_focused()
    handle.focus()
    expect(handle).to_be_focused()
    page.keyboard.press("Shift+Escape")
    page.wait_for_function("window.submitted.includes('dpb-btn-skip')")
    proto.locator("body").evaluate("el => {const input=document.createElement('input'); input.id='ip-input'; el.append(input)}")
    proto.locator("#ip-input").focus()
    page.keyboard.press(f"{modifier}+Enter")
    assert page.evaluate("window.submitted.length") == 2


def test_skip_shortcut_submits_while_feedback_has_focus(editor_page):
    from playwright.sync_api import expect

    page = editor_page
    page.evaluate("""() => {
      window.submitted = [];
      document.querySelector('form').addEventListener('submit', e => {
        e.preventDefault(); window.submitted.push(e.submitter.id);
      });
    }""")
    feedback = page.locator("#dpb-feedback")
    feedback.focus()
    expect(feedback).to_be_focused()
    page.keyboard.press("Shift+Escape")
    assert page.evaluate("window.submitted") == ["dpb-btn-skip"]


def test_ip06_inspector_enter_is_local_and_ip07_abort_focus(editor_page):
    from playwright.sync_api import expect

    page = editor_page
    select_interaction_target(page)
    page.evaluate("document.querySelector('form').addEventListener('submit', e => {e.preventDefault(); window.leaked = true})")
    field = page.locator('.dpb-react-field[data-property="width"] input')
    field.fill("250px")
    field.press("Control+Enter")
    expect(page.locator("#dpb-visual-count")).to_have_text("1")
    assert not page.evaluate("Boolean(window.leaked)")
    page.locator("#dpb-abort").click()
    expect(page.locator("#dpb-abort-cancel")).to_be_focused()
    page.keyboard.press("Shift+Tab")
    expect(page.locator("#dpb-abort-confirm")).to_be_focused()
    page.keyboard.press("Tab")
    expect(page.locator("#dpb-abort-cancel")).to_be_focused()
    page.locator("#dpb-theme-toggle").click()
    expect(page.locator("#dpb-abort")).to_be_focused()
    expect(page.locator("#dpb-abort-popover")).to_be_hidden()
    page.locator("#dpb-abort").click()
    page.keyboard.press("Escape")
    expect(page.locator("#dpb-abort")).to_be_focused()


@pytest.mark.parametrize("locale", ["zh", "en"])
def test_ip09_central_labels_render_in_inspector_and_bridge(editor_page, locale):
    from playwright.sync_api import expect
    from design_playbook.mcp.preview.i18n import EN, ZH, _STRINGS

    page = editor_page
    set_review_locale(page, locale)
    select_interaction_target(page)
    strings = _STRINGS[ZH if locale == "zh" else EN]
    expect(page.locator('[data-section="typography"] strong')).to_have_text(strings["sec_typography"])
    proto = page.frame_locator("iframe.dpb-proto-frame")
    expect(proto.locator(".dpb-tb-italic")).to_have_attribute("aria-label", strings["visual_italic"])
    expect(proto.locator(".dpb-handle-se")).to_have_attribute("aria-label", strings["visual_resize"].replace("{handle}", "se"))
    proto.locator(".dpb-tb-color-btn").click()
    expect(proto.locator(".dpb-cp-hue")).to_have_attribute("aria-label", strings["visual_hue"])
    expect(proto.locator(".dpb-cp-hex")).to_have_attribute("aria-label", strings["visual_hex"])
    page.locator("#dpb-language-toggle").click()
    other = _STRINGS[EN if locale == "zh" else ZH]
    expect(proto.locator(".dpb-tb-italic")).to_have_attribute("aria-label", other["visual_italic"])
    assert "var LABELS" not in JS


@pytest.mark.parametrize("locale", ["zh", "en"])
def test_ip10_layout_and_ip11_ip13_stable_borders(editor_page, locale):
    from playwright.sync_api import expect

    page = editor_page
    set_review_locale(page, locale)
    for width in (1024, 1280, 1440):
        page.set_viewport_size({"width": width, "height": 900})
        assert page.locator(".dpb-header").bounding_box()["height"] == 48
        assert page.locator(".dpb-rail-head").bounding_box()["height"] == 48
        assert page.locator("#dpb-inspector").bounding_box()["width"] == 320
    kbd = page.locator("#dpb-btn-approve kbd")
    before = kbd.bounding_box()["height"]
    page.locator("#dpb-btn-approve").evaluate("el => {el.classList.remove('dpb-approve-muted'); el.classList.add('dpb-approve-ready')}")
    expect(kbd).to_have_css("border-bottom-width", "2px")
    assert kbd.bounding_box()["height"] == before
    page.locator("#dpb-tab-visual").click()
    header = page.locator(".dpb-section-header").first
    before = header.bounding_box()["height"]
    header.click()
    expect(header).to_have_css("border-bottom-width", "1px")
    assert header.bounding_box()["height"] == before


def test_ip12_svg_coordinate_systems_follow_dimensions(editor_page):
    from playwright.sync_api import expect

    page = editor_page
    proto = page.frame_locator("iframe.dpb-proto-frame")
    page.locator("iframe.dpb-proto-frame").evaluate("""el => el.contentWindow.postMessage({
      dpbPinAnchors: [{selector: '@draw:1', tag: 'draw', n: 1, points: [[10,10],[40,40]]}]
    }, '*')""")
    page.locator("#dpb-ruler-toggle").click()
    proto.locator("#panel-title").hover()
    expect(proto.locator("#dpb-ruler-layer")).to_be_attached()
    for selector in (page.locator("#dpb-draw-layer"), proto.locator("#dpb-draw-layer"), proto.locator("#dpb-ruler-layer")):
        assert selector.evaluate("el => el.getAttribute('viewBox') === '0 0 ' + el.getAttribute('width') + ' ' + el.getAttribute('height')")


def test_rail_tabs_put_visual_editor_second(editor_page) -> None:
    """Rail order is annotations, visual editor, criteria.

    The visual editor is a primary review surface, so it sits directly after the
    annotations list instead of trailing the criteria tab.
    """
    ids = editor_page.evaluate(
        "() => [...document.querySelectorAll('.dpb-rail-tabs > button')].map(b => b.id)"
    )
    assert ids == ["dpb-tab-annotations", "dpb-tab-visual", "dpb-tab-spec"]


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
    # "验收准判 验收准判 0/1" is the defect this pins.
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
    # The approve tooltip is always reachable and states that edits travel along.
    assert "视觉编辑" in zh["confirm_desc"]
    assert "visual edit" in en["confirm_desc"].lower()


def test_visual_panel_submit_is_the_header_channel_gated_by_the_floor(editor_page) -> None:
    """The panel's own submit button mirrors the header state; one floor owner.

    Pending visual edits alone do not satisfy the ADR-0008 floor, so the local
    button must not re-derive readiness: it starts disabled with the shared
    not-ready wording, a note enables it, and clicking it submits through the
    same channel as the header button (submitter dpb-btn-approve).
    """
    from playwright.sync_api import expect

    from design_playbook.mcp.preview import i18n

    page = editor_page
    page.locator("#dpb-tab-visual").click()
    submit = page.locator("#dpb-visual-submit")
    expect(submit).to_be_visible()
    expect(submit).to_be_disabled()
    expect(submit).to_contain_text(i18n.t("approve_not_ready"))

    page.locator("#dpb-feedback").fill("Styles need a pass before this ships.")
    expect(submit).to_be_enabled()
    expect(submit).to_contain_text(i18n.t("visual_submit"))

    page.evaluate("""() => {
      window.dpbSubmitted = [];
      document.querySelector('form').addEventListener('submit', e => {
        e.preventDefault();
        window.dpbSubmitted.push(e.submitter ? e.submitter.id : '(null)');
      });
    }""")
    submit.click()
    page.wait_for_function("window.dpbSubmitted.includes('dpb-btn-approve')")

    # Withdrawing the note puts the whole gate back to not-ready.
    page.locator("#dpb-feedback").fill("")
    expect(submit).to_be_disabled()


def test_visual_submit_bar_stays_inside_the_scrolling_panel(editor_page) -> None:
    """The panel's primary action must never be something you scroll to find.

    #dpb-visual-view is the scroll container and the panel is far taller than the
    rail, so the submit bar is sticky to that scrollport and stays inside it at
    every offset.
    """
    page = editor_page
    page.locator("#dpb-tab-visual").click()
    page.locator("#dpb-visual-submit").wait_for(state="visible")

    def bar_state() -> dict:
        return page.evaluate("""() => {
          const view = document.getElementById('dpb-visual-view').getBoundingClientRect();
          const bar = document.querySelector('.dpb-react-submit').getBoundingClientRect();
          return {
            inside: bar.top >= view.top - 1 && bar.bottom <= view.bottom + 1,
            position: getComputedStyle(document.querySelector('.dpb-react-submit')).position,
          };
        }""")

    top = bar_state()
    assert top["position"] == "sticky", "the submit bar must ride the scrollport"
    assert top["inside"]

    page.evaluate(
        "() => { const v = document.getElementById('dpb-visual-view'); v.scrollTop = v.scrollHeight; }"
    )
    page.wait_for_timeout(150)
    assert bar_state()["inside"], "the submit bar left the scrollport after scrolling"
