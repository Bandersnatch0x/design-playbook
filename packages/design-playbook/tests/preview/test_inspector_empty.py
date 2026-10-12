"""U-27 (E-21): empty inspector renders no disabled fields; arrow keys step numbers."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.browser


def _page(pw, tmp_path):
    from tests.preview.test_visual_edit_acceptance import PROTOTYPE, review_session

    control = review_session._build_control(1, "Empty", ["Confirm"])
    path = tmp_path / "preview.html"
    path.write_text(review_session._build_parent_page(PROTOTYPE, control), encoding="utf-8")
    browser = pw.chromium.launch()
    page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
    page.goto(path.as_uri())
    return browser, page


def test_unselected_inspector_shows_empty_state_not_disabled_fields(tmp_path):
    from playwright.sync_api import sync_playwright, expect
    from preview_e2e_helpers import dismiss_onboarding

    with sync_playwright() as pw:
        browser, page = _page(pw, tmp_path)
        try:
            dismiss_onboarding(page)
            page.locator("#dpb-tab-visual").click()
            expect(page.locator(".dpb-react-empty")).to_be_visible()
            assert page.locator(".dpb-react-fields input:disabled, .dpb-react-fields select:disabled").count() == 0
            assert page.locator(".dpb-react-empty button").count() == 1
        finally:
            browser.close()


def test_arrow_keys_step_numeric_value(tmp_path):
    from playwright.sync_api import sync_playwright, expect
    from preview_e2e_helpers import dismiss_onboarding
    from tests.preview.test_visual_ui_regressions import select_interaction_target

    with sync_playwright() as pw:
        browser, page = _page(pw, tmp_path)
        try:
            dismiss_onboarding(page)
            target = select_interaction_target(page, "width: 100px")
            box = page.locator('.dpb-react-field[data-property="width"] input')
            box.fill("100")
            box.press("ArrowUp")
            assert box.input_value() == "101"
            box.press("Shift+ArrowUp")
            assert box.input_value() == "111"
            box.press("Alt+ArrowDown")
            assert box.input_value() == "110.9"
        finally:
            browser.close()
