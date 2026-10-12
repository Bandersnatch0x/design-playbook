"""U-05 (E-22): an invalid value is flagged before dispatch and a rejected one rolls back."""
from __future__ import annotations

import pytest

from tests.preview.test_inspector_empty import _page

pytestmark = pytest.mark.browser


def test_invalid_value_marks_field_and_does_not_dispatch(tmp_path):
    from playwright.sync_api import sync_playwright, expect
    from preview_e2e_helpers import dismiss_onboarding
    from tests.preview.test_visual_ui_regressions import select_interaction_target

    with sync_playwright() as pw:
        browser, page = _page(pw, tmp_path)
        try:
            dismiss_onboarding(page)
            select_interaction_target(page, "width: 100px")
            box = page.locator('.dpb-react-field[data-property="width"] input')
            box.fill("banana")
            box.press("Enter")
            expect(box).to_have_attribute("aria-invalid", "true")
            box.fill("120px")
            box.press("Enter")
            expect(box).not_to_have_attribute("aria-invalid", "true")
        finally:
            browser.close()


def test_invalid_value_reverts_to_accepted_on_blur_after_invalid(tmp_path):
    from playwright.sync_api import sync_playwright, expect
    from preview_e2e_helpers import dismiss_onboarding
    from tests.preview.test_visual_ui_regressions import select_interaction_target

    with sync_playwright() as pw:
        browser, page = _page(pw, tmp_path)
        try:
            dismiss_onboarding(page)
            select_interaction_target(page, "width: 100px")
            box = page.locator('.dpb-react-field[data-property="width"] input')
            box.fill("banana")
            box.press("Enter")
            expect(box).to_have_attribute("aria-invalid", "true")
            box.press("Escape")
            expect(box).not_to_have_attribute("aria-invalid", "true")
            assert box.input_value() != "banana"
        finally:
            browser.close()
